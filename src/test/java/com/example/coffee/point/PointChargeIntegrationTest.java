package com.example.coffee.point;

import static org.hamcrest.Matchers.nullValue;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import com.example.coffee.TestcontainersConfiguration;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@Import(TestcontainersConfiguration.class)
class PointChargeIntegrationTest {

	private static final long USER_ID = 1L;

	@Autowired
	private MockMvc mockMvc;

	@Autowired
	private PointService pointService;

	@Autowired
	private UserRepository userRepository;

	@Autowired
	private PointHistoryRepository pointHistoryRepository;

	@Autowired
	private JdbcTemplate jdbcTemplate;

	private ExecutorService executorService;

	@BeforeEach
	void resetPointData() {
		dropRejectPointHistoryConstraint();
		jdbcTemplate.update("DELETE FROM point_history");
		jdbcTemplate.update("UPDATE user SET balance = 0 WHERE id = ?", USER_ID);
	}

	@AfterEach
	void cleanUp() {
		dropRejectPointHistoryConstraint();
		shutdownExecutor();
	}

	@Test
	void 포인트를_충전하면_잔액과_CHARGE_이력이_함께_저장된다() throws Exception {
		mockMvc.perform(post("/users/{userId}/points/charge", USER_ID)
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"amount\":10000}"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.success").value(true))
				.andExpect(jsonPath("$.error").value(nullValue()))
				.andExpect(jsonPath("$.data.userId").value(USER_ID))
				.andExpect(jsonPath("$.data.balance").value(10000));

		User user = userRepository.findById(USER_ID).orElseThrow();
		List<PointHistory> histories = pointHistoryRepository.findAllByUser_IdOrderByIdAsc(USER_ID);

		assertEquals(10000L, user.getBalance());
		assertEquals(1, histories.size());
		assertEquals(10000L, histories.get(0).getAmount());
		assertEquals(PointHistoryType.CHARGE, histories.get(0).getType());
	}

	@ParameterizedTest
	@ValueSource(longs = {0, -1})
	void 충전_금액이_0_이하면_400을_반환하고_DB를_변경하지_않는다(long amount) throws Exception {
		mockMvc.perform(post("/users/{userId}/points/charge", USER_ID)
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"amount\":" + amount + "}"))
				.andExpect(status().isBadRequest())
				.andExpect(jsonPath("$.success").value(false))
				.andExpect(jsonPath("$.data").value(nullValue()))
				.andExpect(jsonPath("$.error.code").value("INVALID_CHARGE_AMOUNT"))
				.andExpect(jsonPath("$.error.message").value("충전 금액은 0보다 커야 합니다."));

		assertEquals(0L, userRepository.findById(USER_ID).orElseThrow().getBalance());
		assertEquals(0, pointHistoryRepository.countByUser_Id(USER_ID));
	}

	@Test
	void 충전_금액이_null이면_400을_반환하고_DB를_변경하지_않는다() throws Exception {
		mockMvc.perform(post("/users/{userId}/points/charge", USER_ID)
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"amount\":null}"))
				.andExpect(status().isBadRequest())
				.andExpect(jsonPath("$.success").value(false))
				.andExpect(jsonPath("$.data").value(nullValue()))
				.andExpect(jsonPath("$.error.code").value("INVALID_CHARGE_AMOUNT"));

