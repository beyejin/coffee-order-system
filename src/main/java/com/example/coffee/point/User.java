package com.example.coffee.point;

import java.time.LocalDateTime;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "user")
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
		balance -= amount;
	}

	public Long getId() {
		return id;
	}

	public Long getBalance() {
		return balance;
	}
}
