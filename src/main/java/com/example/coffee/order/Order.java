package com.example.coffee.order;

import java.time.LocalDateTime;

import com.example.coffee.menu.Menu;
import com.example.coffee.point.User;
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

	@Column(name = "created_at", insertable = false, updatable = false)
	private LocalDateTime createdAt;

	protected Order() {
	}

	private Order(User user, Menu menu, Long price) {
		this.user = user;
		this.menu = menu;
		this.price = price;
	}

	public static Order create(User user, Menu menu, Long price) {
		return new Order(user, menu, price);
	}

	public Long getId() {
		return id;
	}

	public Long getPrice() {
		return price;
	}
}
