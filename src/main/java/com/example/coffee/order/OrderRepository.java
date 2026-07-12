package com.example.coffee.order;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<Order, Long> {

	long countByUser_Id(Long userId);
}
