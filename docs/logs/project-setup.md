# project-setup — 로그

## Plan — 2026-07-10
- 무엇을: Spring Initializr로 받은 빈 Gradle 스캐폴드(`coffee.zip`, Spring Boot 4.1.0 / Java 17)에 `strategy.md` 7장이 확정한 의존성(MySQL 드라이버, Flyway, Spring Data JPA, Testcontainers, springdoc-openapi)을 추가한다.
- 왜: 다른 모든 기능(1~6번)이 이 위에서 시작되는데, 지금은 `spring-boot-starter-webmvc`+lombok만 있어 아무 기능도 못 붙인다.
- 케이스: `./gradlew build`가 성공하는지만 확인한다 (아직 API/엔티티가 없으므로 별도 테스트 케이스는 없음).

## Attempt 1 — 2026-07-10  ❌ FAIL (환경 문제, 코드 결함 아님)
- 시도: `build.gradle`에 MySQL/Flyway/Spring Data JPA/Testcontainers/springdoc-openapi 의존성 추가, `policy.md`의 "H2 금지" 원칙에 맞춰 `TestcontainersConfiguration`(`@ServiceConnection` + `MySQLContainer`)으로 기본 `contextLoads()` 테스트 연결
- 결과: `./gradlew compileJava compileTestJava` — BUILD SUCCESSFUL (의존성 해석·컴파일 정상). `./gradlew test` — FAIL, `DockerClientProviderStrategy`에서 `IllegalStateException` (Docker 데몬을 찾을 수 없음)
- 원인: 이 세션(샌드박스)에 Docker Desktop.app은 설치돼 있지만 데몬이 실행 중이 아님. 코드/의존성 설정 자체는 문제 없음.
- 다음: 로컬에서 Docker Desktop을 켠 뒤 `./gradlew test`로 재검증 필요.

## Attempt 2 — 2026-07-12  ❌ FAIL
- 시도: 현재 환경에서 `./gradlew test` 재실행 및 의존성 호환성 점검
- 결과: 컴파일은 성공했지만 Docker 데몬을 찾지 못해 `contextLoads()` 실패
- 추가 발견: Spring Boot 4.x는 springdoc 3.x와 호환되지만 현재 `build.gradle`은 springdoc 2.7.0을 사용 중
- 다음:
  1. springdoc을 Spring Boot 4.x 호환 버전으로 정렬
  2. Testcontainers 버전 관리 방식을 하나로 통일
  3. Docker Desktop 기동 후 `./gradlew clean test` 재실행
  4. 테스트 통과 전에는 프로젝트 셋업을 완료 처리하지 않음

## Attempt 3 — 2026-07-12  ❌ FAIL
- 시도: 별도 Testcontainers 1.20.4 BOM을 제거하고 Spring Boot 의존성 관리만 사용
- 결과: `junit-jupiter`, `mysql` 모듈 버전을 결정하지 못해 테스트 코드 컴파일 실패
- 원인: Testcontainers 2.0부터 모듈 artifact 이름과 컨테이너 패키지가 변경됐으며, 명시적인 2.0 BOM이 필요함
- 다음: Testcontainers 2.0.5 BOM과 새 모듈·패키지 이름으로 함께 변경

## Attempt 4 — 2026-07-12  ✅ PASS
- 변경:
  - springdoc 3.0.3으로 Spring Boot 4 호환성 정렬
  - Testcontainers 2.0.5 BOM과 `testcontainers-mysql`, `testcontainers-junit-jupiter` 사용
  - `MySQLContainer`를 Testcontainers 2.0 API로 변경
  - 로컬 MySQL 실행용 `compose.yaml`과 `DB_URL` 설정 추가
- 결과:
  - `./gradlew clean compileJava compileTestJava` 성공
  - `./gradlew clean test --console plain` 성공 (MySQL 8.0 Testcontainers)
  - 임시 MySQL 8.0.46에서 Spring Boot 4.1.0 애플리케이션 기동 성공
  - `GET /swagger-ui.html` → 302, `GET /v3/api-docs` → 200
- 배운 점: 메이저 버전 변경 시 버전 번호뿐 아니라 artifact와 Java 패키지 변경까지 공식 문서로 함께 확인해야 함
