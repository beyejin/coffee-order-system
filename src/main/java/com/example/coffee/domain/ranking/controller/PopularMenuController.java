package com.example.coffee.domain.ranking.controller;

import java.util.List;

import com.example.coffee.domain.ranking.dto.PopularMenuResponse;
import com.example.coffee.domain.ranking.service.PopularMenuService;
import com.example.coffee.global.response.ApiResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/menus/popular")
public class PopularMenuController {

	private final PopularMenuService popularMenuService;

	public PopularMenuController(PopularMenuService popularMenuService) {
		this.popularMenuService = popularMenuService;
	}

	@GetMapping
	public ApiResponse<List<PopularMenuResponse>> getPopularMenus() {
		return ApiResponse.success(popularMenuService.getPopularMenus());
	}
}
