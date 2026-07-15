package com.example.coffee.domain.menu.controller;

import java.util.List;

import com.example.coffee.domain.menu.dto.MenuResponse;
import com.example.coffee.domain.menu.service.MenuService;
import com.example.coffee.global.response.ApiResponse;
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
