package com.example.coffee.order;

public record OrderPaidEvent(Long userId, Long menuId, Long paymentAmount) {
}
