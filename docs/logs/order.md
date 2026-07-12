# order — 로그

## Plan — 2026-07-12
- 불변식: 존재하는 주문은 성공한 주문이며, 주문 가격은 결제 시점 메뉴 가격 스냅샷이다.
- 트랜잭션: 사용자 행을 잠근 뒤 잔액 차감, `USE` 이력, 주문 저장을 한 트랜잭션으로 처리한다.
- 예외: 없는 메뉴·사용자, 잔액 부족, 요청 형식 오류에서는 주문·잔액·이력이 변경되지 않는다.
- 동시성: 같은 사용자에게 동시 주문을 실행해 성공 건수, 잔액, 주문 수, `USE` 이력 수가 일치하는지 확인한다.
- 롤백: 실제 MySQL이 주문 INSERT를 거부하게 해 앞선 잔액·이력 변경도 함께 롤백되는지 확인한다.
- 외부 전송: 커밋 후 사용자 ID·메뉴 ID·결제금액을 비동기 Mock client에 전달하고, 외부 실패가 DB 커밋에 영향을 주지 않는지 확인한다.
- 범위 제외: 인기 메뉴 API, Outbox, Kafka, 전송 재시도는 구현하지 않는다.

## Attempt 1 — 2026-07-12 ✅ PASS
- 결과: `./gradlew clean test --console plain` 성공, 기존 메뉴·포인트 회귀를 포함한 전체 23개 테스트가 통과했다.
- 정상 주문: 10,000P에서 4,500P 메뉴 주문 후 잔액 5,500P, 주문 1건, `USE` 이력 1건을 확인했다. 이후 메뉴 가격을 변경해도 주문 가격은 4,500P로 유지됐다.
- 예외: 잔액 부족은 409, 없는 메뉴·사용자는 404, 누락된 ID는 400을 반환하며 주문·잔액·이력을 변경하지 않았다.
- 롤백: 테스트용 MySQL CHECK 제약으로 `orders` INSERT를 실패시켰을 때 잔액 10,000P, 이력 0건, 주문 0건으로 전체 롤백됐고 이벤트도 전송되지 않았다.
- 동시성: 잔액 9,000P인 사용자에게 4,500P 주문을 10건 동시에 실행해 성공 2건, 최종 잔액 0P, 주문 2건, `USE` 이력 2건·합계 9,000P를 확인했다.
- 외부 전송: 비동기 client가 사용자 ID 1, 메뉴 ID 1, 결제금액 4,500P를 받았고 전송 시점에 커밋된 주문을 별도 DB 연결에서 조회할 수 있었다.
- 장애 격리: Mock client가 예외를 던져도 주문 응답은 200이며 잔액 5,500P, 주문 1건, 이력 1건이 유지됐다.
- 한계: `AFTER_COMMIT` 메모리 이벤트는 재시도·영속 기록이 없어 프로세스 종료나 전송 실패 시 유실될 수 있다.

## Review fix Attempt 1 — 2026-07-12 ❌ FAIL
- 시도: `@Async` listener를 Mockito spy로 감싸 실제 메서드 반환 시 completion latch를 감소시켰다.
- 결과: 비동기 AOP proxy의 void 메서드 스터빙과 충돌해 Mockito unfinished stubbing과 완료 대기 실패가 발생했다.
- 다음: 운영 listener의 `finally`에서 호출되는 no-op completion observer를 두고 테스트에서만 latch 구현으로 교체한다.

## Review fix Attempt 2 — 2026-07-12 ✅ PASS
- 결과: `./gradlew clean test --console plain` 성공, 전체 23개 테스트가 통과했다.
- 비동기 경계: client 호출 시작 latch와 listener 완료 observer를 분리해 외부 client 예외가 발생하고 listener의 catch/finally가 끝날 때까지 결정적으로 대기했다.
- 격리: 각 테스트의 `@AfterEach`가 예상한 listener 완료 수를 모두 기다린 뒤 DB와 테스트 client를 다음 테스트에서 초기화한다.
- 요청 검증: `userId`가 누락된 `POST /orders`가 400 `VALIDATION_ERROR`를 반환하고 잔액 0P, 주문 0건, 이력 0건, 외부 전송 0건을 유지했다.

## Review fix Attempt 3 — 2026-07-12 ✅ PASS
- 단순화: 운영용 completion observer와 no-op bean을 제거하고 시작·실패·완료 신호를 테스트 client 내부로만 이동했다.
- 경쟁 조건 방지: `send()` 시작 시 `failNext.getAndSet(false)` 결과를 지역 변수에 캡처하고 `finally`에서 완료 latch를 감소시켜 reset과 실패 플래그 사이의 경쟁을 없앴다.
- 테스트 격리: `@AfterEach`가 예상한 client send 완료를 모두 기다린 뒤 다음 테스트가 client를 reset한다. 완료 대기 실패나 interrupt가 발생해도 `finally`에서 테스트용 DB 제약 제거와 executor 종료를 수행한다.
- 결과: `./gradlew clean test --console plain` 성공, 전체 23개 테스트가 통과했다.
