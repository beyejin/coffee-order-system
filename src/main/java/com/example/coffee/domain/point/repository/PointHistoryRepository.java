package com.example.coffee.domain.point.repository;

import java.util.List;

import com.example.coffee.domain.point.entity.PointHistory;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PointHistoryRepository extends JpaRepository<PointHistory, Long> {

	List<PointHistory> findAllByUser_IdOrderByIdAsc(Long userId);

	long countByUser_Id(Long userId);
}
