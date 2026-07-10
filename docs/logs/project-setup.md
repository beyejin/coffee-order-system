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
