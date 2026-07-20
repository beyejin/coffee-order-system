# 정책 (Policy) — 공유 비즈니스 규칙 / 진실의 원천

여러 기능이 함께 의존하는 도메인 불변식과, 아직 결정되지 않은 사항을 어떻게 다룰지에 대한 규칙이다. 명세(테이블 구조는 `docs/table-spec.md`, API 형태는 `docs/api-spec.md`)와는 다르게, "여러 기능에 걸쳐 항상 참이어야 하는 규칙"만 다룬다.

## 도메인 불변식 — 절대 깨지 않는다

- `Order`에 `status` 컬럼을 추가하지 않는다 — 실패한 주문은 레코드 자체를 만들지 않는 것이 설계 전제다 (`존재하는 주문 = 성공한 주문`).
- `User.balance`와 `PointHistory` INSERT는 항상 같은 트랜잭션에서 함께 갱신한다.
- `User`는 포인트 사용 시 잔액 부족을 직접 거부해 어떤 호출 경로에서도 잔액이 음수가 되지 않게 한다.
- `Order.price`는 주문 시점 스냅샷이다 — `Menu` 조인으로 대체하지 않는다.
- 주문은 요청 1건당 메뉴 1개다 — 장바구니(여러 메뉴) 구조로 확장하지 않는다.
- 주문 시각과 인기 메뉴 조회 시각은 같은 UTC `Clock`에서 microsecond 정밀도로 캡처한다. 인기 메뉴는 `to`를 한 번 고정한 `[to - 7일, to)` 주문만 집계하고, 동률이면 메뉴 ID 오름차순으로 정렬한다.
- Kafka를 활성화한 경우에도 주문·잔액·이력 DB 트랜잭션과 Kafka 발행은 분리한다. DB 커밋 전에는 Kafka를 발행하지 않으며, broker 장애는 성공한 주문을 롤백하지 않는다.
- Kafka `orders.paid` topic은 `userId`를 message key로 사용해 동일 사용자 이벤트의 순서 보장 단위를 유지한다. Consumer는 동일 Consumer Group의 offset을 수동 커밋하고 실패 메시지를 재처리할 수 있어야 한다.

이 규칙들의 배경과 근거는 `docs/strategy.md` 2장 참고.

## 전략 상태 — 선택과 미확정을 구분한다

`docs/strategy.md` 5장의 전략 상태는 다음과 같다.

1. 포인트 차감 동시성: **MySQL 비관적 락 선택**
2. 결제 트랜잭션 ↔ 데이터 수집 플랫폼 전송: **`AFTER_COMMIT` 비동기 전송 선택**
3. 인기 메뉴 집계: **MySQL `GROUP BY` 정본 + Redis ZSET read model 선택**
4. 주문 이벤트 메시징: **선택적으로 Kafka Producer/Consumer Group 연동**

외부 Mock/Kafka 전송과 Redis read model 갱신은 결제 트랜잭션 커밋 후 실행한다. 외부 전송과 Redis 갱신 실패는 성공한 주문·잔액·이력을 롤백하지 않는다. 인기 메뉴 API는 Redis 오류 시 MySQL 집계로 fallback하며, MySQL이 주문·인기 메뉴의 정확성 기준이다. Kafka는 `acks=all`, idempotence, 재시도와 Consumer Group offset 재처리를 사용하지만 영속 Outbox는 아니므로 프로세스 종료 직후의 완전한 전달 보장은 범위에 포함하지 않는다. 전략을 바꿀 때는 `strategy.md`와 `api-spec.md`를 먼저 갱신하고 구현한다.

## 검증 정책

테스트는 Testcontainers로 실제 MySQL 컨테이너를 띄워 검증한다. Kafka 연동 테스트도 실제 Kafka broker 컨테이너를 사용한다. H2나 가짜 broker로 대체하지 않는다 — 락·트랜잭션·Partition·Consumer Group 동작을 검증할 수 없기 때문이다.
