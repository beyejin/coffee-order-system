package com.example.coffee.domain.ranking.dto;

import com.example.coffee.domain.order.repository.PopularMenuProjection;

public record PopularMenuResponse(Long menuId, String name, Long orderCount) {

	public static PopularMenuResponse from(PopularMenuProjection projection) {
		return new PopularMenuResponse(
				projection.getMenuId(),
				projection.getName(),
				projection.getOrderCount()
		);
	}
}
