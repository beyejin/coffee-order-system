package com.example.coffee.domain.order.event;

import java.time.LocalDateTime;

public record OrderPaidEvent(
		Long orderId,
		Long userId,
		Long menuId,
		Long paymentAmount,
		LocalDateTime orderedAt
) {
}
