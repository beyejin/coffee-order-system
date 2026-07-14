# 개발·검증 흐름

기능은 `Plan → Issue → Branch → Manifest → Prepare → Generate → Evaluate → Explain` 순서로 진행합니다. 상태 관리는 이 문서에서, machine-readable 범위는 `harness/plans/{issue}.json`에서, 실제 시도와 증거는 `docs/logs/{기능}.md`에서 관리합니다.

## 작업 순서

| 순서 | 항목 | 상태 | 브랜치 | 로그 |
|---|---|---|---|---|
| 0 | 프로젝트 셋업 | ✅ | `feature/project-setup` | `docs/logs/project-setup.md` |
| 1 | 메뉴 목록 조회 | ✅ | `feature/menu-list` | `docs/logs/menu-list.md` |
| 2 | 포인트 충전과 비관적 락 | ✅ | `feature/point-charge` | `docs/logs/point-charge.md` |
| 3 | 주문·결제와 외부 전송 실험 | ✅ | `feature/order` | `docs/logs/order.md` |
| 4 | 인기 메뉴 조회 | ✅ | `feature/popular-menu` | `docs/logs/popular-menu.md` |
| 5 | 통합 동시성 검증 | 🔲 | `feature/concurrency-test` | `docs/logs/concurrency-test.md` |
| 6 | 다중 인스턴스 검증 | ✅ | `feature/multi-instance` | `docs/logs/multi-instance.md` |

상태는 `🔲 미착수 → 🔨 진행 중 → ✅ 검증 완료` 순서로 변경합니다.

## Plan

- 관련 설계·API·테이블·정책 문서를 읽습니다.
- 목적, 핵심 불변식, 트랜잭션 경계, 해피패스·예외와 완료 조건을 확정합니다.
- AI는 구현보다 먼저 동시성·실패·경계값 반례를 제시하고, 미확정 판단이 있으면 질문합니다.

## Issue

- 확정한 Plan, 작업 범위, 완료 조건과 검증 방법을 GitHub 이슈에 기록해 issue 번호를 얻습니다.
- 이슈 생성 전에는 구현을 시작하지 않으며, 범위가 달라지면 이슈와 Plan을 먼저 검토합니다.

## Branch

- 최신 `origin/main`에서 issue 전용 clean worktree와 branch를 만듭니다.
- branch 이름은 `feature|fix|refactor|docs/{이슈번호}-{slug}` 형식이며 이후 manifest의 issue 번호와 같아야 합니다.
- 하나의 브랜치는 하나의 이슈만 처리합니다.

## Manifest

- 제품 파일보다 먼저 `harness/plans/{issue}.json`을 작성합니다.
- objective, allowedPaths, acceptanceCriteria, declaredRisks, contractChanges, nonGoals를 기록합니다.
- 범위나 위험이 바뀌면 manifest를 자동 확대하지 않고 REPLAN_REQUIRED로 돌아갑니다.

## Prepare

- 최신 `origin/main`의 clean worktree에서 `python3 scripts/agent-harness.py prepare harness/plans/{issue}.json`을 실행합니다.
- 선택한 plan 외 dirty 경로, branch·issue 불일치, base 확인 실패, Python·Java 17·Docker 환경 부재를 PASS로 처리하지 않습니다.
- prepare가 `PASS=0`일 때만 allowedPaths 안의 파일을 변경합니다.

## Generate

- Plan에 포함된 코드와 테스트만 작성합니다.
- 해피패스와 주요 예외 테스트를 함께 작성합니다.
- 다음 기능, 불필요한 인프라, 인접 리팩터링을 선행하지 않습니다.
- 현재 브랜치가 해당 이슈의 작업 브랜치인지 확인한 뒤 코드를 변경합니다.

## Evaluate

- 완료 선언 전 `python3 scripts/agent-harness.py evaluate harness/plans/{issue}.json`을 실행합니다.
- 상태는 `PASS=0`, `FAIL=1`, `BLOCKED=2`, `REPLAN_REQUIRED=3`입니다.
- FAIL은 최소 수정 뒤 다시 검증하고, BLOCKED는 환경이나 oracle을 준비하며, REPLAN_REQUIRED는 manifest와 사람의 범위 검토로 돌아갑니다.
- 현재 base tip·merge-base·HEAD·plan·diff에 연결된 PASS evidence만 완료 근거입니다.
- DB·락·트랜잭션 검증은 H2가 아니라 MySQL Testcontainers로 실행합니다.
- 성공을 추측하지 않고 실제 명령 결과를 확인합니다.
- 실패와 성공을 모두 기능 로그의 `Attempt`에 추가합니다.
- 실패하면 원인을 설명한 뒤 Generate로 돌아가 최소 수정하고 재검증합니다.

## Explain

다음 질문에 답할 수 있을 때 완료합니다.

1. 어떤 불변식을 지키는가?
2. 트랜잭션은 어디서 시작하고 끝나는가?
3. 동일 사용자 요청이 동시에 오면 어떻게 되는가?
4. 중간 실패 시 무엇이 롤백되는가?
5. 다른 후보 대신 이 전략을 선택한 근거는 무엇인가?
6. 테스트·SQL·실행 결과로 어떻게 증명했는가?

검증이 끝난 변경은 pull request로만 `main`에 병합합니다. Phase 1A와 Phase 1B bootstrap은 repository owner가 수동 검토하고, Phase 1B canary 뒤에는 required checks를 모두 통과해야 합니다. 커밋·병합은 사용자가 요청한 범위에서만 수행합니다.

## 기능 로그

기능 로그는 작업 목록이 아니라 학습과 검증의 증거입니다.

```markdown
# point-charge — 로그

## Plan — 2026-07-12
- 불변식: 잔액과 충전 이력은 같은 트랜잭션에서 변경
- 검증: 정상/0 이하/없는 사용자/동시 충전

## Attempt 1 — 2026-07-12 ❌ FAIL
- 현상: 동시 요청에서 기대 잔액과 실제 잔액이 다름
- 원인: 조회와 갱신 사이에 다른 트랜잭션이 개입
- 다음: 사용자 행 비관적 락 적용

## Attempt 2 — 2026-07-12 ✅ PASS
- 결과: MySQL Testcontainers 동시성 테스트 통과
- 증거: 요청 수, 성공 수, 최종 잔액, 이력 수
- 배운 점: `@Transactional`만으로 동시 요청이 직렬화되지는 않음
```

단순 파일 생성 목록은 커밋에서 확인할 수 있으므로 로그에 반복하지 않습니다.
