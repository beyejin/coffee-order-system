package com.example.coffee.domain.ranking.repository;

public interface PopularMenuProjection {

	Long getMenuId();

	String getName();

	Long getOrderCount();
}
