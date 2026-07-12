package com.example.coffee.menu;

public record PopularMenuResponse(Long menuId, String name, Long orderCount) {

	static PopularMenuResponse from(PopularMenuProjection projection) {
		return new PopularMenuResponse(
				projection.getMenuId(),
				projection.getName(),
				projection.getOrderCount()
		);
	}
}
