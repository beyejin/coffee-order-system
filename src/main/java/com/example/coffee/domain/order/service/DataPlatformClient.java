package com.example.coffee.domain.order.service;

import com.example.coffee.domain.order.event.OrderDataMessage;

public interface DataPlatformClient {

	void send(OrderDataMessage message);
}
