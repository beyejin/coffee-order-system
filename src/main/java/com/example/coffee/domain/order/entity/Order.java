package com.example.coffee.domain.order.entity;

import java.time.LocalDateTime;

import com.example.coffee.domain.menu.entity.Menu;
import com.example.coffee.domain.user.entity.User;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class Order {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	@JoinColumn(name = "user_id", nullable = false)
	private User user;

	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	@JoinColumn(name = "menu_id", nullable = false)
	private Menu menu;

	private Long price;

	@Column(name = "created_at", nullable = false, updatable = false)
	private LocalDateTime createdAt;

	protected Order() {
	}

	private Order(User user, Menu menu, Long price, LocalDateTime createdAt) {
		this.user = user;
		this.menu = menu;
		this.price = price;
		this.createdAt = createdAt;
	}

	public static Order create(User user, Menu menu, Long price, LocalDateTime createdAt) {
		return new Order(user, menu, price, createdAt);
	}

	public Long getId() {
		return id;
	}

	public Long getPrice() {
		return price;
	}
}
