package com.example.coffee.infra.kafka;

import com.example.coffee.domain.order.event.OrderDataMessage;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name = "app.kafka.enabled", havingValue = "true")
public class KafkaOrderDataConsumer {

	private final KafkaOrderDataMessageHandler messageHandler;

	public KafkaOrderDataConsumer(KafkaOrderDataMessageHandler messageHandler) {
		this.messageHandler = messageHandler;
	}

	@KafkaListener(
			topics = "${app.kafka.topic}",
			groupId = "${app.kafka.consumer.group-id}",
			concurrency = "${app.kafka.consumer.concurrency:1}"
	)
	public void consume(ConsumerRecord<String, OrderDataMessage> record, Acknowledgment acknowledgment) {
		messageHandler.handle(
				record.value(),
				new KafkaMessageMetadata(record.key(), record.partition(), record.offset())
		);
		acknowledgment.acknowledge();
	}
}
