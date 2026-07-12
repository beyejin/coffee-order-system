package com.example.coffee.order;

import java.lang.System.Logger;
import java.lang.System.Logger.Level;

import org.springframework.stereotype.Component;

@Component
public class MockDataPlatformClient implements DataPlatformClient {

	private static final Logger LOGGER = System.getLogger(MockDataPlatformClient.class.getName());

	@Override
	public void send(OrderDataMessage message) {
		LOGGER.log(Level.INFO, "주문 데이터 전송: {0}", message);
	}
}
