# point-charge — 로그

## Plan — 2026-07-12
- 불변식: 충전 금액은 0보다 커야 하며, 사용자 잔액과 `CHARGE` 이력은 같은 트랜잭션에서 함께 반영한다.
- 동시성: 동일 사용자 행을 `PESSIMISTIC_WRITE`로 조회해 여러 인스턴스의 충전 요청도 DB에서 직렬화한다.
- 예외: 없는 사용자는 `USER_NOT_FOUND`, 0 이하 금액은 `INVALID_CHARGE_AMOUNT`로 공통 실패 응답을 반환한다.
- 검증: 정상 충전, 0·음수 금액, 없는 사용자, 동일 사용자 20건 동시 충전을 MySQL Testcontainers에서 확인한다.
- 완료 증거: 동시 요청 성공 수, 최종 잔액, `CHARGE` 이력 수와 금액 합계가 모두 일치해야 한다.

## Attempt 1 — 2026-07-12 ✅ PASS
- 결과: `./gradlew clean test --console plain` 성공, 메뉴 회귀를 포함한 전체 8개 테스트가 통과했다.
- API 증거: 정상 충전 후 잔액 10,000P와 `CHARGE` 이력 1건이 함께 저장됐고, 0·음수 금액은 400, 없는 사용자는 404를 반환하면서 DB를 변경하지 않았다.
- 동시성 증거: 동일 사용자에게 100P 충전을 20건 동시에 실행해 성공 20건, 최종 잔액 2,000P, 이력 20건, 이력 금액 합계 2,000P를 확인했다.
- 배운 점: `@Transactional` 경계 안에서 사용자 행을 `PESSIMISTIC_WRITE`로 먼저 잠그면, 애플리케이션 스레드가 달라도 공유 MySQL이 잔액 변경을 순서대로 처리한다.

## Review fix Attempt 1 — 2026-07-12 ❌ FAIL
- 시도: 테스트용 MySQL trigger가 `point_history` INSERT를 거부하게 해 잔액 변경 롤백을 검증했다.
- 결과: MySQL binary logging 환경에서 테스트 사용자는 trigger 생성에 필요한 `SUPER` 권한이 없어 error 1419로 실패했다.
- 다음: 권한 상승 없이 실제 DB INSERT를 실패시키도록 테스트용 CHECK 제약을 사용한다.

## Review fix Attempt 2 — 2026-07-12 ✅ PASS
- 결과: `./gradlew clean test --console plain` 성공, 전체 12개 테스트가 통과했다.
- 오버플로 증거: 잔액이 `Long.MAX_VALUE`인 사용자에게 1P 충전 시 409 `POINT_BALANCE_OVERFLOW`를 반환하고 잔액과 이력이 그대로 유지됐다.
- 요청 검증 증거: 잘못된 JSON과 빈 요청 본문이 모두 400 `VALIDATION_ERROR` 공통 응답으로 변환됐다.
- 롤백 증거: 테스트용 CHECK 제약이 양수 `point_history` INSERT를 실제 MySQL에서 거부했을 때 `DataIntegrityViolationException`이 발생했고, 앞서 변경된 잔액도 0P로 롤백되며 이력은 0건이었다.
- 배운 점: 성공 결과만 확인하는 테스트와 달리 DB의 두 번째 쓰기를 의도적으로 실패시키면 트랜잭션 원자성을 직접 증명할 수 있다.

## Review fix Attempt 3 — 2026-07-12 ✅ PASS
- 결과: `./gradlew clean test --console plain` 성공, 전체 14개 테스트가 통과했다.
- 경로 검증: `/users/abc/points/charge`가 400 `VALIDATION_ERROR` 공통 응답을 반환했다.
- 금액 형식 검증: Jackson의 `Float → Integer` 변환만 차단해 소수 충전 금액이 400 `VALIDATION_ERROR`를 반환하고 DB를 변경하지 않았다. 문자열 coercion 정책은 변경하지 않았다.
- 종료 보장: 동시성 테스트가 `shutdownNow()` 후 최대 5초간 worker 종료를 기다리고, 대기가 중단되면 interrupt 상태를 복원하도록 보강했다.
