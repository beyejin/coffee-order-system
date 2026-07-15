package com.example.coffee.domain.point.controller;

import com.example.coffee.domain.point.dto.ChargePointRequest;
import com.example.coffee.domain.point.dto.ChargePointResponse;
import com.example.coffee.domain.point.service.PointService;
import com.example.coffee.global.response.ApiResponse;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/users/{userId}/points")
public class PointController {

	private final PointService pointService;

	public PointController(PointService pointService) {
		this.pointService = pointService;
	}

	@PostMapping("/charge")
	public ApiResponse<ChargePointResponse> charge(
			@PathVariable Long userId,
			@Valid @RequestBody ChargePointRequest request
	) {
		return ApiResponse.success(pointService.charge(userId, request.amount()));
	}
}
