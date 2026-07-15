package com.example.coffee.domain.order.service;

import java.time.Clock;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;

import com.example.coffee.domain.menu.entity.Menu;
import com.example.coffee.domain.menu.repository.MenuRepository;
import com.example.coffee.domain.order.dto.OrderResponse;
import com.example.coffee.domain.order.entity.Order;
import com.example.coffee.domain.order.event.OrderPaidEvent;
import com.example.coffee.domain.order.repository.OrderRepository;
import com.example.coffee.domain.point.entity.PointHistory;
import com.example.coffee.domain.point.repository.PointHistoryRepository;
import com.example.coffee.domain.user.entity.User;
import com.example.coffee.domain.user.repository.UserRepository;
import com.example.coffee.global.error.BusinessException;
import com.example.coffee.global.error.ErrorCode;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

	private final MenuRepository menuRepository;
	private final UserRepository userRepository;
	private final PointHistoryRepository pointHistoryRepository;
	private final OrderRepository orderRepository;
	private final ApplicationEventPublisher eventPublisher;
	private final Clock clock;

	public OrderService(
			MenuRepository menuRepository,
			UserRepository userRepository,
			PointHistoryRepository pointHistoryRepository,
			OrderRepository orderRepository,
			ApplicationEventPublisher eventPublisher,
			Clock clock
	) {
		this.menuRepository = menuRepository;
		this.userRepository = userRepository;
		this.pointHistoryRepository = pointHistoryRepository;
		this.orderRepository = orderRepository;
		this.eventPublisher = eventPublisher;
		this.clock = clock;
	}

	@Transactional
	public OrderResponse order(Long userId, Long menuId) {
		Menu menu = menuRepository.findById(menuId)
				.orElseThrow(() -> new BusinessException(ErrorCode.MENU_NOT_FOUND));
		User user = userRepository.findByIdForUpdate(userId)
				.orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));

		long price = menu.getPrice();
		user.use(price);
		pointHistoryRepository.save(PointHistory.use(user, price));
		LocalDateTime orderedAt = LocalDateTime.ofInstant(
				clock.instant().truncatedTo(ChronoUnit.MICROS),
				ZoneOffset.UTC
		);
		Order order = orderRepository.save(Order.create(user, menu, price, orderedAt));

		eventPublisher.publishEvent(new OrderPaidEvent(userId, menuId, price));

		return new OrderResponse(order.getId(), userId, menuId, price, user.getBalance());
	}
}
