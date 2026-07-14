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

1. 새 GitHub issue를 만들고 최신 `origin/main`에서 issue 전용 branch와 clean worktree를 만듭니다.
2. 제품 파일보다 먼저 `harness/plans/<issue>.json`을 작성합니다.
3. 다음 명령이 PASS한 뒤 허용 경로 안에서만 변경합니다.

       python3 scripts/agent-harness.py prepare harness/plans/<issue>.json

4. 완료를 말하기 전에 다음 명령을 실행합니다.

       python3 scripts/agent-harness.py evaluate harness/plans/<issue>.json

5. `build/harness/evaluation.json`의 identity와 현재 작업이 같고 state가 PASS일 때만 로컬 검증 완료라고 말합니다.

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

Phase 1A PR에는 기본 브랜치 판정기가 없고, Phase 1B PR에는 새 trusted workflow가 아직 기본 브랜치에 없습니다. 따라서 두 bootstrap PR 전체를 repository owner가 수동 검토합니다. hard gate는 Phase 1B merge와 canary 검증 뒤 일반 제품 PR부터 적용합니다.
