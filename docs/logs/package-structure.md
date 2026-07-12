# package-structure — 로그

## Plan — 2026-07-12

- 목적: 평평한 기능 패키지를 도메인과 역할이 드러나는 구조로 재배치
- 불변식: API 경로·요청·응답, DB 스키마, 트랜잭션 경계, 비즈니스 동작 유지
- 범위: `domain`, `global`, `infra` 패키지와 테스트 패키지 정리
- 제외: Outbox, 멱등성, 캐시 등 참조 저장소의 추가 기능
- 검증: 전체 MySQL Testcontainers 테스트, 애플리케이션 기동, OpenAPI·메뉴 API 응답

## Attempt 1 — 2026-07-12 ❌ FAIL

- 현상: MySQL과 Flyway 검증 후 웹 서버 기동 실패
- 원인: 사용자 실행 프로세스가 이미 `8080` 포트를 사용 중
- 다음: 사용자 프로세스는 유지하고 검증용 포트를 `18082`로 변경

## Attempt 2 — 2026-07-12 ✅ PASS

- 결과: `./gradlew clean test` 전체 통과
- 실행: Docker MySQL `13306`, 애플리케이션 `18082`에서 정상 기동
- HTTP: `/v3/api-docs` 200, `/menus` 200 및 메뉴 3개 확인
- API 계약: OpenAPI 경로 4개가 기존과 동일함을 확인
- 배운 점: 패키지 이동은 런타임 동작을 바꾸지 않지만 DTO 변환 메서드의 패키지 가시성은 명시적으로 조정해야 함
