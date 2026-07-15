package com.example.coffee.global.config;

import org.springframework.boot.jackson.autoconfigure.JsonMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.cfg.CoercionAction;
import tools.jackson.databind.cfg.CoercionInputShape;
import tools.jackson.databind.type.LogicalType;

@Configuration
public class JacksonConfiguration {

	@Bean
	JsonMapperBuilderCustomizer rejectFloatingPointForInteger() {
		return builder -> builder.withCoercionConfig(
				LogicalType.Integer,
				config -> config.setCoercion(CoercionInputShape.Float, CoercionAction.Fail)
		);
	}
}
