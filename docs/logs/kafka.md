# kafka — 로그

## Plan — 2026-07-20

- 목적: 주문 결제 커밋 이후 `orders.paid` topic으로 JSON 이벤트를 발행하고 Consumer Group 수신을 확인한다.
- Producer: 기존 `DataPlatformClient` 포트를 유지하고 `KAFKA_ENABLED=true`일 때만 Kafka 구현을 선택한다. key는 `userId`다.
- Consumer: `coffee-order-data-platform` Group, 최소 3 Partition, Compose concurrency 3으로 Partition 병렬 처리와 partition·offset을 관찰한다.
- 트랜잭션: 주문·잔액·이력 DB 커밋과 Kafka 발행을 분리한다. 커밋 전 예외에서는 메시지를 발행하지 않고, broker 장애는 성공한 주문을 롤백하지 않는다.
- 비목표: Outbox, DLT, schema registry, Kafka Streams, 주문 API·DB schema 변경.
- 검증: 실제 Kafka Testcontainers 통합 테스트, Compose config, 전체 Gradle 회귀 테스트, Kafka UI 실행 경로.

## Attempt 1 — 2026-07-20 ✅ PASS

- 설계 문서와 하네스 manifest를 먼저 갱신했다.
- 이슈 `#11`과 `feature/11-kafka-order-events` worktree를 사용한다.
- `./gradlew cleanTest test --tests com.example.coffee.infra.kafka.KafkaIntegrationTest --console plain` 성공. 3개 테스트가 통과했다.
- Kafka 통합 테스트: 주문 커밋 후 `OrderDataMessage[userId=1, menuId=1, paymentAmount=4500]`를 Consumer가 수신했고 key `1`, partition 범위 `0..2`, offset을 확인했다.
- Partition 검증: 동일 `userId` key 3건의 partition·offset 순서가 유지됐고, 서로 다른 key 6건이 2개 이상 Partition으로 분산됐다.
- 롤백 검증: 주문 INSERT CHECK 제약으로 트랜잭션을 실패시켰을 때 잔액은 10,000P로 복원되고 Consumer 메시지는 0건이었다.
- `./gradlew clean test --console plain` 성공. Kafka 3개를 포함한 전체 44개 MySQL·Redis·주문·동시성 회귀 테스트가 통과했다.
- Compose 검증: `docker compose -p coffee-kafka-verify-20260720-1 up -d --build --wait` 성공. 포트 충돌 후 검증 전용 포트 `13326/16379/12992/18081/18082`로 재시도했다.
- Kafka CLI: `orders.paid`는 3 partitions, Consumer Group `coffee-order-data-platform`은 주문 수신 후 lag 0을 보였다.
- 실기동 API: gateway를 통해 포인트 충전 후 주문 응답 `remainingBalance=11,000`, MySQL `orders=2`, Kafka payload `{"userId":1,"menuId":1,"paymentAmount":4500}`를 확인했다.
- Kafka UI: `http://localhost:18081/api/clusters`가 `coffee` cluster `online`을 반환했다. 검증 컨테이너·볼륨은 완료 후 `down -v --remove-orphans`로 정리한다.
- 배운 점: `AFTER_COMMIT` 비동기 listener와 Kafka Producer acknowledgement를 결합하면 DB 정합성과 외부 broker 장애 격리를 동시에 확보하면서, key·Partition·Consumer Group을 운영 화면에서 관찰할 수 있다.
