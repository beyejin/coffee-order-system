package com.example.coffee.menu;

import java.util.List;

import com.example.coffee.common.ApiResponse;
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
