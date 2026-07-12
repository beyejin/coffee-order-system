package com.example.coffee.domain.order;

import static org.hamcrest.Matchers.nullValue;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import com.example.coffee.TestcontainersConfiguration;
import com.example.coffee.domain.order.event.OrderDataMessage;
import com.example.coffee.domain.order.repository.OrderRepository;
import com.example.coffee.domain.order.service.DataPlatformClient;
import com.example.coffee.domain.order.service.OrderService;
import com.example.coffee.global.error.BusinessException;
import com.example.coffee.global.error.ErrorCode;
import com.example.coffee.domain.point.entity.PointHistory;
import com.example.coffee.domain.point.repository.PointHistoryRepository;
import com.example.coffee.domain.point.entity.PointHistoryType;
import com.example.coffee.domain.user.repository.UserRepository;
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
@Import({TestcontainersConfiguration.class, OrderIntegrationTest.DataPlatformTestConfiguration.class})
class OrderIntegrationTest {

	private static final long USER_ID = 1L;
	private static final long MENU_ID = 1L;
	private static final long MENU_PRICE = 4500L;

	@Autowired
	private MockMvc mockMvc;

	@Autowired
	private OrderService orderService;

	@Autowired
	private OrderRepository orderRepository;

	@Autowired
	private UserRepository userRepository;

	@Autowired
	private PointHistoryRepository pointHistoryRepository;

	@Autowired
	private JdbcTemplate jdbcTemplate;

	@Autowired
	private TestDataPlatformClient dataPlatformClient;

	private ExecutorService executorService;

	@BeforeEach
	void resetData() {
		dropRejectOrderConstraint();
		jdbcTemplate.update("DELETE FROM orders");
		jdbcTemplate.update("DELETE FROM point_history");
		jdbcTemplate.update("UPDATE user SET balance = 0 WHERE id = ?", USER_ID);
		jdbcTemplate.update("UPDATE menu SET price = ? WHERE id = ?", MENU_PRICE, MENU_ID);
		dataPlatformClient.reset();
	}

	@AfterEach
	void cleanUp() throws InterruptedException {
		try {
			assertTrue(dataPlatformClient.awaitSendCompletion(),
					"비동기 외부 전송 client가 종료되지 않았습니다.");
		} finally {
			dropRejectOrderConstraint();
			shutdownExecutor();
		}
	}

	@Test
	void 주문하면_가격을_보존하고_잔액_USE이력_주문을_함께_저장한_뒤_전송한다() throws Exception {
		setBalance(10000L);
		dataPlatformClient.expectSends(1);

		mockMvc.perform(post("/orders")
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"userId\":1,\"menuId\":1}"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.success").value(true))
				.andExpect(jsonPath("$.error").value(nullValue()))
				.andExpect(jsonPath("$.data.orderId").isNumber())
				.andExpect(jsonPath("$.data.userId").value(USER_ID))
				.andExpect(jsonPath("$.data.menuId").value(MENU_ID))
				.andExpect(jsonPath("$.data.price").value(MENU_PRICE))
				.andExpect(jsonPath("$.data.remainingBalance").value(5500));

		assertEquals(5500L, balance());
		assertEquals(1, orderRepository.countByUser_Id(USER_ID));
		List<PointHistory> histories = pointHistoryRepository.findAllByUser_IdOrderByIdAsc(USER_ID);
		assertEquals(1, histories.size());
		assertEquals(MENU_PRICE, histories.get(0).getAmount());
		assertEquals(PointHistoryType.USE, histories.get(0).getType());

		OrderDataMessage message = dataPlatformClient.awaitMessage();
		assertEquals(new OrderDataMessage(USER_ID, MENU_ID, MENU_PRICE), message);
		assertTrue(dataPlatformClient.wasCommittedOrderVisible());

		jdbcTemplate.update("UPDATE menu SET price = 9999 WHERE id = ?", MENU_ID);
		assertEquals(MENU_PRICE, jdbcTemplate.queryForObject(
				"SELECT price FROM orders WHERE user_id = ?", Long.class, USER_ID));
	}

	@Test
	void 잔액이_부족하면_409를_반환하고_DB를_변경하지_않는다() throws Exception {
		setBalance(4499L);

		mockMvc.perform(post("/orders")
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"userId\":1,\"menuId\":1}"))
				.andExpect(status().isConflict())
				.andExpect(jsonPath("$.success").value(false))
				.andExpect(jsonPath("$.data").value(nullValue()))
				.andExpect(jsonPath("$.error.code").value("INSUFFICIENT_POINT"));

		assertEquals(4499L, balance());
		assertNoOrderOrHistory();
		assertFalse(dataPlatformClient.wasInvoked());
	}

