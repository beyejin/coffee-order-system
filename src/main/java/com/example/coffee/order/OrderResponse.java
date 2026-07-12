package com.example.coffee.order;

public record OrderResponse(
		Long orderId,
		Long userId,
		Long menuId,
		Long price,
		Long remainingBalance
) {
}
