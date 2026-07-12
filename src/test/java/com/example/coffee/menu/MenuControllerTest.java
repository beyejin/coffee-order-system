package com.example.coffee.menu;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.hamcrest.Matchers.nullValue;

import com.example.coffee.TestcontainersConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@Import(TestcontainersConfiguration.class)
class MenuControllerTest {

	@Autowired
	private MockMvc mockMvc;

	@Test
	void 메뉴_목록을_ID_오름차순으로_조회한다() throws Exception {
		mockMvc.perform(get("/menus"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.success").value(true))
				.andExpect(jsonPath("$.error").value(nullValue()))
				.andExpect(jsonPath("$.data.length()").value(3))
				.andExpect(jsonPath("$.data[0].menuId").value(1))
				.andExpect(jsonPath("$.data[0].name").value("아메리카노"))
				.andExpect(jsonPath("$.data[0].price").value(4500))
				.andExpect(jsonPath("$.data[1].menuId").value(2))
				.andExpect(jsonPath("$.data[1].name").value("카페라떼"))
				.andExpect(jsonPath("$.data[1].price").value(5000))
				.andExpect(jsonPath("$.data[2].menuId").value(3))
				.andExpect(jsonPath("$.data[2].name").value("카페모카"))
				.andExpect(jsonPath("$.data[2].price").value(5500));
	}
}
