package com.example.coffee.infra.kafka;

import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.config.TopicBuilder;
import org.springframework.kafka.listener.CommonErrorHandler;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration(proxyBeanMethods = false)
@EnableKafka
@ConditionalOnProperty(name = "app.kafka.enabled", havingValue = "true")
public class KafkaConfiguration {

	@Bean
	NewTopic orderPaidTopic(
			@Value("${app.kafka.topic}") String topic,
			@Value("${app.kafka.topic-partitions:3}") int partitions
	) {
		return TopicBuilder.name(topic)
				.partitions(partitions)
				.replicas(1)
				.build();
	}

	@Bean
	CommonErrorHandler kafkaErrorHandler() {
		return new DefaultErrorHandler(new FixedBackOff(1000L, 2L));
	}
}
