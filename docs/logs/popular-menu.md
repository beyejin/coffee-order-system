# popular-menu — 로그

## Plan — 2026-07-12
- 시간: `Clock`으로 UTC `to`를 한 번 고정하고 `[to - 168시간, to)` 주문만 포함한다.
- 집계: 메뉴별 주문 수 내림차순, 동률이면 메뉴 ID 오름차순으로 최대 3개를 반환한다.
- 이름: 응답에는 현재 `menu.name`을 사용한다.
- 검증: 시작 경계 포함, 종료 경계 제외, 오래된 주문 제외, 동률, top 3, 빈 결과와 3개 미만 결과를 MySQL 통합 테스트로 확인한다.
- 성능 증거: `(created_at, menu_id)` 인덱스 컬럼 순서를 `SHOW INDEX`로 확인하고 실제 집계 SQL의 `EXPLAIN` 결과를 기록한다. 소량 데이터에서 특정 key 선택은 강제하지 않는다.
- Redis 적용 계획: MySQL을 정본으로 유지하고, 주문 커밋 후 menu별 Redis ZSET에 주문 시각을 저장해 최근 7일 count read model로 사용한다. Redis 오류 시 기존 MySQL 집계로 fallback한다.

## Attempt 1 — 2026-07-12 ✅ PASS
- 결과: `./gradlew clean test --console plain` 성공, 기존 메뉴·포인트·주문 회귀를 포함한 전체 27개 테스트가 통과했다.
- 시간 경계: `to - 168시간`과 같은 주문은 포함하고, `to`와 같은 주문 및 시작 경계보다 1초 오래된 주문은 제외했다.
- 정렬·개수: 주문 수가 같은 메뉴는 ID 오름차순으로 정렬됐고, 4개 메뉴에 주문이 있어도 상위 3개만 반환했다.
- 빈 결과: 최근 168시간 주문이 없으면 성공 응답의 빈 배열을 반환했다. 결과가 1개뿐인 경우에도 그대로 1개만 반환했다.
- 이름: 주문 집계 후 변경된 현재 `menu.name`이 응답에 사용됐다.
- 인덱스: `SHOW INDEX`에서 `idx_orders_created_at_menu_id`의 1번 컬럼 `created_at`, 2번 컬럼 `menu_id`를 확인했다.
- EXPLAIN: 테스트 데이터에서는 `orders`가 `idx_orders_created_at_menu_id`를 사용했고 `menu`는 PK `eq_ref` 조인이었다. `Using where; Using index; Using temporary; Using filesort`가 관찰됐으며, 데이터 분포에 따라 계획은 달라질 수 있어 특정 key 선택을 통과 조건으로 강제하지 않았다.
- 배운 점: 기간 경계와 동률 기준을 명시해야 같은 원본 주문에서 항상 동일한 인기 순위를 계산할 수 있다.

## Review fix Attempt 1 — 2026-07-12 ✅ PASS
- 시간 저장: `OrderService`가 인기 조회와 동일한 UTC `Clock`에서 주문 시각을 캡처하고 microsecond로 절삭해 저장하도록 변경했다.
- 스키마: 기존 V3를 수정하지 않고 V5에서 `orders.created_at`을 `DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6)`로 정렬했다.
- UTC 계약: 로컬 JDBC URL과 Hikari 세션 초기화, compose MySQL, Testcontainers의 시간대를 UTC로 고정했다. 테스트에서 `@@session.time_zone = '+00:00'`과 `UTC_TIMESTAMP() = NOW()`를 확인했다.
- 실제 API 증거: 고정 UTC 시각보다 1초 앞선 시점에 `POST /orders`로 생성한 주문이 해당 조회 구간에서 1건으로 집계됐고, DB `created_at`도 기대한 UTC microsecond 값과 일치했다.
- 세부 경계: microsecond 단위로 시작 경계와 정확히 같은 주문 및 종료 1μs 전 주문은 포함하고, 시작 1μs 전과 종료 경계 주문은 제외했다.
- 현재 이름: 주문 INSERT 후 `menu.name`을 변경하고 조회해 변경된 현재 이름이 반환됨을 확인했다.
- 결과: `./gradlew clean test --console plain` 성공, 전체 29개 테스트가 통과했다.

## Review fix Attempt 2 — 2026-07-12 ✅ PASS
- V5 전제: 아직 배포 전이고 영속 주문 데이터가 없는 현재 환경에서 컬럼 정밀도와 기본값만 정렬하며 데이터 변환은 수행하지 않는다.
- 기존 데이터 환경: V3로 저장된 주문이 있다면 당시 DB session timezone을 먼저 확인하고 검증된 별도 `CONVERT_TZ` 마이그레이션을 설계해야 한다. 시간대를 임의 추정해 변환하거나 데이터를 삭제하지 않으며, 이 절차 없이 V5를 적용하면 안 된다.
- 검증: fresh database에서 V1부터 V5까지 전체 Flyway migration과 전체 테스트를 다시 실행한다.

## Redis ZSET Attempt 1 — 2026-07-15 ✅ PASS
- read model: 성공한 주문의 `AFTER_COMMIT` 이벤트에서 `popular:menus:{menuId}:orders` ZSET에 주문 ID를 member로 저장하고, UTC epoch microsecond를 score로 저장한다. MySQL 주문 원장은 그대로 정본이다.
- 기간: 메뉴별 `ZCOUNT`에 `[to - 7일, to)`를 적용해 시작 경계 포함·종료 경계 제외를 유지한다. 결과는 주문 수 내림차순, menu ID 오름차순으로 최대 3개를 반환한다.
- 장애: Redis 조회 실패 또는 read model stale 감지 시 기존 MySQL `GROUP BY` 집계로 fallback한다. 포인트·주문 트랜잭션은 Redis 장애 때문에 롤백하지 않는다.
- 검증: `./gradlew clean test --console plain` 성공, 전체 37개 테스트가 통과했다. Redis Testcontainers 통합 3개와 기존 인기 메뉴 MySQL 회귀 6개를 포함한다.
- 실패 주문: 포인트 부족 주문은 Redis ZSET에 반영되지 않는다. 커밋 전 주문 INSERT 실패에서는 `AFTER_COMMIT` 랭킹 리스너가 실행되지 않는다.
- 배운 점: 단순 누적 `ZINCRBY`는 최근 7일의 부분 경계를 표현하기 어렵다. 주문 시각을 score로 저장한 menu별 ZSET이 현재 과제의 정확성 계약에 더 직접적으로 맞는다.
