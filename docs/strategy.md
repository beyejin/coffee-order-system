# 문제 해결 전략

## 1. 과제 범위 및 목표

이 과제는 정답이 정해진 문제가 아니라 "왜 이렇게 설계했는가"를 설명하고 설득하는 것이 핵심이라고 이해했습니다.
따라서 필수 요구사항 4개(메뉴 조회, 포인트 충전, 주문/결제, 인기 메뉴 조회)뿐 아니라 도전 요구사항(다중 인스턴스, 동시성, 데이터 일관성, 테스트)까지 정공법으로 구현하는 것을 목표로 합니다.

기술 스택은 **Spring Boot / Java / MySQL / Redis / Kafka**를 사용합니다. MySQL은 주문·포인트의 정본으로 유지하고, Redis는 인기 메뉴 조회 read model, Kafka는 커밋된 주문 이벤트의 비동기 전달과 Consumer Group·Partition 실습 경계로 한정합니다.

## 2. 도메인 설계 의도

### 2.1 주문 단위 — 메뉴 1개 / 요청
요구사항 문구("메뉴 ID를 입력받아 주문한다")가 단수형인 점을 근거로, 한 번의 주문 요청은 메뉴 1개에 대해서만 처리하도록 설계했습니다. 장바구니형(여러 메뉴 동시 주문)은 요구사항에 없는 확장이라 배제했습니다. 이 결정 덕분에 `Order` 테이블이 `OrderItem` 없이 단일 레코드로 단순해집니다.

### 2.2 사용자 — 인증 없는 식별값
요구사항에 회원가입/로그인 절차가 명시되어 있지 않으므로, `User` 엔티티는 존재하되 별도 인증 없이 `userId`를 요청 파라미터로 받아 조회/검증하는 방식으로 설계했습니다. 포인트 충전/차감의 동시성·일관성이라는 과제의 본질에 집중하기 위한 범위 축소입니다.

### 2.3 포인트 — 스냅샷 + 이력 분리
포인트 잔액은 `User.balance` 컬럼에 스냅샷으로 저장하고, 모든 충전/차감 이벤트는 `PointHistory`에 별도로 기록합니다.
- **이유**: 매 조회마다 이력을 SUM하면 이력이 쌓일수록 조회가 느려지지만, 스냅샷만 두면 "왜 잔액이 이렇게 됐는지" 감사(audit)가 불가능합니다. 두 값을 분리해 조회 성능과 추적 가능성을 모두 확보했습니다.
- `balance`와 `PointHistory` 레코드는 **반드시 같은 트랜잭션 안에서 함께 갱신**하여 정합성을 보장합니다.

### 2.4 주문 가격 — 스냅샷 저장
`Order.price`는 주문 시점의 메뉴 가격을 스냅샷으로 저장합니다. 메뉴 가격이 추후 변경되어도 과거 주문 금액이 영향받지 않도록 하기 위함이며, 실제 결제/회계 시스템의 표준 방식이기도 합니다.

### 2.5 주문 실패 처리 — 실패 시 레코드 없음
포인트 부족, 존재하지 않는 메뉴 등 검증에 실패한 주문은 `Order` 테이블에 아무 흔적도 남기지 않습니다(검증 통과 후에만 INSERT). 이에 따라 `Order`에 `status` 컬럼이 필요 없으며, "존재하는 주문 = 성공한 주문"이라는 단순한 불변식이 성립해 인기 메뉴 집계 로직도 단순해집니다.

### 2.6 메뉴 데이터 — 사전 시딩
필수 API 목록에 메뉴 등록/수정 API가 없으므로, 메뉴 데이터는 DB 마이그레이션(Flyway) 스크립트로 서버 기동 시 미리 등록합니다. 요구사항 범위를 벗어나는 CRUD API를 임의로 추가하지 않기 위한 선택입니다.

### 2.7 포인트 충전 금액 제약
0보다 큰 정수만 허용하며 별도의 업무상 충전 상한선은 두지 않습니다. 다만 저장 타입인 Java `long`/MySQL `BIGINT`의 표현 범위를 넘는 누적 결과는 `POINT_BALANCE_OVERFLOW`로 거부해 잔액이 음수로 뒤집히는 것을 막습니다.

## 3. API 설계

