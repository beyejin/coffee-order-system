package com.example.coffee.menu;

import static org.hamcrest.Matchers.nullValue;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import com.example.coffee.TestcontainersConfiguration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@Import({TestcontainersConfiguration.class, PopularMenuIntegrationTest.FixedClockConfiguration.class})
class PopularMenuIntegrationTest {

	private static final Instant FIXED_INSTANT = Instant.parse("2026-07-12T00:00:00.123456Z");
	private static final LocalDateTime TO = LocalDateTime.ofInstant(FIXED_INSTANT, ZoneOffset.UTC);
	private static final LocalDateTime FROM = TO.minusHours(168);

	@Autowired
	private MockMvc mockMvc;

	@Autowired
	private JdbcTemplate jdbcTemplate;

	@Autowired
	private MutableClock clock;

	@BeforeEach
	void resetData() {
		clock.setInstant(FIXED_INSTANT);
		jdbcTemplate.update("DELETE FROM orders");
		jdbcTemplate.update("DELETE FROM point_history");
		jdbcTemplate.update("UPDATE user SET balance = 0 WHERE id = 1");
		for (long menuId = 1; menuId <= 5; menuId++) {
			jdbcTemplate.update("""
					INSERT INTO menu (id, name, price)
					VALUES (?, ?, ?)
					ON DUPLICATE KEY UPDATE name = VALUES(name), price = VALUES(price)
					""", menuId, "메뉴" + menuId, 4000L + menuId * 500L);
		}
	}

	@Test
	void 시작_경계는_포함하고_종료_경계와_오래된_주문은_제외하며_현재_메뉴명을_반환한다() throws Exception {
		insertOrder(1L, FROM);
		insertOrder(1L, TO.minusNanos(1_000));
		insertOrder(2L, TO);
		insertOrder(3L, FROM.minusNanos(1_000));
		jdbcTemplate.update("UPDATE menu SET name = '현재 아메리카노' WHERE id = 1");

		mockMvc.perform(get("/menus/popular"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.success").value(true))
				.andExpect(jsonPath("$.error").value(nullValue()))
				.andExpect(jsonPath("$.data.length()").value(1))
				.andExpect(jsonPath("$.data[0].menuId").value(1))
				.andExpect(jsonPath("$.data[0].name").value("현재 아메리카노"))
				.andExpect(jsonPath("$.data[0].orderCount").value(2));
	}

	@Test
	void 실제_주문_API가_저장한_UTC_microsecond_주문을_인기_구간에서_집계한다() throws Exception {
		jdbcTemplate.update("UPDATE user SET balance = 10000 WHERE id = 1");
		clock.setInstant(FIXED_INSTANT.minusSeconds(1));

		mockMvc.perform(post("/orders")
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"userId\":1,\"menuId\":1}"))
				.andExpect(status().isOk());

		clock.setInstant(FIXED_INSTANT);
		mockMvc.perform(get("/menus/popular"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.data.length()").value(1))
				.andExpect(jsonPath("$.data[0].menuId").value(1))
				.andExpect(jsonPath("$.data[0].orderCount").value(1));

		assertEquals(
				TO.minusSeconds(1),
				jdbcTemplate.queryForObject("SELECT created_at FROM orders", LocalDateTime.class)
		);
	}

	@Test
	void 주문수_내림차순과_메뉴ID_동률순으로_상위_3개만_반환한다() throws Exception {
		insertOrders(1L, 3);
		insertOrders(2L, 3);
		insertOrders(3L, 2);
		insertOrders(4L, 1);

		mockMvc.perform(get("/menus/popular"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.data.length()").value(3))
				.andExpect(jsonPath("$.data[0].menuId").value(1))
				.andExpect(jsonPath("$.data[0].orderCount").value(3))
				.andExpect(jsonPath("$.data[1].menuId").value(2))
				.andExpect(jsonPath("$.data[1].orderCount").value(3))
				.andExpect(jsonPath("$.data[2].menuId").value(3))
				.andExpect(jsonPath("$.data[2].orderCount").value(2));
	}

	@Test
	void 최근_7일_주문이_없으면_빈_목록을_반환한다() throws Exception {
		mockMvc.perform(get("/menus/popular"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.success").value(true))
				.andExpect(jsonPath("$.data.length()").value(0))
				.andExpect(jsonPath("$.error").value(nullValue()));
	}

	@Test
	void 인기_메뉴_인덱스와_실제_MySQL_실행계획을_확인한다() {
		List<Map<String, Object>> indexRows = jdbcTemplate.queryForList("""
				SHOW INDEX FROM orders WHERE Key_name = 'idx_orders_created_at_menu_id'
				""");
		indexRows.sort(Comparator.comparingInt(row -> ((Number) row.get("Seq_in_index")).intValue()));

		assertEquals(2, indexRows.size());
		assertEquals("created_at", indexRows.get(0).get("Column_name"));
		assertEquals("menu_id", indexRows.get(1).get("Column_name"));

		List<Map<String, Object>> explainRows = jdbcTemplate.queryForList("""
				EXPLAIN
				SELECT m.id AS menuId, m.name AS name, COUNT(o.id) AS orderCount
				FROM orders o
				JOIN menu m ON m.id = o.menu_id
				WHERE o.created_at >= ? AND o.created_at < ?
				GROUP BY m.id, m.name
				ORDER BY orderCount DESC, m.id ASC
				LIMIT 3
				""", FROM, TO);

		assertFalse(explainRows.isEmpty());
		System.out.println("POPULAR_MENU_EXPLAIN=" + explainRows);
	}

	@Test
	void Testcontainers_MySQL과_JDBC_세션은_UTC를_사용한다() {
		assertEquals("+00:00", jdbcTemplate.queryForObject("SELECT @@session.time_zone", String.class));
		assertEquals(0L, jdbcTemplate.queryForObject(
				"SELECT TIMESTAMPDIFF(SECOND, UTC_TIMESTAMP(), NOW())",
				Long.class
		));
	}

	private void insertOrders(long menuId, int count) {
		for (int i = 0; i < count; i++) {
			insertOrder(menuId, TO.minusHours(i + 1L));
		}
	}

	private void insertOrder(long menuId, LocalDateTime createdAt) {
		jdbcTemplate.update("""
				INSERT INTO orders (user_id, menu_id, price, created_at)
				VALUES (1, ?, (SELECT price FROM menu WHERE id = ?), ?)
				""", menuId, menuId, createdAt);
	}

	@TestConfiguration(proxyBeanMethods = false)
	static class FixedClockConfiguration {

		@Bean
		@Primary
		MutableClock fixedClock() {
			return new MutableClock(FIXED_INSTANT);
		}
	}

	static class MutableClock extends Clock {

		private final AtomicReference<Instant> instant;

		MutableClock(Instant instant) {
			this.instant = new AtomicReference<>(instant);
		}

		void setInstant(Instant instant) {
			this.instant.set(instant);
		}

		@Override
		public ZoneId getZone() {
			return ZoneOffset.UTC;
		}

		@Override
		public Clock withZone(ZoneId zone) {
			return Clock.fixed(instant(), zone);
		}

		@Override
		public Instant instant() {
			return instant.get();
		}
	}
}
