package com.example.coffee.infra.kafka;

import java.time.Duration;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import com.example.coffee.domain.order.event.OrderDataMessage;
import com.example.coffee.domain.order.service.DataPlatformClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name = "app.kafka.enabled", havingValue = "true")
public class KafkaDataPlatformClient implements DataPlatformClient {

	private final KafkaTemplate<String, OrderDataMessage> kafkaTemplate;
	private final String topic;
	private final Duration sendTimeout;

	public KafkaDataPlatformClient(
			KafkaTemplate<String, OrderDataMessage> kafkaTemplate,
			@Value("${app.kafka.topic}") String topic,
			@Value("${app.kafka.producer.timeout:10s}") Duration sendTimeout
	) {
		this.kafkaTemplate = kafkaTemplate;
		this.topic = topic;
		this.sendTimeout = sendTimeout;
	}

	@Override
	public void send(OrderDataMessage message) {
		try {
			kafkaTemplate.send(topic, String.valueOf(message.userId()), message)
					.get(sendTimeout.toMillis(), TimeUnit.MILLISECONDS);
		} catch (InterruptedException exception) {
			Thread.currentThread().interrupt();
			throw new IllegalStateException("Kafka 주문 메시지 전송이 중단됐습니다.", exception);
		} catch (ExecutionException | TimeoutException exception) {
			throw new IllegalStateException("Kafka 주문 메시지 전송에 실패했습니다.", exception);
		}
	}
}
