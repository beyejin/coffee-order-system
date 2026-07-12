package com.example.coffee.domain.order.controller;

import com.example.coffee.domain.order.dto.OrderRequest;
import com.example.coffee.domain.order.dto.OrderResponse;
import com.example.coffee.domain.order.service.OrderService;
import com.example.coffee.global.response.ApiResponse;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

	private final OrderService orderService;

	public OrderController(OrderService orderService) {
		this.orderService = orderService;
	}

	@PostMapping
	public ApiResponse<OrderResponse> order(@RequestBody OrderRequest request) {
		return ApiResponse.success(orderService.order(request.userId(), request.menuId()));
	}
}
