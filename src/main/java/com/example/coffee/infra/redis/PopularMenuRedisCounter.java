package com.example.coffee.infra.redis;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

import com.example.coffee.domain.ranking.repository.PopularMenuCounter;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class PopularMenuRedisCounter implements PopularMenuCounter {

	private static final String KEY_PREFIX = "popular:menus:";
	private static final String KEY_SUFFIX = ":orders";
	private static final long MICROS_PER_SECOND = 1_000_000L;

	private final StringRedisTemplate redisTemplate;
	private final AtomicBoolean readModelStale = new AtomicBoolean();

	public PopularMenuRedisCounter(StringRedisTemplate redisTemplate) {
		this.redisTemplate = redisTemplate;
	}

	@Override
	public void record(Long orderId, Long menuId, LocalDateTime orderedAt) {
		try {
			redisTemplate.opsForZSet().add(
					key(menuId),
					orderId.toString(),
					toEpochMicros(orderedAt)
			);
		} catch (RuntimeException exception) {
			readModelStale.set(true);
			throw exception;
		}
	}

	@Override
	public Map<Long, Long> countByMenuIds(List<Long> menuIds, LocalDateTime from, LocalDateTime to) {
		if (readModelStale.get()) {
			throw new IllegalStateException("Redis 인기 메뉴 read model이 stale 상태입니다.");
		}

		try {
			long fromScore = toEpochMicros(from);
			long toScoreExclusive = toEpochMicros(to);
			Map<Long, Long> counts = new LinkedHashMap<>();

			for (Long menuId : menuIds) {
				Long count = redisTemplate.opsForZSet().count(key(menuId), fromScore, toScoreExclusive - 1);
				counts.put(menuId, count == null ? 0L : count);
			}

			return counts;
		} catch (RuntimeException exception) {
			readModelStale.set(true);
			throw exception;
		}
	}

	private String key(Long menuId) {
		return KEY_PREFIX + menuId + KEY_SUFFIX;
	}

	private long toEpochMicros(LocalDateTime dateTime) {
		Instant instant = dateTime.toInstant(ZoneOffset.UTC);
		return instant.getEpochSecond() * MICROS_PER_SECOND + instant.getNano() / 1_000;
	}
}
