package com.example.coffee.domain.ranking;

import static org.hamcrest.Matchers.nullValue;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
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
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
@AutoConfigureMockMvc
@Import({TestcontainersConfiguration.class, PopularMenuRedisIntegrationTest.FixedClockConfiguration.class})
class PopularMenuRedisIntegrationTest {

	private static final Instant TO = Instant.parse("2026-07-12T00:00:00.123456Z");
	private static final Instant FROM = TO.minusSeconds(7 * 24 * 60 * 60L);
	private static final long USER_ID = 1L;
	private static final String MENU_1_ORDERS_KEY = "popular:menus:1:orders";

	@Container
	static final GenericContainer<?> REDIS = new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
			.withExposedPorts(6379);

	@Autowired
	private MockMvc mockMvc;

	@Autowired
	private JdbcTemplate jdbcTemplate;

	@Autowired
	private StringRedisTemplate redisTemplate;

	@Autowired
	private MutableClock clock;

	@DynamicPropertySource
	static void redisProperties(DynamicPropertyRegistry registry) {
		registry.add("spring.data.redis.host", REDIS::getHost);
		registry.add("spring.data.redis.port", () -> REDIS.getMappedPort(6379));
		registry.add("spring.data.redis.connect-timeout", () -> "500ms");
		registry.add("spring.data.redis.timeout", () -> "500ms");
	}

	@BeforeEach
	void resetData() {
		clock.setInstant(TO);
		flushRedis();
		jdbcTemplate.update("DELETE FROM orders");
		jdbcTemplate.update("DELETE FROM point_history");
		jdbcTemplate.update("UPDATE users SET balance = 100000 WHERE id = ?", USER_ID);
		for (long menuId = 1; menuId <= 5; menuId++) {
			jdbcTemplate.update("""
					INSERT INTO menus (id, name, price)
					VALUES (?, ?, ?)
					ON DUPLICATE KEY UPDATE name = VALUES(name), price = VALUES(price)
					""", menuId, "메뉴" + menuId, 4000L + menuId * 500L);
		}
	}

	@Test
	void 성공한_주문은_커밋_후_메뉴별_ZSET에_반영되고_인기메뉴가_반환된다() throws Exception {
		placeOrderAt(TO.minusSeconds(3600), 1L);
		clock.setInstant(TO);

		assertEquals(1L, redisTemplate.opsForZSet().zCard(MENU_1_ORDERS_KEY));
		mockMvc.perform(get("/menus/popular"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.success").value(true))
				.andExpect(jsonPath("$.error").value(nullValue()))
				.andExpect(jsonPath("$.data[0].menuId").value(1))
				.andExpect(jsonPath("$.data[0].orderCount").value(1));
	}

	@Test
	void 최근_7일_경계는_Redis_ZSET에서도_정확하게_적용된다() throws Exception {
		placeOrderAt(FROM, 1L);
		placeOrderAt(TO.minusNanos(1_000), 1L);
		placeOrderAt(TO, 2L);
		placeOrderAt(FROM.minusNanos(1_000), 3L);
		clock.setInstant(TO);

		mockMvc.perform(get("/menus/popular"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.data.length()").value(1))
				.andExpect(jsonPath("$.data[0].menuId").value(1))
				.andExpect(jsonPath("$.data[0].orderCount").value(2));
	}

	@Test
	void 결제에_실패한_주문은_Redis_ZSET에_반영되지_않는다() throws Exception {
		jdbcTemplate.update("UPDATE users SET balance = 0 WHERE id = ?", USER_ID);

		mockMvc.perform(post("/orders")
					.contentType(MediaType.APPLICATION_JSON)
					.content("{\"userId\":1,\"menuId\":1}"))
				.andExpect(status().isConflict());

		assertEquals(0L, redisTemplate.opsForZSet().zCard(MENU_1_ORDERS_KEY));
	}

	private void placeOrderAt(Instant instant, long menuId) throws Exception {
		clock.setInstant(instant);
		mockMvc.perform(post("/orders")
					.contentType(MediaType.APPLICATION_JSON)
					.content("{\"userId\":1,\"menuId\":" + menuId + "}"))
				.andExpect(status().isOk());
	}

	private void flushRedis() {
		redisTemplate.execute((RedisCallback<Void>) connection -> {
			connection.serverCommands().flushDb();
			return null;
		});
	}

	@TestConfiguration(proxyBeanMethods = false)
	static class FixedClockConfiguration {

		@Bean
		@Primary
		MutableClock fixedClock() {
			return new MutableClock(TO);
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
