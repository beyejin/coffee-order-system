package com.example.coffee.domain.user.entity;

import java.time.LocalDateTime;

import com.example.coffee.global.error.BusinessException;
import com.example.coffee.global.error.ErrorCode;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "users")
public class User {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	private Long balance;

	@Column(name = "created_at", insertable = false, updatable = false)
	private LocalDateTime createdAt;

	protected User() {
	}

	public void charge(long amount) {
		balance = Math.addExact(balance, amount);
	}

	public void use(long amount) {
		if (amount <= 0) {
			throw new IllegalArgumentException("사용 포인트는 0보다 커야 합니다.");
		}
		if (balance < amount) {
			throw new BusinessException(ErrorCode.INSUFFICIENT_POINT);
		}
		balance -= amount;
	}

	public Long getId() {
		return id;
	}

	public Long getBalance() {
		return balance;
	}
}
