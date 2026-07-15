package com.example.coffee.domain.menu.service;

import java.util.List;

import com.example.coffee.domain.menu.dto.MenuResponse;
import com.example.coffee.domain.menu.repository.MenuRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MenuService {

	private final MenuRepository menuRepository;

	public MenuService(MenuRepository menuRepository) {
		this.menuRepository = menuRepository;
	}

	@Transactional(readOnly = true)
	public List<MenuResponse> getMenus() {
		return menuRepository.findAllByOrderByIdAsc().stream()
				.map(MenuResponse::from)
				.toList();
	}
}
