package com.example.coffee.global.error;

import com.example.coffee.global.response.ApiError;
import com.example.coffee.global.response.ApiResponse;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class GlobalExceptionHandler {

	@ExceptionHandler(BusinessException.class)
	public ResponseEntity<ApiResponse<Void>> handleBusinessException(BusinessException exception) {
		ErrorCode errorCode = exception.getErrorCode();
		ApiError error = new ApiError(errorCode.name(), errorCode.getMessage());

		return ResponseEntity.status(errorCode.getStatus())
				.body(ApiResponse.failure(error));
	}

	@ExceptionHandler(HttpMessageNotReadableException.class)
	public ResponseEntity<ApiResponse<Void>> handleHttpMessageNotReadable() {
		return validationErrorResponse();
	}

	@ExceptionHandler(MethodArgumentTypeMismatchException.class)
	public ResponseEntity<ApiResponse<Void>> handleMethodArgumentTypeMismatch() {
		return validationErrorResponse();
	}

	private ResponseEntity<ApiResponse<Void>> validationErrorResponse() {
		ErrorCode errorCode = ErrorCode.VALIDATION_ERROR;
		ApiError error = new ApiError(errorCode.name(), errorCode.getMessage());

		return ResponseEntity.status(errorCode.getStatus())
				.body(ApiResponse.failure(error));
	}
}
