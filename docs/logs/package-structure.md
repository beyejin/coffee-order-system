# package-structure — 로그

## Plan — 2026-07-13 리뷰 반영

- `User`가 포인트 사용 시 잔액 부족을 직접 거부하고, HTTP 요청 형식 검증은 DTO와 컨트롤러 경계에서 처리한다.
- 충돌 가능성이 있는 단수형 테이블명을 `users`, `menus`로 바꾸고 모든 FK·쿼리·문서를 동기화한다.
- `users`, `point_history`의 생성 시각 정밀도를 `DATETIME(6)`로 통일하고 최근 7일 계산은 `minusDays(7)`로 표현한다.
- 인증·인가는 과제 제외 범위이므로 추가하지 않는다.

## Attempt 1 — 2026-07-13 ❌ FAIL

- `./gradlew test`에서 Java 소스와 테스트 소스 컴파일은 통과했다.
- Docker 엔진이 실행 중이지 않아 Testcontainers가 MySQL 컨테이너를 만들지 못했고, 전체 테스트가 애플리케이션 컨텍스트 생성 전에 중단됐다.
- 다음: Docker를 기동한 뒤 같은 전체 테스트를 다시 실행한다.

## Attempt 2 — 2026-07-13 ✅ PASS

- Docker 기동 후 `./gradlew clean test` 전체 통과 (`BUILD SUCCESSFUL`, 28초).
- `User.use` 직접 호출의 잔액 부족 예외와 잔액 불변을 확인했다.
- 누락·0·음수 요청 값이 DTO 검증을 거쳐 400 `VALIDATION_ERROR`로 응답됨을 확인했다.
- MySQL `information_schema.columns`에서 `users`, `point_history`, `orders`의 `created_at` 정밀도가 모두 6임을 확인했다.
- Flyway가 `users`, `menus`와 이를 참조하는 FK를 생성하고 Hibernate 스키마 검증 및 전체 API 통합 테스트가 통과했다.

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
