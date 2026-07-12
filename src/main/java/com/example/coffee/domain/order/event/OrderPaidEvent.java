package com.example.coffee.domain.order.event;

public record OrderPaidEvent(Long userId, Long menuId, Long paymentAmount) {
}
