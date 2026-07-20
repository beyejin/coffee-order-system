package com.example.coffee.infra.kafka;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import com.example.coffee.TestcontainersConfiguration;
import com.example.coffee.domain.order.event.OrderDataMessage;
import com.example.coffee.domain.order.service.DataPlatformClient;
import com.example.coffee.domain.order.service.OrderService;
import org.springframework.dao.DataIntegrityViolationException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.annotation.DirtiesContext;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.kafka.KafkaContainer;

@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBootTest(properties = {
		"app.kafka.enabled=true",
		"app.kafka.topic=orders.paid.test",
		"app.kafka.consumer.group-id=coffee-order-data-platform-test",
		"app.kafka.consumer.concurrency=3",
		"spring.kafka.consumer.auto-offset-reset=earliest"
})
@Import({TestcontainersConfiguration.class, KafkaIntegrationTest.CapturingHandlerConfiguration.class})
class KafkaIntegrationTest {

	@Container
	static final KafkaContainer KAFKA = new KafkaContainer("apache/kafka:3.8.0")
			.withStartupTimeout(Duration.ofMinutes(2));

	@Autowired
	private OrderService orderService;

	@Autowired
	private DataPlatformClient dataPlatformClient;

	@Autowired
	private JdbcTemplate jdbcTemplate;

	@Autowired
	private CapturingKafkaOrderDataMessageHandler messageHandler;

	@DynamicPropertySource
	static void kafkaProperties(DynamicPropertyRegistry registry) {
		registry.add("spring.kafka.bootstrap-servers", KAFKA::getBootstrapServers);
	}

	@BeforeEach
	void resetData() {
		jdbcTemplate.update("DELETE FROM orders");
		jdbcTemplate.update("DELETE FROM point_history");
		jdbcTemplate.update("UPDATE users SET balance = 10000 WHERE id = 1");
		messageHandler.reset();
	}

	@Test
	void 주문이_커밋된_뒤_Kafka_Consumer가_메시지를_수신한다() throws Exception {
		var response = orderService.order(1L, 1L);

		assertEquals(5500L, response.remainingBalance());
		ReceivedKafkaMessage received = messageHandler.awaitMessage();

		assertEquals(new OrderDataMessage(1L, 1L, 4500L), received.message());
		assertEquals("1", received.metadata().key());
		assertTrue(received.metadata().partition() >= 0 && received.metadata().partition() < 3);
		assertTrue(received.metadata().offset() >= 0);
		assertEquals(1, jdbcTemplate.queryForObject("SELECT COUNT(*) FROM orders", Integer.class));
	}

	@Test
	void userId_key는_같은_Partition의_순서를_보존하고_서로_다른_key는_여러_Partition으로_분산된다() throws Exception {
		dataPlatformClient.send(new OrderDataMessage(1L, 1L, 1001L));
		dataPlatformClient.send(new OrderDataMessage(1L, 1L, 1002L));
		dataPlatformClient.send(new OrderDataMessage(1L, 1L, 1003L));

		ReceivedKafkaMessage first = messageHandler.awaitMessage();
		ReceivedKafkaMessage second = messageHandler.awaitMessage();
		ReceivedKafkaMessage third = messageHandler.awaitMessage();

		assertEquals(first.metadata().partition(), second.metadata().partition());
		assertEquals(second.metadata().partition(), third.metadata().partition());
		assertTrue(first.metadata().offset() < second.metadata().offset());
		assertTrue(second.metadata().offset() < third.metadata().offset());

		Set<Integer> partitions = new HashSet<>();
		for (long userId = 1L; userId <= 6L; userId++) {
			dataPlatformClient.send(new OrderDataMessage(userId, 1L, 2000L + userId));
			partitions.add(messageHandler.awaitMessage().metadata().partition());
		}
		assertTrue(partitions.size() >= 2);
	}

	@Test
	void 주문이_롤백되면_Kafka_Consumer에_메시지를_보내지_않는다() throws InterruptedException {
		jdbcTemplate.execute("""
				ALTER TABLE orders
				ADD CONSTRAINT chk_reject_kafka_order_insert CHECK (price < 0)
				""");

		try {
			assertThrows(DataIntegrityViolationException.class, () -> orderService.order(1L, 1L));
			assertEquals(10000L, jdbcTemplate.queryForObject(
					"SELECT balance FROM users WHERE id = 1", Long.class));
			assertTrue(messageHandler.awaitNoMessage());
		} finally {
			jdbcTemplate.execute("ALTER TABLE orders DROP CHECK chk_reject_kafka_order_insert");
		}
	}

	@TestConfiguration(proxyBeanMethods = false)
	static class CapturingHandlerConfiguration {

		@Bean
		@Primary
		CapturingKafkaOrderDataMessageHandler capturingKafkaOrderDataMessageHandler() {
			return new CapturingKafkaOrderDataMessageHandler();
		}
	}

	static class CapturingKafkaOrderDataMessageHandler implements KafkaOrderDataMessageHandler {

		private final BlockingQueue<ReceivedKafkaMessage> messages = new LinkedBlockingQueue<>();

		@Override
		public void handle(OrderDataMessage message, KafkaMessageMetadata metadata) {
			messages.offer(new ReceivedKafkaMessage(message, metadata));
		}

		void reset() {
			messages.clear();
		}

		ReceivedKafkaMessage awaitMessage() throws InterruptedException {
			ReceivedKafkaMessage message = messages.poll(15, TimeUnit.SECONDS);
			if (message == null) {
				throw new IllegalStateException("Kafka Consumer 메시지를 받지 못했습니다.");
			}
			return message;
		}

		boolean awaitNoMessage() throws InterruptedException {
			return messages.poll(2, TimeUnit.SECONDS) == null;
		}
	}

	record ReceivedKafkaMessage(OrderDataMessage message, KafkaMessageMetadata metadata) {
	}
}