- 모든 응답은 공통 응답 래퍼(`{success, data, error{code, message}}`)로 통일합니다.
- 업무 에러는 `ErrorCode` enum(예: `INSUFFICIENT_POINT`, `MENU_NOT_FOUND`)으로 정의하고, HTTP 상태 코드와 함께 반환합니다. 클라이언트가 에러 종류를 문자열 파싱 없이 분기할 수 있도록 하기 위함입니다.
- API 명세는 springdoc-openapi(Swagger UI)로 코드에서 자동 생성하여, 문서와 코드가 어긋나지 않도록 합니다.

## 4. 도전 요구사항: 다수 서버·다수 인스턴스

Docker Compose로 동일 애플리케이션 이미지의 `app1`, `app2`와 nginx gateway를 실제로 실행합니다. 두 앱은 세션·로컬 캐시를 사용하지 않고 하나의 MySQL과 Redis를 공유하므로 어느 인스턴스로 요청이 가더라도 같은 잔액·주문·인기 read model을 봅니다. MySQL·Redis·JDBC session·두 JVM은 모두 UTC 기준으로 동작합니다.

검증에서 nginx는 충전 요청을 `app2`, 주문 요청을 `app1`, 인기 메뉴 조회를 다시 `app2`로 전달합니다. 공유 MySQL에는 최종 잔액·주문·포인트 이력이 저장되고, 공유 Redis에도 주문 이벤트가 반영되어 인기 메뉴 결과를 반환합니다. 이는 로컬 메모리가 아니라 공유 MySQL이 정본이고, Redis는 여러 인스턴스가 함께 읽는 read model임을 보여줍니다.

nginx 1.27의 Docker DNS resolver(`127.0.0.11`)와 upstream `resolve`를 사용해 앱 컨테이너가 재생성되어 IP가 바뀌어도 설정 재시작 없이 다시 조회합니다. nginx 자체 HTTP health check를 두어 Compose `--wait`가 gateway까지 준비된 뒤 완료됩니다. `X-Upstream-Addr` 응답 헤더는 로컬 개발 검증용이며, smoke 스크립트가 두 upstream 사용 여부를 자동 판정합니다.

## 5. 도전 요구사항: 동시성 / 데이터 일관성 / 실시간 전송

아래 세 가지는 후보안을 한 번에 채택하지 않고, 가장 단순한 구현으로 문제를 재현한 뒤 테스트 결과를 근거로 최종안을 확정합니다. 현재 단계와 최종 제출 전략을 구분하여 구현되지 않은 내용을 완료된 것처럼 설명하지 않습니다.

### 5.1 포인트 차감 동시성 제어

| 후보안 | 장점 | 단점 |
|---|---|---|
| MySQL 비관적 락 (`SELECT ... FOR UPDATE`) | 단일 DB를 공유하는 구조라 인스턴스 수와 무관하게 정합성 보장. 추가 인프라 불필요, 구현이 명확 | 락 대기 시간 동안 처리량 저하 가능 |
| 분산 락 (Redis + Redisson) | DB 락보다 성능이 좋고 다중 서버 환경의 정석으로 언급됨 | Redis 인프라 추가, 락 해제 실패·만료 시간 등 고려사항 증가 |
| 낙관적 락(버전 컬럼) + 재시도 | 락 대기 없이 충돌 감지 후 재시도 | 동시 요청이 많을 경우 재시도 빈도 증가로 비효율적일 수 있음 |

**선택**: MySQL 비관적 락. 단일 공유 DB 구조에서 추가 인프라 없이 다중 인스턴스에도 적용되며, 실제 MySQL 동시성 테스트로 동작을 검증할 수 있기 때문입니다. Redis 분산 락은 현재 요구사항에 필요한 근거가 없으므로 구현하지 않습니다.

### 5.2 결제 트랜잭션 ↔ 데이터 수집 플랫폼 실시간 전송

| 후보안 | 장점 | 단점 |
|---|---|---|
| 트랜잭션 내 동기 호출 | 구현이 가장 간단 | 외부 장애/지연이 결제 자체를 막을 수 있음 (치명적 결합) |
| `@TransactionalEventListener(AFTER_COMMIT)` + 비동기 호출 | DB 커밋이 먼저 보장된 후 전송하므로 외부 장애가 결제를 막지 않음 | 전송 실패 시 재시도·유실 처리를 별도로 설계해야 함 |
| Outbox 패턴 | 가장 견고하며 전송 실패에도 유실 없음 | 구현 복잡도가 가장 높음 (outbox 테이블 + 발행기 필요) |

