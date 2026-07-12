package com.example.coffee.point;

import java.time.LocalDateTime;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "point_history")
public class PointHistory {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	@JoinColumn(name = "user_id", nullable = false)
	private User user;

	private Long amount;

	@Enumerated(EnumType.STRING)
	private PointHistoryType type;

	@Column(name = "created_at", insertable = false, updatable = false)
	private LocalDateTime createdAt;

	protected PointHistory() {
	}

	private PointHistory(User user, Long amount, PointHistoryType type) {
		this.user = user;
		this.amount = amount;
		this.type = type;
	}

	public static PointHistory charge(User user, Long amount) {
		return new PointHistory(user, amount, PointHistoryType.CHARGE);
	}

	public Long getAmount() {
		return amount;
	}

	public PointHistoryType getType() {
		return type;
	}
}
