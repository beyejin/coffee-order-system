# Agent Harness

이 디렉터리는 에이전트 변경의 계획, 범위, 위험, 검증 증거를 fail-closed로 판정합니다.

## 현재 범위

현재 구현은 Phase 1A 로컬 trust core와 8개 도메인 oracle입니다. GitHub trusted/candidate workflow, branch protection, mutation benchmark는 아직 강제하지 않습니다. 도메인 oracle은 구조·API·migration·트랜잭션·동시성·비동기·다중 인스턴스 경계를 실제 파일과 테스트로 판정합니다.

## Issue 단위 오케스트레이션

메인 오케스트레이터와 서브에이전트의 실행 계약은
[`docs/ai/orchestration-policy.md`](../docs/ai/orchestration-policy.md)에 두고,
기계 판독 값은 [`orchestration-policy.json`](orchestration-policy.json)에 둡니다.

- 하나의 issue에는 `implementation`, `verification`, `qa`, `pr-review` 네 role slot만 둡니다.
- 하나의 issue는 하나의 branch와 하나의 PR로 끝까지 유지합니다.
- 동시에 실행하는 role은 최대 2개이며, 제품 파일을 쓰는 role은 `implementation` 하나뿐입니다.
- reviewer role은 read-only로 PASS/REJECT와 blocking finding만 반환합니다.
- repair loop은 최대 3회, PR review 재리뷰는 최대 2회입니다.
- repair loop 한도에 도달하면 `FAILED`에서 종료하며 자동으로 PASS나 merge를 만들지 않습니다.
- main orchestrator는 현재 HEAD에서 최종 `evaluate`를 다시 실행하고, merge guard 조건을 모두 만족하면 자동으로 병합합니다.

로컬 `agent-harness.py`는 범위와 완료 증거를 판정하고, `scripts/agent-publish.py`가 그 결과를 확인해 branch push와 Ready PR 생성을 실행합니다. `--merge`를 명시한 경우에만 required checks를 기다린 뒤 PR을 병합하고 PR `MERGED`·이슈 `CLOSED`를 검증합니다. 검증 PASS를 우회하거나 실패 결과를 자동으로 병합하는 경로는 없습니다.

## 상태

| 상태 | exit code | 의미 |
|---|---:|---|
| PASS | 0 | 현재 base tip, merge-base, HEAD, plan, diff에 필요한 검증이 성공 |
| FAIL | 1 | schema, 구현, test 또는 command가 결정론적으로 실패 |
| BLOCKED | 2 | Docker·Java 등 필수 실행 환경을 사용할 수 없어 판단 불가 |
| REPLAN_REQUIRED | 3 | 범위 밖 변경, 미분류 경로, 미선언 위험, plan·base 이동 |

## 도메인 oracle

다음 check는 `scripts/harness-oracles.py`가 실행하며, 미구현 상태를 PASS로 대체하지 않습니다.

- `oracle.architecture`: Java import 경계와 순환 의존성
- `oracle.api-contract`: controller route, 공통 응답·오류 contract, API 회귀 테스트
- `oracle.migration-fresh`: V1부터 최신 migration까지 fresh DB 적용
- `oracle.migration-upgrade`: 기존 데이터가 있는 V5 DB의 최신 migration upgrade
- `oracle.transaction`: 충전·주문 원자성과 rollback 통합 테스트
- `oracle.cross-domain-concurrency`: 충전과 주문 혼합 동시성 불변식
- `oracle.async-isolation`: 커밋 후 외부 전송과 응답 격리
- `oracle.multi-instance`: Compose 두 인스턴스와 공유 MySQL·Redis smoke

## 작업 순서

`Plan → Issue → Branch → Manifest → Prepare → Generate → Verify → Commit → Evaluate → Publish → Explain` 순서를 따릅니다.

읽기 전용 질의를 제외하고 저장소를 변경하는 모든 작업에 이 순서를 적용합니다.

1. 새 GitHub issue를 만들고 최신 `origin/main`에서 issue 전용 branch와 clean worktree를 만듭니다.
2. plan 외 저장소 파일보다 먼저 `harness/plans/issue-<issue>-<slug>.json`을 작성합니다. 숫자만 있는 `harness/plans/<issue>.json`은 기존 manifest 호환용입니다.
3. 다음 명령이 PASS한 뒤 허용 경로 안에서만 변경합니다.

       python3 scripts/agent-harness.py prepare harness/plans/issue-<issue>-<slug>.json