**선택**: `@TransactionalEventListener(AFTER_COMMIT)` + `@Async`. 주문·차감·이력 저장이 커밋된 뒤 기존 Mock 데이터 플랫폼 또는 선택된 Kafka Producer로 전송해 외부 지연이나 장애가 결제 응답과 DB 커밋을 되돌리지 않게 합니다. `KAFKA_ENABLED` 기본값은 `false`라 MySQL 단독 개발 흐름은 유지합니다.

**한계**: 메모리 이벤트라 애플리케이션이 커밋 직후 종료되면 재시도할 영속 기록이 없어 유실될 수 있습니다. Kafka Producer는 `acks=all`, idempotence, 재시도와 broker acknowledgement를 사용하지만 Outbox가 아니므로 이 한계를 제거하지는 않습니다. 이번 범위에서는 결제와 외부 장애의 분리, Kafka Consumer Group과 Partition 관찰을 우선하며 Outbox·DLT는 추가하지 않습니다.

### 5.3 Kafka Producer/Consumer 병렬 처리

Kafka를 활성화하면 `OrderDataPlatformEventListener`가 `OrderDataMessage`를 `orders.paid` topic으로 발행합니다. message key는 `userId`로 고정해 같은 사용자의 메시지가 같은 Partition 순서 보장 단위에 들어가도록 하고, topic은 3개 Partition으로 생성합니다.

Consumer는 `coffee-order-data-platform` Consumer Group으로 구독하고 `enable-auto-commit=false`, manual ack mode를 사용합니다. handler 처리가 성공한 뒤 `Acknowledgment.acknowledge()`를 호출해 offset을 커밋하며, 실패 메시지는 `DefaultErrorHandler`의 짧은 재시도로 다시 처리합니다. Consumer concurrency는 Compose에서 3으로 설정해 Partition 수와 같은 수의 소비 스레드를 관찰할 수 있습니다. 재시도 한도를 넘긴 메시지를 DLT로 보내는 동작은 이번 범위에 포함하지 않습니다.

Producer/Consumer 통합 테스트는 MySQL과 별도로 실제 Kafka Testcontainers를 사용해 주문 커밋 후 payload·key·Partition·offset을 확인합니다. Kafka UI는 topic·message·Partition·Consumer Group의 운영 관찰 표면으로만 사용합니다.

### 5.4 인기 메뉴(최근 7일) 집계 방식

| 후보안 | 장점 | 단점 |
|---|---|---|
| 조회 시점 실시간 `GROUP BY` | 항상 정확한 값 보장, 구현 단순 | 데이터가 많아지면 조회 성능 저하 가능 |
| 스케줄러 기반 주기적 집계 + 캐싱 | 조회가 빠름 | "실시간 정확성"과 트레이드오프(주기 간격만큼 지연) |
| 주문 시마다 카운터 증가 (Redis ZSET 등) | 조회 성능이 가장 좋음 | 7일 시간 경계와 카운터 정합성 구현이 복잡 |
| 주문별 시각을 Redis ZSET score로 저장하고 `ZCOUNT` | 최근 7일의 microsecond 경계를 정확히 표현하고 메뉴별 count 조회 가능 | 메뉴별 ZSET과 주문 이벤트 read model 운영 필요 |

**선택**: MySQL `GROUP BY`를 정확성의 fallback으로 유지하면서, Redis ZSET을 인기 메뉴 read model로 추가한다. `popular:menus:{menuId}:orders`의 member는 주문 ID이고 score는 주문 시각의 UTC epoch microsecond다. 조회 시 각 메뉴에 대해 `ZCOUNT(from, to - 1 microsecond)`를 수행해 `[to - 7일, to)`를 구현한다. 단순 일자별 `ZINCRBY`는 시작·종료일의 부분 구간을 정확히 표현하지 못하므로 선택하지 않았다.

