package com.example.coffee.infra.kafka;

public record KafkaMessageMetadata(String key, int partition, long offset) {
}
