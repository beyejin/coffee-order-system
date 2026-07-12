package com.example.coffee.common;

public record ApiResponse<T>(boolean success, T data, ApiError error) {

	public static <T> ApiResponse<T> success(T data) {
		return new ApiResponse<>(true, data, null);
	}
}
