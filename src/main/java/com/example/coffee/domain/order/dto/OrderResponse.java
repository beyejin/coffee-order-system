package com.example.coffee.domain.order.dto;

public record OrderResponse(
		Long orderId,
		Long userId,
		Long menuId,
		Long price,
		Long remainingBalance
) {
}
