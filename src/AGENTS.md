# src 작업 라우터

`src/` 아래 코드를 변경할 때는 루트 [`AGENTS.md`](../AGENTS.md)의 게이트와 아래 경로를 함께 따릅니다.

## 도메인별 진입점

| 영역 | API 진입점 | 트랜잭션·핵심 로직 | 저장소 | 테스트·필수 문서 |
|---|---|---|---|---|
| 메뉴 | [`MenuController.java`](main/java/com/example/coffee/domain/menu/controller/MenuController.java) | [`MenuService.java`](main/java/com/example/coffee/domain/menu/service/MenuService.java) | [`MenuRepository.java`](main/java/com/example/coffee/domain/menu/repository/MenuRepository.java) | [`MenuControllerTest.java`](test/java/com/example/coffee/domain/menu/MenuControllerTest.java), [`docs/api-spec.md`](../docs/api-spec.md) |
| 포인트·사용자 | [`PointController.java`](main/java/com/example/coffee/domain/point/controller/PointController.java) | [`PointService.java`](main/java/com/example/coffee/domain/point/service/PointService.java), [`User.java`](main/java/com/example/coffee/domain/user/entity/User.java) | [`UserRepository.java`](main/java/com/example/coffee/domain/user/repository/UserRepository.java), [`PointHistoryRepository.java`](main/java/com/example/coffee/domain/point/repository/PointHistoryRepository.java) | [`PointChargeIntegrationTest.java`](test/java/com/example/coffee/domain/point/PointChargeIntegrationTest.java), [`docs/rules/policy.md`](../docs/rules/policy.md) |
| 주문·외부 전송 | [`OrderController.java`](main/java/com/example/coffee/domain/order/controller/OrderController.java) | [`OrderService.java`](main/java/com/example/coffee/domain/order/service/OrderService.java), [`OrderDataPlatformEventListener.java`](main/java/com/example/coffee/infra/dataplatform/OrderDataPlatformEventListener.java) | [`OrderRepository.java`](main/java/com/example/coffee/domain/order/repository/OrderRepository.java)와 포인트·사용자 저장소 | [`OrderIntegrationTest.java`](test/java/com/example/coffee/domain/order/OrderIntegrationTest.java), [`ARCHITECTURE.md`](../ARCHITECTURE.md) |
| 인기 메뉴 | [`PopularMenuController.java`](main/java/com/example/coffee/domain/ranking/controller/PopularMenuController.java) | [`PopularMenuService.java`](main/java/com/example/coffee/domain/ranking/service/PopularMenuService.java) | [`OrderRepository.java`](main/java/com/example/coffee/domain/order/repository/OrderRepository.java), [`PopularMenuProjection.java`](main/java/com/example/coffee/domain/ranking/repository/PopularMenuProjection.java) | [`PopularMenuIntegrationTest.java`](test/java/com/example/coffee/domain/ranking/PopularMenuIntegrationTest.java), [`docs/strategy.md`](../docs/strategy.md) |
| 공통·인프라 | 각 도메인 controller | [`공통 예외`](main/java/com/example/coffee/global/error), [`공통 응답`](main/java/com/example/coffee/global/response), [`공통 설정`](main/java/com/example/coffee/global/config), [`인프라 구현`](main/java/com/example/coffee/infra) | 해당 도메인 repository | 관련 통합 테스트, [`docs/table-spec.md`](../docs/table-spec.md) |

## 변경 경로

- API 계약 변경: `docs/api-spec.md` → controller/dto → service → 관련 테스트
- 불변식·트랜잭션 변경: `docs/rules/policy.md` → service/entity/repository → MySQL 통합 테스트 → `docs/logs/{기능}.md`
- 테이블·쿼리 변경: `docs/table-spec.md` → 새 Flyway migration → entity/repository → `MigrationUpgradeTest`와 관련 통합 테스트
- 도메인 간 흐름 변경: `ARCHITECTURE.md` → 발행 이벤트·리스너·service/repository → 주문·랭킹 통합 테스트
- 공통 응답·예외 변경: [`docs/api-spec.md`](../docs/api-spec.md) → [`공통 예외`](main/java/com/example/coffee/global/error)·[`공통 응답`](main/java/com/example/coffee/global/response) → 영향을 받는 controller 테스트

기존 migration 파일은 수정하지 않고 새 버전을 추가합니다. DB·락·트랜잭션 변경은 MySQL Testcontainers 결과 없이 완료로 표시하지 않습니다.
