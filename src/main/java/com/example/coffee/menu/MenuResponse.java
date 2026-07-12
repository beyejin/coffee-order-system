package com.example.coffee.menu;

public record MenuResponse(Long menuId, String name, Long price) {

	static MenuResponse from(Menu menu) {
		return new MenuResponse(menu.getId(), menu.getName(), menu.getPrice());
	}
}
