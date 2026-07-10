# 개발 단계 지침 (Workflow)

기능 단위(API 하나, 도전 요구사항 항목 하나) 작업은 Plan → Generate → Evaluate 3단계를 매번 거친다. 한 번에 Generate로 건너뛰지 않는다.

## 작업 순서

전체 중 어디까지 왔는지 보는 인덱스다. 상태는 🔲(미착수) → 🔨(진행중) → ✅(main 병합 완료) 순으로만 갱신한다. 각 항목의 세부 시도 이력은 `docs/logs/{기능}.md` 참고.

| 순서 | 항목 | 상태 | 브랜치 | 로그 |
|---|---|---|---|---|
| 0 | 프로젝트 셋업 (빌드 도구, DB/Flyway/Testcontainers/springdoc 의존성) | 🔨 | feature/project-setup | docs/logs/project-setup.md |
| 1 | 커피 메뉴 목록 조회 | 🔲 | feature/menu-list | docs/logs/menu-list.md |
| 2 | 포인트 충전 (비관적 락 포함) | 🔲 | feature/point-charge | docs/logs/point-charge.md |
| 3 | 주문/결제 (비관적 락 + 실시간 전송 포함) | 🔲 | feature/order | docs/logs/order.md |
| 4 | 인기 메뉴 조회 | 🔲 | feature/popular-menu | docs/logs/popular-menu.md |
| 5 | 동시성 검증 테스트 (2·3 완료 후) | 🔲 | feature/concurrency-test | docs/logs/concurrency-test.md |
| 6 | 다수 인스턴스 검증 (docker-compose + nginx) | 🔲 | feature/multi-instance | docs/logs/multi-instance.md |

- 0번은 다른 모든 항목이 얹히는 선행 작업이다 — Spring Boot 프로젝트 골격에 `strategy.md` 7장이 확정한 MySQL/Flyway/Testcontainers/springdoc-openapi 의존성을 추가하고 빌드되는지까지 확인한다. 데이터 접근 방식은 Spring Data JPA로 한다 (엔티티가 `table-spec.md`와 1:1 대응, 락은 `@Lock(PESSIMISTIC_WRITE)`로 표현).
- **2·3번은 구현 시점에 이미 `strategy.md` 5.1의 비관적 락을 포함한다.** 락을 나중에(5번에서) 추가하는 게 아니다 — 5번은 그 락이 동시 요청에서도 정합성을 지키는지 `ExecutorService`로 검증하는 별도 테스트 단계다.
- 6번은 1~4번 API가 모두 구현된 뒤, 상태를 공유 MySQL에만 두는 stateless 설계(`strategy.md` 4장)가 실제로 다중 인스턴스에서 동작하는지 시연하는 단계다.

## Plan — 여기까지만 한다

- `docs/strategy.md` / `table-spec.md` / `api-spec.md`(및 `docs/rules/policy.md`)를 근거로 구현 계획을 짧게 서술한다: 무엇을, 왜, 어떤 케이스(해피패스 + 예외)를 다룰지.
- **코드를 쓰지 않는다.** 계획 단계의 산출물은 문장/체크리스트다.
- 계획이 확정되면 아래 "로그" 절 템플릿에 따라 `docs/logs/{기능}.md`의 "Plan" 섹션에 남긴다 (세션이 끊겨도 재개 시 여기서 확인한다).
- 문서에 근거가 없는 판단이 필요하면 여기서 멈추고 사용자에게 질문한다. 특히 `policy.md`의 "보류 항목"에 해당하면 반드시 멈춘다.
- 이미 튜터 설계 점검 전이라면, 엔티티 추가/삭제·API 시그니처 변경처럼 문서의 구조 자체를 바꾸는 계획은 세우지 않는다 (`conventions.md`의 문서 갱신 순서 참고).
- 코드를 건드리는 작업이면 아래 "브랜치" 절에 따라 `feature/{기능}` 브랜치부터 분기하고, 이 문서 위쪽 "작업 순서" 표에서 해당 항목 상태를 🔲 → 🔨로 갱신한다.

## Generate — 여기까지만 한다

- Plan에서 확정한 범위 안에서만 코드와 테스트를 작성한다.
- 테스트는 해피패스 1개 + 주요 예외 케이스(정책 문서에 정의된 에러코드 기준)를 함께 작성한다.
- 계획에 없던 리팩터링, 요청 밖 기능, "하는 김에" 개선을 끼워 넣지 않는다. 발견하면 언급만 하고 별도로 제안한다.

## Evaluate — 여기까지만 한다

- Testcontainers로 실제 MySQL 컨테이너를 띄워 테스트를 실행한다. H2 등으로 대체하지 않는다 (락/트랜잭션 동작 차이로 신뢰 불가).
- 실행 결과를 직접 확인한다. 코드를 보고 "통과할 것 같다"고 추측으로 완료를 선언하지 않는다.
- 시도 결과(성공/실패 모두)를 아래 "로그" 절 템플릿에 따라 `docs/logs/{기능}.md`에 Attempt로 append한다.
- 실패하면 원인을 분석해 Generate로 되돌아가 수정 후 재검증한다. Evaluate 단계에서 코드를 직접 고치고 넘어가지 않는다 — 반드시 Generate로 돌아가는 루프를 명시적으로 거친다.
- 통과가 확인되면 아래 "브랜치" 절에 따라 `feature/{기능}`을 `main`에 병합하고, "작업 순서" 표에서 해당 항목 상태를 🔨 → ✅로 갱신한다. 이후 다음 기능으로 넘어가거나 사용자에게 완료를 보고한다.

## 브랜치

