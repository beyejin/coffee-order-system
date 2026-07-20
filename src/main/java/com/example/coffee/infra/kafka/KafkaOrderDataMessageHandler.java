package com.example.coffee.infra.kafka;

import com.example.coffee.domain.order.event.OrderDataMessage;

public interface KafkaOrderDataMessageHandler {

	void handle(OrderDataMessage message, KafkaMessageMetadata metadata);
}