		assertEquals(0L, userRepository.findById(USER_ID).orElseThrow().getBalance());
		assertEquals(0, pointHistoryRepository.countByUser_Id(USER_ID));
	}

	@Test
	void 존재하지_않는_사용자는_404를_반환한다() throws Exception {
		mockMvc.perform(post("/users/{userId}/points/charge", 999L)
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"amount\":1000}"))
				.andExpect(status().isNotFound())
				.andExpect(jsonPath("$.success").value(false))
				.andExpect(jsonPath("$.data").value(nullValue()))
				.andExpect(jsonPath("$.error.code").value("USER_NOT_FOUND"))
				.andExpect(jsonPath("$.error.message").value("사용자를 찾을 수 없습니다."));

		assertEquals(0, pointHistoryRepository.count());
	}

	@Test
	void 충전_후_잔액이_long_범위를_넘으면_409를_반환하고_DB를_변경하지_않는다() throws Exception {
		jdbcTemplate.update("UPDATE user SET balance = ? WHERE id = ?", Long.MAX_VALUE, USER_ID);

		mockMvc.perform(post("/users/{userId}/points/charge", USER_ID)
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"amount\":1}"))
				.andExpect(status().isConflict())
				.andExpect(jsonPath("$.success").value(false))
				.andExpect(jsonPath("$.data").value(nullValue()))
				.andExpect(jsonPath("$.error.code").value("POINT_BALANCE_OVERFLOW"))
				.andExpect(jsonPath("$.error.message").value("포인트 잔액이 허용 범위를 초과합니다."));

		assertEquals(Long.MAX_VALUE, userRepository.findById(USER_ID).orElseThrow().getBalance());
		assertEquals(0, pointHistoryRepository.countByUser_Id(USER_ID));
	}

	@Test
	void 잘못된_JSON은_공통_VALIDATION_ERROR를_반환한다() throws Exception {
		mockMvc.perform(post("/users/{userId}/points/charge", USER_ID)
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"amount\":"))
				.andExpect(status().isBadRequest())
				.andExpect(jsonPath("$.success").value(false))
				.andExpect(jsonPath("$.data").value(nullValue()))
				.andExpect(jsonPath("$.error.code").value("VALIDATION_ERROR"))
				.andExpect(jsonPath("$.error.message").value("요청 형식이 올바르지 않습니다."));
	}

	@Test
	void 빈_요청_본문은_공통_VALIDATION_ERROR를_반환한다() throws Exception {
		mockMvc.perform(post("/users/{userId}/points/charge", USER_ID)
				.contentType(MediaType.APPLICATION_JSON))
				.andExpect(status().isBadRequest())
				.andExpect(jsonPath("$.success").value(false))
				.andExpect(jsonPath("$.data").value(nullValue()))
				.andExpect(jsonPath("$.error.code").value("VALIDATION_ERROR"));
	}

	@Test
	void 사용자_ID가_숫자가_아니면_공통_VALIDATION_ERROR를_반환한다() throws Exception {
		mockMvc.perform(post("/users/abc/points/charge")
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"amount\":1000}"))
				.andExpect(status().isBadRequest())
				.andExpect(jsonPath("$.success").value(false))
				.andExpect(jsonPath("$.data").value(nullValue()))
				.andExpect(jsonPath("$.error.code").value("VALIDATION_ERROR"));
	}

	@Test
	void 충전_금액이_소수이면_공통_VALIDATION_ERROR를_반환하고_DB를_변경하지_않는다() throws Exception {
		mockMvc.perform(post("/users/{userId}/points/charge", USER_ID)
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"amount\":100.5}"))
				.andExpect(status().isBadRequest())
				.andExpect(jsonPath("$.success").value(false))
				.andExpect(jsonPath("$.data").value(nullValue()))
				.andExpect(jsonPath("$.error.code").value("VALIDATION_ERROR"));

		assertEquals(0L, userRepository.findById(USER_ID).orElseThrow().getBalance());
		assertEquals(0, pointHistoryRepository.countByUser_Id(USER_ID));
	}

	@Test
	void 이력_INSERT가_실패하면_잔액_변경도_롤백된다() {
		jdbcTemplate.execute("""
				ALTER TABLE point_history
				ADD CONSTRAINT chk_reject_point_history_insert CHECK (amount < 0)
				""");

		assertThrows(DataIntegrityViolationException.class, () -> pointService.charge(USER_ID, 1000L));

		assertEquals(0L, userRepository.findById(USER_ID).orElseThrow().getBalance());
		assertEquals(0, pointHistoryRepository.countByUser_Id(USER_ID));
	}

	@Test
	void 동일_사용자에게_동시에_충전해도_잔액과_이력이_유실되지_않는다() throws Exception {
		int requestCount = 20;
		long amount = 100L;
		executorService = Executors.newFixedThreadPool(requestCount);
		CountDownLatch ready = new CountDownLatch(requestCount);
		CountDownLatch start = new CountDownLatch(1);
		List<Future<ChargePointResponse>> futures = new ArrayList<>();

		for (int i = 0; i < requestCount; i++) {
			futures.add(executorService.submit(() -> {
				ready.countDown();
				start.await();
				return pointService.charge(USER_ID, amount);
			}));
		}

		assertTrue(ready.await(10, TimeUnit.SECONDS));
		start.countDown();

		for (Future<ChargePointResponse> future : futures) {
			future.get(10, TimeUnit.SECONDS);
		}

		User user = userRepository.findById(USER_ID).orElseThrow();
		List<PointHistory> histories = pointHistoryRepository.findAllByUser_IdOrderByIdAsc(USER_ID);

		assertEquals(requestCount * amount, user.getBalance());
		assertEquals(requestCount, histories.size());
		assertEquals(requestCount * amount,
				histories.stream().mapToLong(PointHistory::getAmount).sum());
		assertTrue(histories.stream().allMatch(history -> history.getType() == PointHistoryType.CHARGE));
	}

	private void dropRejectPointHistoryConstraint() {
		Integer constraintCount = jdbcTemplate.queryForObject("""
				SELECT COUNT(*)
				FROM information_schema.table_constraints
				WHERE constraint_schema = DATABASE()
				  AND table_name = 'point_history'
				  AND constraint_name = 'chk_reject_point_history_insert'
				""", Integer.class);

		if (constraintCount != null && constraintCount > 0) {
			jdbcTemplate.execute("ALTER TABLE point_history DROP CHECK chk_reject_point_history_insert");
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
}