개인 프로젝트지만 기능 단위로 작업을 분리해 커밋 이력을 명확하게 남긴다. PR은 열지 않는다 — 리뷰어가 없고, 커밋 메시지 자체가 이미 변경 근거를 담기 때문이다 (`conventions.md` 참고).

**이름**: `feature/{기능}` — `api-spec.md`의 API 단위와 맞춘다. 예: `feature/menu-list`, `feature/point-charge`, `feature/order`, `feature/popular-menu`. 특정 API에 속하지 않는 작업(동시성 테스트 등)은 `feature/{주제}`로 자유롭게 명명한다 (예: `feature/concurrency-test`).

**흐름**:
1. Plan 시작 시 `main`에서 분기한다: `git switch -c feature/{기능} main`
2. 구현 중 커밋은 이 브랜치 위에 계속 쌓는다.
3. Evaluate 통과 후 `main`으로 되돌아가 병합한다: `git switch main && git merge --no-ff feature/{기능}` — `--no-ff`로 병합 커밋을 남겨, 나중에도 "이 기능이 어느 범위의 커밋들로 이루어졌는지" 로그에서 구분 가능하게 한다.
4. 병합 후 로컬 브랜치는 삭제해도 되고 남겨도 된다 (기록 목적이면 유지).

**예외 — 문서 전용 변경**: `docs/*.md`만 바꾸는 커밋(설계 문서 갱신, 이 저장소의 규칙 문서 자체 수정 등)은 브랜치를 만들지 않고 `main`에 직접 커밋한다. 브랜치 전략은 **코드 변경**(구현)에만 적용한다 — 문서 작업까지 브랜치로 나누면 오히려 오버헤드만 커진다.

**main 직접 커밋 금지 (코드 한정)**: 코드(`src/`)를 변경하는 커밋은 `feature/{기능}` 브랜치 위에서만 만든다. `main`에 코드를 직접 커밋하지 않는다.

## 로그

Plan의 계획과 Evaluate의 실행 이력·증거를 남기는 방법이다. 세 역할을 한다:

1. **계획 기록** — Plan 단계에서 확정한 범위(무엇을, 왜, 어떤 케이스)를 남긴다. 세션이 끊기거나 컨텍스트가 압축된 뒤 재개할 때 "뭘 하기로 했었는지"를 여기서 바로 확인한다.
2. **피드백 센서** — 실패 후 재시도할 때, 이전에 뭘 시도했고 왜 실패했는지 참고한다.
3. **증거** — "이 기능이 실제로 이렇게 동작했다"를 튜터에게 보일 수 있는 근거.

> `docs/strategy.md`·`table-spec.md`·`api-spec.md`는 **스펙(계획·현재 상태)**이고, 로그는 **실행 증거(raw 이력)**다. 서로 안 겹친다 — 스펙은 덮어쓰고, 로그는 append-only로 쌓는다 (단, Plan 섹션은 예외 — 아래 참고).

**위치 & 이름**: `docs/logs/{기능}.md` (예: `docs/logs/point-charge.md`, `docs/logs/order.md`, `docs/logs/concurrency-test.md`) — 위 "브랜치" 절의 이름과 1:1로 맞춘다 (`feature/{기능}` ↔ `docs/logs/{기능}.md`).

**무엇을 기록하나**:
- **Plan 섹션은 파일당 1개, 나중에 덮어쓸 수 있다** — Plan 단계에서 계획이 바뀌면(예: 사용자 승인 후 범위 조정) 이 섹션만 갱신한다. append-only가 아니다.
- **Attempt는 성공·실패 매 시도를 모두** 기록한다 (append-only, 지우거나 고치지 않는다). 실패를 빼면 같은 실수를 반복하기 쉽다.
- 각 기록은 짧은 요약으로 남긴다. 테스트 로그 원문을 통째로 붙여넣지 않는다 — 노이즈는 판단을 방해한다.
- 백엔드 증거로는 **API 요청/응답 샘플**이 가장 핵심이다. 필요하면 테스트 결과 요약, DB before/after 샘플도 남긴다.

**템플릿**:

```markdown
# point-charge — 로그

## Plan — 2026-07-11
- 무엇을: 포인트 충전 API (`POST /users/{userId}/points/charge`)
- 왜: 필수 요구사항 2번, `table-spec.md`의 point_history 구조 사용
- 케이스: 해피패스(정상 충전) + amount <= 0 → 400 + 존재하지 않는 userId → 404

## Attempt 1 — 2026-07-11  ❌ FAIL
- 시도: 포인트 충전 API 구현
- 결과: `amount = 0` 요청이 400이 아니라 200으로 처리됨
- 원인: 검증 조건이 `amount < 0`으로만 되어 있어 0을 걸러내지 못함
- 다음: `amount <= 0` 검증으로 수정

## Attempt 2 — 2026-07-11  ✅ PASS
- 시도: 검증 조건을 `amount <= 0`으로 수정
- 결과: 통합 테스트 전체 통과 (Testcontainers MySQL)
- 증거:
  - `POST /users/1/points/charge {"amount": 0}` → `400 {"error":{"code":"INVALID_CHARGE_AMOUNT"}}`
  - `POST /users/1/points/charge {"amount": 10000}` → `200 {"data":{"userId":1,"balance":10000}}`
```

**언제 쓰나**:
- Plan 단계를 마치면 곧바로 `docs/logs/{기능}.md`를 만들고 Plan 섹션을 채운다 (파일이 없으면 이때 새로 만든다).
- Evaluate 단계마다 시도 결과를 Attempt로 추가한다 — 통과한 시도도 남긴다 (마지막에 통과했다는 사실 자체가 증거).
