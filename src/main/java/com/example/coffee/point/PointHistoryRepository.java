package com.example.coffee.point;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PointHistoryRepository extends JpaRepository<PointHistory, Long> {

	List<PointHistory> findAllByUser_IdOrderByIdAsc(Long userId);

	long countByUser_Id(Long userId);
}
