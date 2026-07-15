package com.example.coffee.domain.ranking.repository;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

public interface PopularMenuCounter {

	void record(Long orderId, Long menuId, LocalDateTime orderedAt);

	Map<Long, Long> countByMenuIds(List<Long> menuIds, LocalDateTime from, LocalDateTime to);
}
