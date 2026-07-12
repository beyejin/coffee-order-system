package com.example.coffee.domain.menu.repository;

import java.util.List;

import com.example.coffee.domain.menu.entity.Menu;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MenuRepository extends JpaRepository<Menu, Long> {

	List<Menu> findAllByOrderByIdAsc();
}
