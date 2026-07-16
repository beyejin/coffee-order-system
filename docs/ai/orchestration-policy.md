# Issue 단위 4-role loop engineering 계약

이 문서는 하나의 GitHub issue를 하나의 작업 단위로 처리할 때 main orchestrator와
네 개의 고정 role이 지켜야 하는 실행 계약이다. agent spawning runtime은 구현하지
않으며, 실행 순서·권한·handoff 형식과 `scripts/agent-publish.py`를 통한 GitHub
provider 연결을 정의한다.

기계 판독 정본은 [`harness/orchestration-policy.json`](../../harness/orchestration-policy.json)이다.
이 문서와 JSON은 같은 계약의 사람용·기계용 표현이므로 값이 달라지면 둘 다 같은
변경에서 갱신하고 테스트로 확인한다.

## 1. 범위와 role slot

한 issue는 하나의 branch와 하나의 PR로 처리하고, 아래 네 role만 할당한다. main
orchestrator와 사용자는 role slot에 포함하지 않는다.

| role | 담당 단계 | 제품 코드·문서 쓰기 | 결과 | 승인 권한 |
|---|---|---|---|---|
| `implementation` | `IMPLEMENT`, `FIX_LOOP` | `manifest.allowedPaths` 안에서만 가능하며 유일한 writer | `PASS`, `FAIL`, `BLOCKED`, `REPLAN_REQUIRED` | 없음 |
| `verification` | `VERIFY` | 불가, read-only | `PASS`, `REJECT` | 없음 |
| `qa` | `QA` | 불가, read-only | `PASS`, `REJECT` | 없음 |
| `pr-review` | `PR_REVIEW` | 불가, read-only | `PASS`, `REJECT` | `PASS`/`REJECT` 결정 |

이슈당 최대 `4`개 role slot, 동시 실행은 최대 `2`개 role slot이다. 병렬 실행은
서로 독립된 read-only 검사에만 허용하며, 공유 DB·Compose·evidence 파일을
사용하는 검사는 순차 실행한다. 네 role의 이름과 권한은 고정하며 임의의
coordinator, reviewer, writer role을 추가하지 않는다. repair loop에서 다시
구현하더라도 같은 issue의 implementation writer identity를 유지한다. 같은
issue의 writer는 `1`개만 허용한다.

`implementation`을 제외한 세 reviewer는 코드나 문서를 수정하지 않는다.
reviewer는 고정 handoff schema로 `PASS` 또는 `REJECT`를 반환하고, `REJECT`이면
blocking finding을 함께 남긴다.

## VCS capability matrix

다음 표는 다섯 actor가 이 workflow에서 수행할 수 있는 VCS 작업을 정의한다.

| actor | repo read | product file write | local commit | branch push | PR merge |
|---|---:|---:|---:|---:|---:|
| `implementation` | Yes | Yes (`manifest.allowedPaths`) | Yes | No | No |
| `verification` | Yes | No | No | No | No |
| `qa` | Yes | No | No | No | No |
| `pr-review` | Yes | No | No | No | No |
| `main-orchestrator` | Yes | No | No | Yes | Yes |

JSON의 `vcsCapabilities`는 workflow capability contract를 설명한다. 실제 GitHub
credentials는 branch push와 PR merge를 포함한 최종 enforcement layer로 남는다.

## 2. main orchestrator의 자동 merge 권한

main orchestrator가 맡는 일은 다음 일곱 가지뿐이다.

1. `PLAN`: 목적, 불변식, 범위와 완료 조건을 정리한다.
2. `ISSUE`: 확정한 계획으로 GitHub issue를 만든다.
3. `MANIFEST`: issue manifest와 `allowedPaths`·completion contract를 고정한다.
4. `ASSIGN`: 네 role slot 중 필요한 role을 할당하고 순서를 관리한다.
5. `RETRY`: `FAIL`과 reviewer의 blocking finding을 `FIX_LOOP`으로 라우팅한다.
6. `FINAL_EVALUATE`: 현재 candidate HEAD에서 completion contract를 다시 실행한다.
7. `AUTO_MERGE`: merge guard를 확인한 뒤 검증된 candidate를 자동으로 병합한다.

