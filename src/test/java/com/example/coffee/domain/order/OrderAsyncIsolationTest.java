package com.example.coffee.domain.order;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import com.example.coffee.TestcontainersConfiguration;
import com.example.coffee.domain.order.event.OrderDataMessage;
import com.example.coffee.domain.order.service.DataPlatformClient;
import com.example.coffee.domain.order.service.OrderService;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@Import({TestcontainersConfiguration.class, OrderAsyncIsolationTest.BlockingClientConfiguration.class})
class OrderAsyncIsolationTest {

	@Autowired
	private MockMvc mockMvc;

	@Autowired
	private OrderService orderService;

	@Autowired
	private JdbcTemplate jdbcTemplate;

	@Autowired
	private BlockingDataPlatformClient dataPlatformClient;

	private ExecutorService executorService;

	@BeforeEach
	void resetData() {
		dropRejectOrderConstraint();
		jdbcTemplate.update("DELETE FROM orders");
		jdbcTemplate.update("DELETE FROM point_history");
		jdbcTemplate.update("UPDATE users SET balance = 10000 WHERE id = 1");
		dataPlatformClient.reset();
	}

	@AfterEach
	void cleanUp() throws InterruptedException {
		dataPlatformClient.release();
		dropRejectOrderConstraint();
		if (executorService != null) {
			executorService.shutdownNow();
			assertTrue(executorService.awaitTermination(5, TimeUnit.SECONDS));
		}
	}

	@Test
	void 외부_전송이_막혀도_주문_응답과_DB커밋은_전송보다_먼저_끝난다() throws Exception {
		dataPlatformClient.block();
		executorService = Executors.newSingleThreadExecutor();
		var responseFuture = executorService.submit(() -> mockMvc.perform(post("/orders")
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"userId\":1,\"menuId\":1}"))
				.andReturn());

		assertTrue(dataPlatformClient.awaitInvocation());
		var response = responseFuture.get(1, TimeUnit.SECONDS);

		assertEquals(200, response.getResponse().getStatus());
		assertEquals(1, jdbcTemplate.queryForObject("SELECT COUNT(*) FROM orders", Integer.class));
		assertEquals(5500L, jdbcTemplate.queryForObject(
				"SELECT balance FROM users WHERE id = 1", Long.class));

		dataPlatformClient.release();
	}

	@Test
	void 롤백된_주문은_AFTER_COMMIT_외부_전송을_제출하지_않는다() {
		jdbcTemplate.execute("""
				ALTER TABLE orders
				ADD CONSTRAINT chk_reject_async_order_insert CHECK (price < 0)
				""");

		try {
			assertThrows(DataIntegrityViolationException.class, () -> orderService.order(1L, 1L));
			assertEquals(0, jdbcTemplate.queryForObject("SELECT COUNT(*) FROM orders", Integer.class));
			assertEquals(0, dataPlatformClient.invocationCount());
		} finally {
			dropRejectOrderConstraint();
		}
	}

	private void dropRejectOrderConstraint() {
		Integer constraintCount = jdbcTemplate.queryForObject("""
				SELECT COUNT(*)
				FROM information_schema.table_constraints
				WHERE constraint_schema = DATABASE()
				  AND table_name = 'orders'
				  AND constraint_name = 'chk_reject_async_order_insert'
				""", Integer.class);

		if (constraintCount != null && constraintCount > 0) {
			jdbcTemplate.execute("ALTER TABLE orders DROP CHECK chk_reject_async_order_insert");
		}
	}

	@TestConfiguration(proxyBeanMethods = false)
	static class BlockingClientConfiguration {

		@Bean
		@Primary
		BlockingDataPlatformClient blockingDataPlatformClient() {
			return new BlockingDataPlatformClient();
		}
	}

	static class BlockingDataPlatformClient implements DataPlatformClient {

		private final AtomicInteger invocationCount = new AtomicInteger();
		private volatile CountDownLatch invocationLatch = new CountDownLatch(1);
		private volatile CountDownLatch releaseLatch = new CountDownLatch(0);

		@Override
		public void send(OrderDataMessage message) {
			invocationCount.incrementAndGet();
			invocationLatch.countDown();
			try {
				releaseLatch.await(5, TimeUnit.SECONDS);
			} catch (InterruptedException exception) {
				Thread.currentThread().interrupt();
				throw new IllegalStateException("외부 전송 대기가 중단됐습니다.", exception);
			}
		}

		void reset() {
			invocationCount.set(0);
			invocationLatch = new CountDownLatch(1);
			releaseLatch = new CountDownLatch(0);
		}

		void block() {
			releaseLatch = new CountDownLatch(1);
		}

		boolean awaitInvocation() throws InterruptedException {
			return invocationLatch.await(5, TimeUnit.SECONDS);
		}

		void release() {
			releaseLatch.countDown();
		}

		int invocationCount() {
			return invocationCount.get();
		}
	}
}
