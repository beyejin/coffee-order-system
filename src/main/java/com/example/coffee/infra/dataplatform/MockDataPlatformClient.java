package com.example.coffee.infra.dataplatform;

import java.lang.System.Logger;
import java.lang.System.Logger.Level;

import com.example.coffee.domain.order.event.OrderDataMessage;
import com.example.coffee.domain.order.service.DataPlatformClient;
import org.springframework.stereotype.Component;

@Component
public class MockDataPlatformClient implements DataPlatformClient {

	private static final Logger LOGGER = System.getLogger(MockDataPlatformClient.class.getName());

	@Override
	public void send(OrderDataMessage message) {
		LOGGER.log(Level.INFO, "주문 데이터 전송: {0}", message);
	}
}
