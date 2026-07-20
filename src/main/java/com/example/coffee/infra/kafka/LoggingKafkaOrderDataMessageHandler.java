package com.example.coffee.infra.kafka;

import java.lang.System.Logger;
import java.lang.System.Logger.Level;

import com.example.coffee.domain.order.event.OrderDataMessage;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name = "app.kafka.enabled", havingValue = "true")
public class LoggingKafkaOrderDataMessageHandler implements KafkaOrderDataMessageHandler {

	private static final Logger LOGGER = System.getLogger(LoggingKafkaOrderDataMessageHandler.class.getName());

	@Override
	public void handle(OrderDataMessage message, KafkaMessageMetadata metadata) {
		LOGGER.log(Level.INFO, "Kafka 주문 메시지 수신: key=%s, partition=%d, offset=%d, message=%s"
				.formatted(metadata.key(), metadata.partition(), metadata.offset(), message));
	}
}
