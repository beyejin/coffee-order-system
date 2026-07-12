package com.example.coffee.order;

public record OrderDataMessage(Long userId, Long menuId, Long paymentAmount) {
}
