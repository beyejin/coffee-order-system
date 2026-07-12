package com.example.coffee.order;

import com.example.coffee.common.BusinessException;
import com.example.coffee.common.ErrorCode;
import com.example.coffee.menu.Menu;
import com.example.coffee.menu.MenuRepository;
import com.example.coffee.point.PointHistory;
import com.example.coffee.point.PointHistoryRepository;
import com.example.coffee.point.User;
import com.example.coffee.point.UserRepository;
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

	public OrderService(
			MenuRepository menuRepository,
			UserRepository userRepository,
			PointHistoryRepository pointHistoryRepository,
			OrderRepository orderRepository,
			ApplicationEventPublisher eventPublisher
	) {
		this.menuRepository = menuRepository;
		this.userRepository = userRepository;
		this.pointHistoryRepository = pointHistoryRepository;
		this.orderRepository = orderRepository;
		this.eventPublisher = eventPublisher;
	}

	@Transactional
	public OrderResponse order(Long userId, Long menuId) {
		if (userId == null || menuId == null) {
			throw new BusinessException(ErrorCode.VALIDATION_ERROR);
		}

		Menu menu = menuRepository.findById(menuId)
				.orElseThrow(() -> new BusinessException(ErrorCode.MENU_NOT_FOUND));
		User user = userRepository.findByIdForUpdate(userId)
				.orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));

		long price = menu.getPrice();
		if (user.getBalance() < price) {
			throw new BusinessException(ErrorCode.INSUFFICIENT_POINT);
		}

		user.use(price);
		pointHistoryRepository.save(PointHistory.use(user, price));
		Order order = orderRepository.save(Order.create(user, menu, price));

		eventPublisher.publishEvent(new OrderPaidEvent(userId, menuId, price));

		return new OrderResponse(order.getId(), userId, menuId, price, user.getBalance());
	}
}
