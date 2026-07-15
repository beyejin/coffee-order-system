# Agent Harness

이 디렉터리는 에이전트 변경의 계획, 범위, 위험, 검증 증거를 fail-closed로 판정합니다.

## 현재 범위

현재 구현은 Phase 1A 로컬 trust core입니다. GitHub trusted/candidate workflow, branch protection, 도메인별 oracle와 mutation benchmark는 아직 강제하지 않습니다. 해당 검사가 필요한 변경은 PASS로 대체하지 않고 BLOCKED로 남깁니다.

## 상태

| 상태 | exit code | 의미 |
|---|---:|---|
| PASS | 0 | 현재 base tip, merge-base, HEAD, plan, diff에 필요한 검증이 성공 |
| FAIL | 1 | schema, 구현, test 또는 command가 결정론적으로 실패 |
| BLOCKED | 2 | Docker, Java 또는 아직 구현되지 않은 oracle 때문에 판단 불가 |
| REPLAN_REQUIRED | 3 | 범위 밖 변경, 미분류 경로, 미선언 위험, plan·base 이동 |

## 작업 순서

`Plan → Issue → Branch → Manifest → Prepare → Generate → Verify → Commit → Evaluate → Publish → Explain` 순서를 따릅니다.

읽기 전용 질의를 제외하고 저장소를 변경하는 모든 작업에 이 순서를 적용합니다.

1. 새 GitHub issue를 만들고 최신 `origin/main`에서 issue 전용 branch와 clean worktree를 만듭니다.
2. plan 외 저장소 파일보다 먼저 `harness/plans/<issue>.json`을 작성합니다.
3. 다음 명령이 PASS한 뒤 허용 경로 안에서만 변경합니다.

       python3 scripts/agent-harness.py prepare harness/plans/<issue>.json

4. 변경 범위 테스트와 정적 검사를 통과한 파일만 커밋합니다.
5. clean한 최종 커밋 HEAD에서 다음 명령을 실행합니다. 시작이나 종료 시 dirty 경로가 생기면 `REPLAN_REQUIRED`의 `git.clean`으로 중단합니다.

       python3 scripts/agent-harness.py evaluate harness/plans/<issue>.json

6. `build/harness/evaluation.json`의 identity와 현재 작업이 같고 state가 PASS인지 확인합니다.
7. branch를 push하고 `main` 대상 Ready for review PR을 생성합니다.
8. `gh pr view --json url,isDraft,baseRefName,headRefName,headRefOid`로 `url` 존재, `isDraft=false`, `baseRefName=main`, 현재 branch와 `headRefName` 일치, 현재 로컬 HEAD와 `headRefOid` 일치를 확인합니다.
9. `git rev-parse HEAD`와 `git rev-parse origin/$(git branch --show-current)`가 같은지 확인합니다.
10. PASS evidence와 검증된 PR URL이 모두 있을 때 기본 작업 완료를 보고합니다.

Draft PR은 사용자가 명시적으로 요청한 경우에만 사용합니다. 사용자가 명시적으로 `local-only` 또는 push 금지를 요청하면 Publish를 생략하고 branch·commit과 원격 미게시 상태를 보고합니다.

사용자의 일반 변경 요청은 Commit과 Publish까지 포함합니다. Merge는 별도 요청이 있을 때만 수행합니다.

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

Phase 1A에는 별도 stale evidence 소비 명령이 없습니다. 완료 직전에 evaluate를 다시 실행하고 현재 Git identity와 JSON을 대조합니다. Phase 1B CI는 PR event에서 identity를 재구성해 오래된 artifact 사용을 기계적으로 거부합니다.

## Bootstrap 예외

수동 Bootstrap 예외는 아래 issue #4 한 건에만 적용합니다. 후속 Phase 1B trusted workflow와 canary PR은 이 예외를 승계하지 않고 별도 manifest와 required checks로 검증합니다.

issue #4의 로컬 `main` 동기화 PR은 원격에 게시되지 않았던 기존 검증 커밋을 공개하는 일회성 복구입니다. evaluate는 생략하지 않으며 모든 비-`oracle.*` check가 PASS이고 BLOCKED check가 미구현 `oracle.*`뿐이며 FAIL과 REPLAN_REQUIRED가 없을 때만 repository owner 수동 검토를 위해 Publish할 수 있습니다. 최소한 `scope.allowed-paths`, `risk.classification`, `risk.declaration`, `trust-root.contract`, `harness.unit`, `gradle.test`, `evidence.freshness`는 PASS여야 합니다. 이 예외는 Publish만 허용할 뿐 하네스 PASS나 작업 완료를 뜻하지 않으며, issue #4 PR merge와 동시에 만료되어 재사용할 수 없습니다.
