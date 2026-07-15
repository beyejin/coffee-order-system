package com.example.coffee.domain.order.repository;

import java.time.LocalDateTime;
import java.util.List;

import com.example.coffee.domain.order.entity.Order;
import com.example.coffee.domain.ranking.repository.PopularMenuProjection;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface OrderRepository extends JpaRepository<Order, Long> {

	long countByUser_Id(Long userId);

	@Query(value = """
			SELECT m.id AS menuId, m.name AS name, COUNT(o.id) AS orderCount
			FROM orders o
			JOIN menus m ON m.id = o.menu_id
			WHERE o.created_at >= :from
			  AND o.created_at < :to
			GROUP BY m.id, m.name
			ORDER BY orderCount DESC, m.id ASC
			LIMIT 3
			""", nativeQuery = true)
	List<PopularMenuProjection> findPopularMenus(
			@Param("from") LocalDateTime from,
			@Param("to") LocalDateTime to
	);
}
