package com.example.coffee.domain.ranking.service;

import java.time.Clock;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.List;

import com.example.coffee.domain.order.repository.OrderRepository;
import com.example.coffee.domain.ranking.dto.PopularMenuResponse;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PopularMenuService {

	private final OrderRepository orderRepository;
	private final Clock clock;

	public PopularMenuService(OrderRepository orderRepository, Clock clock) {
		this.orderRepository = orderRepository;
		this.clock = clock;
	}

	@Transactional(readOnly = true)
	public List<PopularMenuResponse> getPopularMenus() {
		LocalDateTime to = LocalDateTime.ofInstant(
				clock.instant().truncatedTo(ChronoUnit.MICROS),
				ZoneOffset.UTC
		);
		LocalDateTime from = to.minusDays(7);

		return orderRepository.findPopularMenus(from, to).stream()
				.map(PopularMenuResponse::from)
				.toList();
	}
}
