package com.example.coffee.domain.ranking.service;

import java.time.Clock;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.lang.System.Logger;
import java.lang.System.Logger.Level;
import java.util.Comparator;
import java.util.List;
import java.util.Map;

import com.example.coffee.domain.menu.entity.Menu;
import com.example.coffee.domain.menu.repository.MenuRepository;
import com.example.coffee.domain.order.repository.OrderRepository;
import com.example.coffee.domain.ranking.dto.PopularMenuResponse;
import com.example.coffee.domain.ranking.repository.PopularMenuCounter;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PopularMenuService {

	private static final Logger LOGGER = System.getLogger(PopularMenuService.class.getName());

	private final OrderRepository orderRepository;
	private final MenuRepository menuRepository;
	private final PopularMenuCounter popularMenuCounter;
	private final Clock clock;

	public PopularMenuService(
			OrderRepository orderRepository,
			MenuRepository menuRepository,
			PopularMenuCounter popularMenuCounter,
			Clock clock
	) {
		this.orderRepository = orderRepository;
		this.menuRepository = menuRepository;
		this.popularMenuCounter = popularMenuCounter;
		this.clock = clock;
	}

	@Transactional(readOnly = true)
	public List<PopularMenuResponse> getPopularMenus() {
		LocalDateTime to = LocalDateTime.ofInstant(
				clock.instant().truncatedTo(ChronoUnit.MICROS),
				ZoneOffset.UTC
		);
		LocalDateTime from = to.minusDays(7);

		try {
			return getFromRedis(from, to);
		} catch (RuntimeException exception) {
			LOGGER.log(
					Level.WARNING,
					"인기 메뉴 Redis 조회 실패, MySQL 집계로 fallback합니다.",
					exception
			);
			return getFromDatabase(from, to);
		}
	}

	private List<PopularMenuResponse> getFromRedis(LocalDateTime from, LocalDateTime to) {
		List<Menu> menus = menuRepository.findAllByOrderByIdAsc();
		List<Long> menuIds = menus.stream()
				.map(Menu::getId)
				.toList();
		Map<Long, Long> orderCounts = popularMenuCounter.countByMenuIds(menuIds, from, to);

		return menus.stream()
				.map(menu -> new PopularMenuResponse(
						menu.getId(),
						menu.getName(),
						orderCounts.getOrDefault(menu.getId(), 0L)
				))
				.filter(response -> response.orderCount() > 0)
				.sorted(Comparator.comparing(PopularMenuResponse::orderCount).reversed()
						.thenComparing(PopularMenuResponse::menuId))
				.limit(3)
				.toList();
	}

	private List<PopularMenuResponse> getFromDatabase(LocalDateTime from, LocalDateTime to) {
		return orderRepository.findPopularMenus(from, to).stream()
				.map(PopularMenuResponse::from)
				.toList();
	}
}
