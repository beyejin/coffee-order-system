package com.example.coffee.global.error;

import org.springframework.http.HttpStatus;

public enum ErrorCode {

	MENU_NOT_FOUND(HttpStatus.NOT_FOUND, "메뉴를 찾을 수 없습니다."),
	USER_NOT_FOUND(HttpStatus.NOT_FOUND, "사용자를 찾을 수 없습니다."),
	INSUFFICIENT_POINT(HttpStatus.CONFLICT, "포인트가 부족합니다."),
	INVALID_CHARGE_AMOUNT(HttpStatus.BAD_REQUEST, "충전 금액은 0보다 커야 합니다."),
	POINT_BALANCE_OVERFLOW(HttpStatus.CONFLICT, "포인트 잔액이 허용 범위를 초과합니다."),
	VALIDATION_ERROR(HttpStatus.BAD_REQUEST, "요청 형식이 올바르지 않습니다.");

	private final HttpStatus status;
	private final String message;

	ErrorCode(HttpStatus status, String message) {
		this.status = status;
		this.message = message;
	}

	public HttpStatus getStatus() {
		return status;
	}

	public String getMessage() {
		return message;
	}
}
