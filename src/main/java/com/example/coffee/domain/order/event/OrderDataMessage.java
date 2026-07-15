package com.example.coffee.domain.order.event;

public record OrderDataMessage(Long userId, Long menuId, Long paymentAmount) {
}