주문 저장과 인기 메뉴 조회는 동일한 UTC `Clock`을 사용하고 시각을 MySQL `DATETIME(6)`과 같은 microsecond 정밀도로 절삭합니다. 주문 트랜잭션이 커밋된 뒤 `AFTER_COMMIT` 리스너가 Redis를 갱신하므로 롤백된 주문은 read model에 반영되지 않습니다. Redis 갱신이나 조회가 실패하면 현재 요청은 MySQL `GROUP BY`로 처리해 Redis를 정본으로 만들지 않습니다. Redis 갱신이 비동기 유실까지 보장해야 하는 요구가 생기면 Outbox 같은 별도 전달 보장을 검토합니다.

조회마다 `to`를 한 번만 얻고 `[to - 7일, to)` 구간을 집계합니다. 시작 경계는 포함하고 종료 경계는 제외해 연속 조회 구간이 겹치지 않게 합니다. `users`와 `point_history`의 DB 생성 시각도 `DATETIME(6)`로 맞춰 테이블 간 정밀도 차이를 없앱니다. JDBC 연결 세션과 로컬·테스트 MySQL도 UTC로 고정해 애플리케이션 시각과 DB 시각의 시간대 차이를 없앱니다.

V5는 아직 배포 전이고 영속 주문 데이터가 없는 현재 환경에서 `orders.created_at`의 스키마 정밀도와 기본값만 정렬합니다. 기존 V3 스키마에 주문 데이터가 있는 환경은 저장 당시 DB session timezone을 먼저 확인해야 하며, 검증된 별도 `CONVERT_TZ` 데이터 마이그레이션 없이 V5를 적용하면 안 됩니다. 기존 데이터의 시간대를 임의로 추정해 변환하거나 데이터를 삭제하지 않습니다.

주문 횟수 내림차순, 동률이면 메뉴 ID 오름차순으로 최대 3개를 반환하며 이름은 현재 `menus.name`을 사용합니다. `(created_at, menu_id)` 인덱스를 두고 실제 MySQL `SHOW INDEX`와 `EXPLAIN`을 확인하되, 작은 테스트 데이터에서 특정 실행계획 선택을 강제하지 않습니다.

## 6. 테스트 전략

- 통합 테스트는 MySQL과의 락/트랜잭션 동작 차이를 없애기 위해 Testcontainers로 실제 MySQL 컨테이너를 띄워 검증합니다.
- 1차로 각 API의 해피패스와 주요 예외 케이스(포인트 부족, 존재하지 않는 메뉴/유저 ID)를 통합 테스트로 작성합니다.
- 동시성 제어 전략이 확정된 후, 동일 유저에 대한 동시 주문 요청을 `ExecutorService`로 발사해 최종 잔액이 예상값과 정확히 일치하는지 검증하는 테스트를 추가합니다.

## 7. 기술 선택 이유 요약

| 항목 | 선택 | 이유 |
|---|---|---|
| 언어/프레임워크 | Spring Boot (Java) | 익숙한 스택으로 설계 깊이에 집중, 트랜잭션 관리 생태계 성숙 |
| DB | MySQL | 다중 인스턴스 환경에서 단일 공유 진실 원천(source of truth) 역할, 비관적 락 지원 |
| read model | Redis ZSET | 주문 시각을 score로 저장해 최근 7일의 메뉴별 주문 수를 빠르게 계산 |
| 데이터 접근 | Spring Data JPA | 엔티티가 `table-spec.md`와 1:1 대응해 가독성이 좋고, `@Lock(PESSIMISTIC_WRITE)`로 5.1의 비관적 락을 선언적으로 표현 가능. 인기 메뉴 집계 같은 복잡한 조회는 JPQL/QueryDSL로 보완 |
| 마이그레이션 | Flyway | 메뉴 시드 데이터와 스키마 변경 이력을 코드로 관리 |
| API 문서 | springdoc-openapi | 코드와 문서 어긋남 방지, 자동 생성 |
| 테스트 DB·브로커 | Testcontainers (MySQL, Kafka) | 락·트랜잭션·Producer/Consumer 동작을 실제 인프라로 검증 |
| 메시지 브로커 | Spring Kafka | `acks=all`, idempotence, key 기반 Partition, Consumer Group offset 재처리 |
| 메시지 관찰 | Kafka UI | topic·message·Partition·Consumer Group을 로컬에서 확인 |
| 다중 인스턴스 증명 | docker-compose | 동일 MySQL·Redis를 공유하는 2개 인스턴스와 Kafka Group의 동작을 시연 |
