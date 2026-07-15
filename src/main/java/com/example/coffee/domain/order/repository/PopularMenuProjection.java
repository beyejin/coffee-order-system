package com.example.coffee.domain.order.repository;

public interface PopularMenuProjection {

	Long getMenuId();

	String getName();

	Long getOrderCount();
}
