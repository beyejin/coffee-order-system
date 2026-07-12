# menu-list — 로그

## Plan — 2026-07-12
- 불변식: 메뉴는 Flyway 시드로만 등록하고, 관리 API는 만들지 않는다.
- 응답: `GET /menus`는 메뉴 ID·이름·가격을 공통 응답 포맷으로 반환한다.
- 순서: 결과는 메뉴 ID 오름차순으로 고정한다.
- 범위: 조회 전용 기능이므로 별도의 변경 트랜잭션과 예외 응답은 없다.
- 검증: MySQL Testcontainers에서 Flyway 시드 적용, 공통 응답, 전체 메뉴 값과 정렬을 통합 테스트로 확인한다.

## Attempt 1 — 2026-07-12 ❌ FAIL
- 현상: `./gradlew clean test`의 테스트 코드 컴파일 단계에서 메뉴 통합 테스트가 `TestcontainersConfiguration`에 접근하지 못했다.
- 원인: 기존 테스트 설정 클래스가 package-private이라 하위 `menu` 패키지에서 import할 수 없었다.
- 다음: 여러 기능 패키지의 통합 테스트가 같은 MySQL 설정을 재사용할 수 있도록 설정 클래스만 public으로 변경하고 재실행한다.

## Attempt 2 — 2026-07-12 ❌ FAIL
- 현상: 컴파일 후 애플리케이션 컨텍스트 시작 시 Hibernate가 `Schema validation: missing table [menu]`로 실패했다.
- 원인: Spring Boot 4에서 `flyway-core`만 직접 추가해 Flyway 자동 설정 모듈이 포함되지 않았고, JPA 검증 전에 마이그레이션이 실행되지 않았다.
- 다음: 공식 Spring Boot 4 구성대로 `spring-boot-starter-flyway`와 MySQL 전용 `flyway-mysql` 조합으로 변경하고 재실행한다.

## Attempt 3 — 2026-07-12 ✅ PASS
- 결과: `./gradlew clean test --console plain` 성공, 전체 2개 테스트 통과.
- 증거: MySQL 8.0 Testcontainers에서 Flyway V1이 `menu` 테이블과 메뉴 3개를 생성했고, Hibernate `ddl-auto: validate`와 `GET /menus` 통합 테스트가 통과했다.
- 확인: 응답은 `success=true`, `error=null`이며 메뉴 ID·이름·가격이 ID 오름차순으로 반환됐다.
- 배운 점: Spring Boot 4에서는 라이브러리 본체만 추가하는 것과 Boot 자동 설정 starter를 추가하는 것이 다르며, Flyway가 먼저 스키마를 만든 뒤 JPA가 이를 검증한다.
