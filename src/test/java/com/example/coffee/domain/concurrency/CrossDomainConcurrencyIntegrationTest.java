package com.example.coffee.domain.concurrency;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import com.example.coffee.TestcontainersConfiguration;
import com.example.coffee.domain.order.repository.OrderRepository;
import com.example.coffee.domain.order.service.OrderService;
import com.example.coffee.domain.point.entity.PointHistory;
import com.example.coffee.domain.point.entity.PointHistoryType;
import com.example.coffee.domain.point.repository.PointHistoryRepository;
import com.example.coffee.domain.point.service.PointService;
import com.example.coffee.domain.user.repository.UserRepository;
import com.example.coffee.global.error.BusinessException;
import com.example.coffee.global.error.ErrorCode;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
@Import(TestcontainersConfiguration.class)
class CrossDomainConcurrencyIntegrationTest {

	private static final long USER_ID = 1L;
	private static final long MENU_ID = 1L;
	private static final long MENU_PRICE = 4500L;
	private static final long INITIAL_BALANCE = MENU_PRICE;
	private static final long CHARGE_AMOUNT = 1000L;

	@Autowired
	private PointService pointService;

	@Autowired
	private OrderService orderService;

	@Autowired
	private UserRepository userRepository;

	@Autowired
	private OrderRepository orderRepository;

	@Autowired
	private PointHistoryRepository pointHistoryRepository;

	@Autowired
	private JdbcTemplate jdbcTemplate;

	private ExecutorService executorService;

	@BeforeEach
	void resetData() {
		jdbcTemplate.update("DELETE FROM orders");
		jdbcTemplate.update("DELETE FROM point_history");
		jdbcTemplate.update("UPDATE users SET balance = ? WHERE id = ?", INITIAL_BALANCE, USER_ID);
		jdbcTemplate.update("UPDATE menus SET price = ? WHERE id = ?", MENU_PRICE, MENU_ID);
	}

	@AfterEach
	void shutdownExecutor() throws InterruptedException {
		if (executorService == null) {
			return;
		}
		executorService.shutdownNow();
		assertTrue(executorService.awaitTermination(5, TimeUnit.SECONDS));
	}

	@Test
	void 충전과_주문을_동시에_실행해도_잔액과_이력의_불변식을_지킨다() throws Exception {
		int chargeRequestCount = 10;
		int orderRequestCount = 10;
		int requestCount = chargeRequestCount + orderRequestCount;
		executorService = Executors.newFixedThreadPool(requestCount);
		CountDownLatch ready = new CountDownLatch(requestCount);
		CountDownLatch start = new CountDownLatch(1);
		List<Future<Boolean>> futures = new ArrayList<>();

		for (int i = 0; i < chargeRequestCount; i++) {
			futures.add(executorService.submit(() -> {
				ready.countDown();
				start.await();
				pointService.charge(USER_ID, CHARGE_AMOUNT);
				return true;
			}));
		}
		for (int i = 0; i < orderRequestCount; i++) {
			futures.add(executorService.submit(() -> {
				ready.countDown();
				start.await();
				try {
					orderService.order(USER_ID, MENU_ID);
					return true;
				} catch (BusinessException exception) {
					if (exception.getErrorCode() != ErrorCode.INSUFFICIENT_POINT) {
						throw exception;
					}
					return false;
				}
			}));
		}

		assertTrue(ready.await(10, TimeUnit.SECONDS));
		start.countDown();

		int successfulCharges = 0;
		int successfulOrders = 0;
		for (int i = 0; i < chargeRequestCount; i++) {
			if (futures.get(i).get(10, TimeUnit.SECONDS)) {
				successfulCharges++;
			}
		}
		for (int i = chargeRequestCount; i < requestCount; i++) {
			if (futures.get(i).get(10, TimeUnit.SECONDS)) {
				successfulOrders++;
			}
		}

		List<PointHistory> histories = pointHistoryRepository.findAllByUser_IdOrderByIdAsc(USER_ID);
		long chargeTotal = histories.stream()
				.filter(history -> history.getType() == PointHistoryType.CHARGE)
				.mapToLong(PointHistory::getAmount)
				.sum();
		long useTotal = histories.stream()
				.filter(history -> history.getType() == PointHistoryType.USE)
				.mapToLong(PointHistory::getAmount)
				.sum();
		long finalBalance = userRepository.findById(USER_ID).orElseThrow().getBalance();

		assertEquals(successfulCharges, histories.stream()
				.filter(history -> history.getType() == PointHistoryType.CHARGE)
				.count());
		assertEquals(successfulOrders, histories.stream()
				.filter(history -> history.getType() == PointHistoryType.USE)
				.count());
		assertEquals(successfulOrders, orderRepository.countByUser_Id(USER_ID));
		assertEquals(successfulCharges * CHARGE_AMOUNT, chargeTotal);
		assertEquals(successfulOrders * MENU_PRICE, useTotal);
		assertEquals(INITIAL_BALANCE + chargeTotal - useTotal, finalBalance);
		assertTrue(finalBalance >= 0);
	}
}