main orchestrator는 `IMPLEMENT`, `VERIFY`, `QA`, `PR_REVIEW`의 결과를 대신
만들지 않는다. `FINAL_EVALUATE`의 `PASS`와 merge guard의 모든 조건이 충족되면
별도 승인 없이 `AUTO_MERGE`를 수행한다.

## 3. 고정 상태 머신

정상 흐름은 다음 순서를 따른다.

```text
PLAN -> ASSIGN -> IMPLEMENT -> VERIFY -> QA -> PR_REVIEW -> FIX_LOOP -> FINAL_EVALUATE -> AUTO_MERGE
```

`PR_REVIEW`가 `REJECT`를 반환하면 `FIX_LOOP`에서 blocking finding을 같은
implementation writer에게 전달한다. 남은 finding이 없으면 `FIX_LOOP`에서
`FINAL_EVALUATE`로 진행한다. finding이 있고 repair loop 한도 안이면
`FIX_LOOP -> IMPLEMENT`로 돌아가며, 이후 `VERIFY -> QA -> PR_REVIEW`를 다시
거친다. 한도를 넘긴 결과는 별도 승인 단계로 보내지 않고 `FAILED`에서 종료한다.
`FINAL_EVALUATE == PASS`일 때만
`AUTO_MERGE`로 진입한다.

예외 전이는 다음처럼 고정한다.

| 신호 | 허용되는 발생 단계 | 다음 상태 | 의미 |
|---|---|---|---|
| `FAIL` | `IMPLEMENT`, `VERIFY`, `QA`, `PR_REVIEW`, `FINAL_EVALUATE` | `FIX_LOOP` 또는 `FAILED` | repair loop 한도 전에는 수정으로, 한도 초과 시 병합하지 않고 종료한다. |
| `BLOCKED` | `PLAN`부터 `FINAL_EVALUATE`까지의 활성 단계 | `PLAN` | 자동 실행기가 환경·oracle·권한 blocker를 해소한 뒤 다시 계획한다. |
| `REPLAN_REQUIRED` | `PLAN`부터 `FINAL_EVALUATE`까지의 활성 단계 | `PLAN` | 자동 실행기가 범위·manifest·기준점을 갱신한 뒤 다시 할당한다. |

`AUTO_MERGE`에 들어가려면 `FINAL_EVALUATE == PASS`, 현재 candidate HEAD와
검증한 HEAD의 일치, `allowedPaths` 준수, 모든 필수 handoff와 completion
contract 증거가 필요하다. `FAILED`는 repair loop 한도 초과를 알리는 비병합
종료 상태이며 자동 병합하지 않는다.

## 4. 실행 한도

| 항목 | 제한 |
|---|---:|
| issue당 role slot | `4` |
| 동시 실행 role slot | `2` |
| repair loop | 최대 `3`회 |
| PR review 재리뷰 | 최대 `2`회 (최초 review 이후, 총 review 시도는 최대 3회) |
| issue당 writer | `1`개 |

repair loop 횟수는 reviewer의 blocking finding을 구현 writer가 수정하는 순환의
횟수다. 재리뷰는 같은 PR review role이 수정된 동일 candidate HEAD를 다시 보는
횟수이며, 한도를 초과하면 자동으로 PASS를 만들지 않는다.

## 5. 결과 일관성의 single source of truth

다음 다섯 항목은 issue 결과를 판정하는 single source of truth다. handoff에 값을
복사해 넣더라도 원본과 일치하는지 확인하며, reviewer의 주장만으로 원본을
덮어쓰지 않는다.

