package com.example.coffee.menu;

import java.util.List;

import com.example.coffee.common.ApiResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/menus")
public class MenuController {

	private final MenuService menuService;

	public MenuController(MenuService menuService) {
		this.menuService = menuService;
	}

	@GetMapping
	public ApiResponse<List<MenuResponse>> getMenus() {
		return ApiResponse.success(menuService.getMenus());
	}
}