4. 변경 범위 테스트와 정적 검사를 통과한 파일만 커밋합니다.
5. clean한 최종 커밋 HEAD에서 다음 명령을 실행합니다. 시작이나 종료 시 dirty 경로가 생기면 `REPLAN_REQUIRED`의 `git.clean`으로 중단합니다.

       python3 scripts/agent-harness.py evaluate harness/plans/issue-<issue>-<slug>.json

6. `build/harness/evaluation.json`의 identity와 현재 작업이 같고 state가 PASS인지 확인합니다.
7. branch를 push하고 `main` 대상 Ready for review PR을 생성합니다.
8. `gh pr view --json url,isDraft,baseRefName,headRefName,headRefOid`로 `url` 존재, `isDraft=false`, `baseRefName=main`, 현재 branch와 `headRefName` 일치, 현재 로컬 HEAD와 `headRefOid` 일치를 확인합니다.
9. `git rev-parse HEAD`와 `git rev-parse origin/$(git branch --show-current)`가 같은지 확인합니다.
10. PASS evidence와 검증된 PR URL이 모두 있을 때 기본 작업 완료를 보고합니다.

Draft PR은 사용자가 명시적으로 요청한 경우에만 사용합니다. 사용자가 명시적으로 `local-only` 또는 push 금지를 요청하면 Publish를 생략하고 branch·commit과 원격 미게시 상태를 보고합니다.

사용자의 일반 변경 요청은 Commit과 Publish까지 포함합니다. Merge는 별도 요청이 있을 때만 수행합니다.

11. PR을 만들거나 갱신하려면 다음 명령을 실행합니다.

       python3 scripts/agent-publish.py harness/plans/issue-<issue>-<slug>.json

12. PR 병합과 이슈 완료까지 자동화할 때만 `--merge`를 명시합니다.

       python3 scripts/agent-publish.py harness/plans/issue-<issue>-<slug>.json --merge

## Manifest 규칙

- 필수 field는 issue, targetBranch, objective, allowedPaths, acceptanceCriteria, declaredRisks, contractChanges, nonGoals입니다.
- targetBranch는 main만 허용합니다.
- branch issue 번호와 manifest issue가 같아야 합니다.
- allowedPaths는 정확한 파일 또는 마지막이 `/**`인 좁은 subtree만 허용합니다.
- 선택한 plan 외 dirty 변경이 있는 상태에서 prepare하지 않습니다.
- contractChanges의 각 값은 `'<정확한 경로> v<양의 정수>'` 형식이어야 합니다.
- 보호 경로를 바꾸는 plan은 해당 경로와 정확히 일치하는 versioned contractChanges 선언을 포함해야 합니다.

## Evidence

evaluation.json은 baseTipSha, mergeBaseSha, candidateHeadSha, testedRevisionSha, planHash, diffHash, declaredRisks, detectedRisks, changedPaths, checks와 최종 state를 기록합니다. commit으로 HEAD가 바뀌거나 plan·base·diff가 바뀌면 이전 evidence는 완료 근거가 아닙니다.

기본 gate는 `scope.allowed-paths`, `risk.classification`, `risk.declaration`, `trust-root.contract`, `harness.unit`, `gradle.test`, 8개 도메인 oracle, `evidence.freshness`입니다.

Phase 1A에는 별도 stale evidence 소비 명령이 없습니다. 완료 직전에 evaluate를 다시 실행하고 현재 Git identity와 JSON을 대조합니다. Phase 1B CI는 PR event에서 identity를 재구성해 오래된 artifact 사용을 기계적으로 거부합니다.

## Bootstrap 예외

과거 issue #4의 로컬 `main` 동기화 PR은 원격에 게시되지 않았던 기존 검증 커밋을 공개하는 일회성 복구였습니다. 당시에는 도메인 oracle이 아직 없었으므로 제한된 예외로 Publish했지만, issue #4 PR merge와 동시에 만료되었습니다. 현재 작업은 모든 필수 oracle과 `evidence.freshness`가 PASS하고 FAIL과 REPLAN_REQUIRED가 없을 때만 Publish할 수 있습니다. 이 조건은 하네스 PASS나 작업 완료를 뜻하지 않으며, 실제 PR·이슈 상태도 별도로 확인합니다.

Phase 1A PR에는 기본 브랜치 판정기가 없고, Phase 1B PR에는 새 trusted workflow가 아직 기본 브랜치에 없습니다. 따라서 두 bootstrap PR은 trusted 검증이 준비될 때까지 자동 병합 대상에서 제외합니다. trusted workflow와 canary 검증이 기본 브랜치에 반영된 뒤 일반 제품 PR에 자동 병합을 적용합니다.