| 항목 | 정본 | 규칙 |
|---|---|---|
| `manifest` | `harness/plans/issue-{issue}-<slug>.json` | issue, 목적, 위험, 범위와 계약 변경을 고정한다. 기존 숫자-only 경로도 하위 호환으로 읽는다. |
| `candidate HEAD` | 현재 검증 대상 branch의 HEAD | HEAD가 바뀌면 이전 verification·QA·PR review·final evaluation 증거는 무효다. |
| `allowedPaths` | `manifest.allowedPaths` | implementation의 유일한 제품 쓰기 범위이며, reviewer는 이 범위를 수정할 수 없다. |
| `completion contract` | manifest의 `acceptanceCriteria`와 정책의 필수 증거 조건 | 완료 선언과 `AUTO_MERGE` 진입 조건을 결정한다. |
| 고정 `handoff schema` | 이 문서의 JSON `handoffSchema` | role 간 전달 필드와 결과값을 임의로 바꾸지 않는다. |

모든 handoff는 issue, manifest, candidate HEAD, `allowedPaths`, completion
contract 참조를 포함해야 한다. candidate HEAD·manifest·diff가 달라지면 main
orchestrator는 final evaluation을 다시 실행해야 한다.

## 6. 고정 handoff schema

모든 role은 다음 필드를 가진 하나의 handoff를 반환한다. 앞의 아홉 필드는 사용자가
읽는 고정 결과 형식이며, 나머지는 정합성 검증을 위한 provenance 필드다.

| 필드 | 형식 | 규칙 |
|---|---|---|
| `role` | 고정 네 role 중 하나 | 할당받은 role과 일치해야 한다. |
| `issue` | integer | 현재 GitHub issue 번호 |
| `candidateHead` | SHA | 결과를 만든 candidate HEAD |
| `status` | 고정 결과 중 하나 | `PASS`, `REJECT`, `FAIL`, `BLOCKED`, `REPLAN_REQUIRED` |
| `changedPaths` | string 배열 | 이번 role이 확인하거나 변경한 경로 |
| `commands` | string 배열 | 실행한 검증 명령 |
| `evidence` | string 배열 | 실행 명령, 로그 또는 검증 증거 참조 |
| `findings` | finding 객체 배열 | reviewer가 `REJECT`할 때 blocking finding을 포함한다. |
| `nextAction` | string | 다음 role 또는 자동 실행기에게 넘길 한 가지 행동 |
| `manifest` | manifest 경로 | `harness/plans/issue-{issue}-<slug>.json` (기존 숫자-only 경로 하위 호환) |
| `allowedPaths` | string 배열 | manifest 값과 완전히 같아야 한다. |
| `completionContract` | 참조 또는 hash | manifest acceptance criteria와 정책 증거 조건 |
| `state` | 고정 상태 중 하나 | handoff를 만든 단계 |
| `nextState` | 고정 상태 중 하나 | 정책 전이에 맞는 다음 상태 |

각 blocking finding은 최소 `id`, `severity`, `path`, `message`를 가진다.
verification·QA·PR review는 `PASS`/`REJECT`만 반환하고, `REJECT`에는 blocking
finding을 `findings`에 남긴다. main orchestrator는 이를 입력으로만 사용하고
`FINAL_EVALUATE`를 독립적으로 재실행한다.

## 7. 적용 범위

이 변경은 실행 계약과 machine-readable policy를 정의한다. 자동 merge는
`FINAL_EVALUATE`와 merge guard를 통과한 경우에만 허용하며, 실제 PR provider 호출은
`scripts/agent-publish.py`와 main orchestrator runtime이 담당한다. 임의의 role 생성은 범위에 포함하지 않는다.
저장소의 한국어·문서 우선·과도한 추상화 금지 규칙에 따라 정책을 먼저 문서화하고,
구현은 지정된 `allowedPaths`의 유일한 writer에게만 맡긴다.
