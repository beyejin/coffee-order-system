# AGENTS.md

이 저장소에서 작업하는 AI 에이전트가 따라야 할 최소 규칙과 문서 라우터입니다.

## 항상 적용

- K사 서버 개발 사전과제이며, 구현보다 `왜 이렇게 설계했는가`를 설명하는 것이 중요하다.
- 모든 설명·문서·커밋은 한국어로 작성한다.
- 작업 전 실제 코드와 관련 문서를 읽고, 구현되지 않은 내용을 완료된 것처럼 말하지 않는다.
- 문서와 코드가 다르면 버그다. 설계 변경은 문서를 먼저 갱신한 뒤 구현한다.
- 요구사항에 없는 기능과 인프라는 문제를 증명할 근거가 생기기 전에는 추가하지 않는다.
- 핵심 설계와 비즈니스 로직은 사용자가 설명할 수 있어야 한다. AI는 반례·테스트·리뷰로 이를 돕는다.

## 문서 라우팅

| 작업 | 먼저 읽을 문서 |
|---|---|
| 현재 범위와 진행 상태 확인 | [`README.md`](README.md) |
| 도메인 간 의존성과 데이터 흐름 확인 | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| 코드 진입점과 변경 경로 확인 | [`src/AGENTS.md`](src/AGENTS.md) |
| 검증 스크립트의 목적과 실행 조건 확인 | [`scripts/AGENTS.md`](scripts/AGENTS.md) |
| 설계 배경과 기술 선택 검토 | [`docs/strategy.md`](docs/strategy.md) |
| 테이블·컬럼·제약 확인 | [`docs/table-spec.md`](docs/table-spec.md) |
| API 요청·응답·에러 확인 | [`docs/api-spec.md`](docs/api-spec.md) |
| 도메인 불변식과 미확정 결정 확인 | [`docs/rules/policy.md`](docs/rules/policy.md) |
| 기능 구현·브랜치·검증 흐름 확인 | [`docs/rules/workflow.md`](docs/rules/workflow.md) |
| 에이전트 작업 범위·검증 게이트 확인 | [`harness/README.md`][harness-readme] |
| 문서·커밋 작성 규칙 확인 | [`docs/rules/conventions.md`](docs/rules/conventions.md) |
| 이전 시도와 실제 검증 결과 확인 | [`docs/logs/`](docs/logs/README.md) |
| 에이전트 작업 pass-rate 확인 | [`docs/agent-evaluation.md`](docs/agent-evaluation.md) |

## 빠른 검증 명령

| 검증 범위 | 명령 |
|---|---|
| 문서 링크·소스 컨텍스트 | `python3 scripts/check-doc-context.py` |
| Flyway 순차 업그레이드 | `./gradlew test --tests com.example.coffee.MigrationUpgradeTest` |
| 전체 MySQL Testcontainers 회귀 | `./gradlew test` |
| 다중 인스턴스 smoke | [`scripts/AGENTS.md`](scripts/AGENTS.md)의 사전 조건 확인 후 `./scripts/multi-instance-smoke.sh` |

[harness-readme]: harness/README.md

## 구현 게이트

기능 작업은 `Plan → Issue → Branch → Manifest → Prepare → Generate → Evaluate → Explain` 순서를 따른다.

1. **Plan**: 사용자가 목적·불변식·트랜잭션 경계·예외 케이스·완료 조건을 설명한다. AI는 반례를 찾는다.
2. **Issue**: 확정한 Plan, 범위, 완료 조건과 검증 방법으로 GitHub 이슈를 생성한다. 이슈가 없으면 코드 변경을 시작하지 않는다.
3. **Branch**: 최신 `origin/main`에서 이슈 번호를 포함한 branch와 clean worktree를 만든다.
4. **Manifest**: 제품 파일보다 먼저 `harness/plans/{issue}.json`에 목적·허용 경로·위험·계약 변경·비목표를 고정한다.
5. **Prepare**: `python3 scripts/agent-harness.py prepare harness/plans/<issue>.json`이 `PASS`한 뒤에만 생성 작업을 시작한다.
6. **Generate**: manifest의 allowedPaths 안에서 확정한 범위의 코드와 테스트만 작성한다.
7. **Evaluate**: 실제 MySQL Testcontainers와 하네스 검증을 실행하고 결과를 기록한다.
8. **Explain**: 선택 이유, 동시 요청, 실패 시 롤백을 사용자가 설명할 수 있어야 완료한다.

하네스가 적용되는 작업은 제품 파일 수정 전 `python3 scripts/agent-harness.py prepare harness/plans/<issue>.json`, 완료 선언 전 `python3 scripts/agent-harness.py evaluate harness/plans/<issue>.json`을 실행한다. 현재 base tip·merge-base·HEAD·plan·diff에 연결된 `PASS` evidence가 없으면 검증 완료라고 말하지 않는다. 상세 규칙은 [`harness/README.md`][harness-readme]를 따른다.

문서에 없는 판단이나 `policy.md`의 미확정 항목이 필요하면 구현 전에 질문한다.