	@Test
	void 없는_메뉴는_404를_반환한다() throws Exception {
		setBalance(10000L);

		mockMvc.perform(post("/orders")
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"userId\":1,\"menuId\":999}"))
				.andExpect(status().isNotFound())
				.andExpect(jsonPath("$.error.code").value("MENU_NOT_FOUND"));

		assertEquals(10000L, balance());
		assertNoOrderOrHistory();
	}

	@Test
	void 없는_사용자는_404를_반환한다() throws Exception {
		mockMvc.perform(post("/orders")
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"userId\":999,\"menuId\":1}"))
				.andExpect(status().isNotFound())
				.andExpect(jsonPath("$.error.code").value("USER_NOT_FOUND"));

		assertNoOrderOrHistory();
	}

	@Test
	void ID가_누락되면_400_VALIDATION_ERROR를_반환한다() throws Exception {
		mockMvc.perform(post("/orders")
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"userId\":1}"))
				.andExpect(status().isBadRequest())
				.andExpect(jsonPath("$.success").value(false))
				.andExpect(jsonPath("$.error.code").value("VALIDATION_ERROR"));

		assertNoOrderOrHistory();
	}

	@Test
	void 사용자_ID가_누락되면_400_VALIDATION_ERROR를_반환하고_DB를_변경하지_않는다() throws Exception {
		mockMvc.perform(post("/orders")
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"menuId\":1}"))
				.andExpect(status().isBadRequest())
				.andExpect(jsonPath("$.success").value(false))
				.andExpect(jsonPath("$.data").value(nullValue()))
				.andExpect(jsonPath("$.error.code").value("VALIDATION_ERROR"));

		assertEquals(0L, balance());
		assertNoOrderOrHistory();
		assertFalse(dataPlatformClient.wasInvoked());
	}

	@Test
	void 주문_INSERT가_실패하면_잔액과_USE이력도_롤백되고_이벤트를_전송하지_않는다() {
		setBalance(10000L);
		jdbcTemplate.execute("""
				ALTER TABLE orders
				ADD CONSTRAINT chk_reject_order_insert CHECK (price < 0)
				""");

		assertThrows(DataIntegrityViolationException.class, () -> orderService.order(USER_ID, MENU_ID));

		assertEquals(10000L, balance());
		assertNoOrderOrHistory();
		assertFalse(dataPlatformClient.wasInvoked());
	}

	@Test
	void 동일_사용자_동시_주문은_가능한_수만_성공하고_잔액과_이력이_정확하다() throws Exception {
		setBalance(9000L);
		dataPlatformClient.expectSends(2);
		int requestCount = 10;
		executorService = Executors.newFixedThreadPool(requestCount);
		CountDownLatch ready = new CountDownLatch(requestCount);
		CountDownLatch start = new CountDownLatch(1);
		List<Future<Boolean>> futures = new ArrayList<>();

		for (int i = 0; i < requestCount; i++) {
			futures.add(executorService.submit(() -> {
				ready.countDown();
				start.await();
				try {
					orderService.order(USER_ID, MENU_ID);
					return true;
				} catch (BusinessException exception) {
					assertEquals(ErrorCode.INSUFFICIENT_POINT, exception.getErrorCode());
					return false;
				}
			}));
		}

		assertTrue(ready.await(10, TimeUnit.SECONDS));
		start.countDown();

		int successCount = 0;
		for (Future<Boolean> future : futures) {
			if (future.get(10, TimeUnit.SECONDS)) {
				successCount++;
			}
		}

		assertEquals(2, successCount);
		assertEquals(0L, balance());
		assertEquals(2, orderRepository.countByUser_Id(USER_ID));
		List<PointHistory> histories = pointHistoryRepository.findAllByUser_IdOrderByIdAsc(USER_ID);
		assertEquals(2, histories.size());
		assertTrue(histories.stream().allMatch(history -> history.getType() == PointHistoryType.USE));
		assertEquals(9000L, histories.stream().mapToLong(PointHistory::getAmount).sum());
		assertTrue(dataPlatformClient.awaitInvocationStart());
	}

	@Test
	void 외부_전송이_실패해도_주문_응답과_DB커밋은_유지된다() throws Exception {
		setBalance(10000L);
		dataPlatformClient.failNextSend();
		dataPlatformClient.expectSends(1);

		mockMvc.perform(post("/orders")
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"userId\":1,\"menuId\":1}"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.data.remainingBalance").value(5500));

		assertTrue(dataPlatformClient.awaitInvocationStart());
		assertEquals(5500L, balance());
		assertEquals(1, orderRepository.countByUser_Id(USER_ID));
		assertEquals(1, pointHistoryRepository.countByUser_Id(USER_ID));
	}

	private void assertNoOrderOrHistory() {
		assertEquals(0, orderRepository.count());
		assertEquals(0, pointHistoryRepository.count());
	}

	private long balance() {
		return userRepository.findById(USER_ID).orElseThrow().getBalance();
	}

	private void setBalance(long balance) {
		jdbcTemplate.update("UPDATE user SET balance = ? WHERE id = ?", balance, USER_ID);
	}

	private void dropRejectOrderConstraint() {
		Integer constraintCount = jdbcTemplate.queryForObject("""
				SELECT COUNT(*)
				FROM information_schema.table_constraints
				WHERE constraint_schema = DATABASE()
				  AND table_name = 'orders'
				  AND constraint_name = 'chk_reject_order_insert'
				""", Integer.class);

		if (constraintCount != null && constraintCount > 0) {
			jdbcTemplate.execute("ALTER TABLE orders DROP CHECK chk_reject_order_insert");
		}
	}

	private void shutdownExecutor() {
		if (executorService == null) {
			return;
		}

		executorService.shutdownNow();
		try {
			if (!executorService.awaitTermination(5, TimeUnit.SECONDS)) {
				throw new IllegalStateException("동시성 테스트 worker가 종료되지 않았습니다.");
			}
		} catch (InterruptedException exception) {
			Thread.currentThread().interrupt();
			throw new IllegalStateException("동시성 테스트 worker 종료 대기가 중단됐습니다.", exception);
		}
	}

	@TestConfiguration(proxyBeanMethods = false)
	static class DataPlatformTestConfiguration {

		@Bean
		@Primary
		TestDataPlatformClient testDataPlatformClient(JdbcTemplate jdbcTemplate) {
			return new TestDataPlatformClient(jdbcTemplate);
		}

	}

	static class TestDataPlatformClient implements DataPlatformClient {

		private final JdbcTemplate jdbcTemplate;
		private final BlockingQueue<OrderDataMessage> messages = new LinkedBlockingQueue<>();
		private final AtomicBoolean failNext = new AtomicBoolean();
		private final AtomicBoolean committedOrderVisible = new AtomicBoolean();
		private final AtomicInteger invocationCount = new AtomicInteger();
		private volatile CountDownLatch invocationStartedLatch = new CountDownLatch(1);
		private volatile CountDownLatch sendCompletedLatch = new CountDownLatch(0);

		TestDataPlatformClient(JdbcTemplate jdbcTemplate) {
			this.jdbcTemplate = jdbcTemplate;
		}

		@Override
		public void send(OrderDataMessage message) {
			boolean shouldFail = failNext.getAndSet(false);
			invocationCount.incrementAndGet();
			invocationStartedLatch.countDown();
			try {
				Integer orderCount = jdbcTemplate.queryForObject("""
						SELECT COUNT(*) FROM orders
						WHERE user_id = ? AND menu_id = ? AND price = ?
						""", Integer.class, message.userId(), message.menuId(), message.paymentAmount());
				committedOrderVisible.set(orderCount != null && orderCount > 0);
				messages.offer(message);

				if (shouldFail) {
					throw new IllegalStateException("외부 플랫폼 장애");
				}
			} finally {
				sendCompletedLatch.countDown();
			}
		}

		void reset() {
			messages.clear();
			failNext.set(false);
			committedOrderVisible.set(false);
			invocationCount.set(0);
			invocationStartedLatch = new CountDownLatch(1);
			sendCompletedLatch = new CountDownLatch(0);
		}

		void failNextSend() {
			failNext.set(true);
		}

		void expectSends(int count) {
			invocationStartedLatch = new CountDownLatch(count);
			sendCompletedLatch = new CountDownLatch(count);
		}

		OrderDataMessage awaitMessage() throws InterruptedException {
			OrderDataMessage message = messages.poll(5, TimeUnit.SECONDS);
			if (message == null) {
				throw new IllegalStateException("외부 전송 메시지를 받지 못했습니다.");
			}
			return message;
		}

		boolean awaitInvocationStart() throws InterruptedException {
			return invocationStartedLatch.await(5, TimeUnit.SECONDS);
		}

		boolean awaitSendCompletion() throws InterruptedException {
			return sendCompletedLatch.await(5, TimeUnit.SECONDS);
		}

		boolean wasInvoked() {
			return invocationCount.get() > 0;
		}

		boolean wasCommittedOrderVisible() {
			return committedOrderVisible.get();
		}
	}
}
