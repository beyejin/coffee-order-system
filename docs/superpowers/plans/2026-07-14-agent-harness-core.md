# Agent Harness Local Trust Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `origin/main`의 깨끗한 기준선에서 plan manifest, 작업 범위, Git 기준점, 위험 분류, 실행 증거를 fail-closed로 판정하는 로컬 하네스 코어를 만든다.

**Architecture:** Python 표준 라이브러리만 사용하는 `scripts/agent-harness.py`를 단일 판정기로 두고, JSON manifest와 risk policy를 입력으로 받는다. `prepare`는 원격 `main`의 tip과 merge-base를 잠그고, `evaluate`는 committed·staged·unstaged·untracked 전체 diff를 다시 계산해 범위·위험·필수 검증·증거 freshness를 판정한다. 이 계획은 독립 실행 가능한 Phase 1A이며, trusted/candidate CI와 GitHub branch protection은 별도 Phase 1B 계획으로 분리한다.

**Tech Stack:** Python 3.13+ 표준 라이브러리, Git CLI, Java 17, Gradle Wrapper, Docker, Python `unittest`

## Global Constraints

- 모든 설명·문서·커밋 메시지는 한국어로 작성한다.
- 현재 dirty `refactor/1-package-structure` worktree의 변경을 commit, stash, 삭제, 구현 기준선으로 사용하지 않는다. 단, 사용자 승인된 `docs/superpowers/specs/2026-07-14-agent-harness-hard-gate-design.md`와 이 구현계획 두 문서만 bootstrap 전달 산출물로 byte-for-byte 복사한다.
- 실행 시 `superpowers:using-git-worktrees`를 먼저 사용하고, 최신 `origin/main`에서 새 issue 전용 worktree를 만든다.
- Phase 1A 전체 PR과 후속 Phase 1B 전체 PR은 각 PR이 도입하는 trust root를 아직 기본 브랜치 gate가 검증할 수 없으므로 repository owner가 파일·권한·테스트를 수동 검토한다. hard gate는 Phase 1B merge와 canary 검증 뒤부터 일반 제품 PR에 적용한다.
- 외부 Python package, JSON Schema engine, Redis, Kafka, Git hook을 추가하지 않는다.
- 상태와 exit code는 `PASS=0`, `FAIL=1`, `BLOCKED=2`, `REPLAN_REQUIRED=3`으로 고정한다.
- 로컬 lock에는 `baseTipSha`와 `mergeBaseSha`를 모두 기록한다. merge-base가 같아도 `origin/main` tip이 움직이면 `REPLAN_REQUIRED`다.
- plan의 `allowedPaths` 문법은 정확한 파일 경로 또는 마지막이 `/**`인 subtree만 허용한다. `src/**`, `docs/**`, `harness/**`, `scripts/**`, `.github/**`, `**`는 plan에서 금지한다.
- 선택한 `harness/plans/<issue>.json`만 scope와 risk classification에서 암묵적으로 제외한다.
- `./gradlew clean test --console plain`은 evaluate마다 실행한다. Docker 또는 Java를 사용할 수 없으면 PASS가 아니라 BLOCKED다.
- Python test 실행은 항상 `PYTHONDONTWRITEBYTECODE=1`을 설정해 `__pycache__`가 diff를 오염시키지 않게 한다.
- `build/harness/plan.lock.json`과 `build/harness/evaluation.json`은 기존 `.gitignore`의 `build/` 규칙을 사용하며 커밋하지 않는다.
- `.github/**`, `src/AGENTS.md`, `scripts/check-doc-context.py`, Java 제품 코드와 Flyway migration은 이 계획에서 수정하지 않는다.
- Phase 1A 완료를 전체 하네스 완료로 표현하지 않는다. Phase 1B와 도메인 oracle이 없는 위험은 BLOCKED로 남긴다.

---

## Scope Split

승인 설계는 로컬 판정기, GitHub trusted gate, candidate runtime gate, 여섯 종류의 제품 oracle, mutation benchmark를 함께 설명한다. 이를 한 PR로 구현하면 바로 방지하려는 “작업 범위 혼합”을 다시 만든다. 이 계획의 완료 범위는 다음뿐이다.

- manifest schema와 branch/issue 일치
- `baseTipSha`·`mergeBaseSha`·plan hash lock
- committed·staged·unstaged·untracked·rename 경로 수집
- allowedPaths, 미분류 경로, 미선언 위험 판정
- trust-root 변경의 `contractChanges` 선언 확인
- Python harness unit test와 전체 Gradle test 실행
- 최소 `evaluation.json`과 evaluate 실행 중 identity freshness 차단; 완료 전 evaluate 재실행 의무
- `AGENTS.md`에서 하네스 사용법으로 얇게 라우팅
- `docs/rules/workflow.md`와 `docs/rules/conventions.md`를 manifest·Prepare·4상태 계약에 동기화

Phase 1A 위험 감지는 경로 기반이다. 승인 설계의 Java import graph 분석은 architecture oracle과 함께 Phase 2A에서 추가하며, 그 전에는 알려진 `common`, `menu`, `order`, `point` 경계를 보수적으로 여러 위험에 매핑하고 새 최상위 제품 경로를 미분류로 REPLAN_REQUIRED 처리한다.

다음 항목은 후속 계획의 선행 조건으로 남는다.

1. Phase 1B: `integrity --ci`, `evaluate --ci`, `trusted-harness-gate.yml`, `quality-gate.yml`, owner hash 승인, canary PR, required checks
2. Phase 2A: architecture, API, migration, transaction, concurrency, async, multi-instance oracle를 각각 trust-root PR로 먼저 도입. 새 gate는 자기 PR을 단독 신뢰하지 않고 owner 승인을 거쳐 다음 PR부터 trusted 기준이 됨
3. Phase 2B: 모든 관련 oracle이 trusted 기준에 들어온 뒤 구조, API, migration, concurrency, async, multi-instance 제품 결함을 서로 다른 plan·PR로 수정
4. Phase 3: JUnit·Compose artifact와 PR template
5. Phase 4: 15개 mutation benchmark

## Runtime-Bound Issue Number

`ISSUE_NUMBER`는 사람이 채울 문서 표식이 아니다. Task 1 Step 1의 `gh issue create`가 반환한 URL 마지막 숫자를 같은 shell session에서 추출한 실행 값이다. 이후 경로 `harness/plans/${ISSUE_NUMBER}.json`과 브랜치 `feature/${ISSUE_NUMBER}-agent-harness-core`에는 그 숫자를 그대로 사용한다. 이슈 생성 뒤 shell이 끊기면 다음 명령으로 복구한다.

```bash
ISSUE_NUMBER=$(gh issue list --state open --search '에이전트 하네스 로컬 trust core in:title' --json number --jq '.[0].number')
test -n "$ISSUE_NUMBER"
```

## File Map

| 경로 | 변경 | 단일 책임 |
|---|---|---|
| `docs/superpowers/specs/2026-07-14-agent-harness-hard-gate-design.md` | 생성 | 사용자 승인 설계와 신뢰 경계의 저장소 정본 |
| `docs/superpowers/plans/2026-07-14-agent-harness-core.md` | 생성 | Phase 1A 실행 순서, test, commit, 완료 기준 |
| `harness/plans/${ISSUE_NUMBER}.json` | 생성 | 이번 bootstrap PR의 목적, 허용 경로, 성공 조건, 위험과 비목표 고정 |
| `harness/plan.example.json` | 생성 | validator를 통과하는 좁은 manifest 예시 |
| `harness/risk-policy.json` | 생성 | 경로→위험, 위험→필수 check, 보호 경로의 신뢰 정본 |
| `harness/tests/test_agent_harness.py` | 생성 | 표준 `unittest`와 임시 Git 원격을 이용한 판정기 회귀 테스트 |
| `scripts/agent-harness.py` | 생성 | manifest, Git, scope, risk, command, evidence를 판정하는 CLI |
| `harness/README.md` | 생성 | Phase 1A 상태·명령·bootstrap 예외·증거·후속 범위 설명 |
| `AGENTS.md` | 수정 | 상세 규칙을 복제하지 않고 하네스 README와 두 명령으로 라우팅 |
| `docs/rules/workflow.md` | 수정 | 자유 형식 Plan을 manifest·Prepare·4상태 전이로 동기화 |
| `docs/rules/conventions.md` | 수정 | clean base, issue branch, allowedPaths, trust-root와 migration 규칙 |

### Stable Interfaces

```python
class State(IntEnum):
    PASS = 0
    FAIL = 1
    BLOCKED = 2
    REPLAN_REQUIRED = 3


@dataclass(frozen=True)
class Plan:
    issue: int
    target_branch: str
    objective: str
    allowed_paths: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    declared_risks: tuple[str, ...]
    contract_changes: tuple[str, ...]
    non_goals: tuple[str, ...]
    relative_path: str
    plan_hash: str


@dataclass(frozen=True)
class GitContext:
    branch: str
    target_branch: str
    base_tip_sha: str
    merge_base_sha: str
    candidate_head_sha: str
    tested_revision_sha: str


def contract_change_path(declaration: str) -> str:
    """version이 붙은 정확한 contractChanges 경로를 반환하거나 REPLAN_REQUIRED를 발생시킨다."""


def parse_plan(raw: bytes, *, relative_path: str, known_risks: frozenset[str]) -> Plan:
    """정확한 8개 manifest 필드만 검증하고 raw bytes SHA-256을 보존한다."""


def resolve_local_git_context(root: Path, plan: Plan) -> GitContext:
    """origin/main을 fetch하고 base tip, merge-base, 현재 HEAD를 직접 계산한다."""


def prepare(
    root: Path,
    plan_path: Path,
    *,
    preflight: Callable[[Path], tuple[CheckResult, ...]] = run_prepare_preflight,
) -> tuple[State, tuple[CheckResult, ...]]:
    """plan 외 dirty 경로가 없을 때 원자적으로 plan.lock.json을 쓴다."""


def evaluate(
    root: Path,
    plan_path: Path,
    *,
    check_runner: Callable[[Path, tuple[str, ...]], tuple[CheckResult, ...]] = run_required_checks,
) -> Evaluation:
    """현재 diff를 판정하고 모든 비정상 상태에서도 가능한 evidence를 기록한다."""
```

위 docstring은 구현 시 그대로 유지한다. `prepare()[0]`과 `evaluate().state`가 각각 CLI exit code다. 예상 가능한 판정은 `HarnessViolation(state, check_id, reason)`으로 전달하고, 예상하지 못한 예외는 `FAIL / harness.internal`로 변환한다.

---

### Task 1: Issue, Clean Worktree, Bootstrap Manifest

**Files:**
- Create: `docs/superpowers/specs/2026-07-14-agent-harness-hard-gate-design.md`
- Create: `docs/superpowers/plans/2026-07-14-agent-harness-core.md`
- Create: `harness/plans/${ISSUE_NUMBER}.json`

**Interfaces:**
- Consumes: GitHub CLI 인증, `origin/main`, 승인된 설계의 Phase 0·Phase 1A 범위
- Produces: `ISSUE_NUMBER`, `feature/${ISSUE_NUMBER}-agent-harness-core`, 이후 모든 task의 유일한 manifest

- [ ] **Step 1: 새 이슈를 만들고 실행 값을 고정한다**

Run:

```bash
ISSUE_URL=$(gh issue create \
  --title "에이전트 하네스 로컬 trust core 도입" \
  --body $'## 목적\norigin/main 기준의 로컬 fail-closed 하네스 코어를 도입한다.\n\n## 작업 범위\n- 승인 설계와 구현계획 추적\n- manifest와 branch/issue 검증\n- base tip, merge-base, plan hash 잠금\n- 전체 diff 범위와 위험 분류\n- Python/Gradle 실행 증거\n- AGENTS.md와 workflow/conventions 동기화\n\n## 알려진 기준선 결함\n- 패키지 의존, API 오류 계약, V5 시간대 전제, 혼합 동시성, async 응답 격리, 다중 인스턴스 경계 oracle가 아직 없다.\n- 통과하는 기존 테스트만으로 green product baseline을 선언하지 않는다.\n\n## 제외 범위\n- GitHub trusted/candidate workflow\n- branch protection\n- 제품 Java와 migration 수정\n- 도메인 oracle와 mutation benchmark\n\n## 완료 조건\n- 하네스 unittest 통과\n- 범위 밖·미분류·미선언 위험은 REPLAN_REQUIRED\n- 환경 부재는 BLOCKED\n- 현재 identity에 묶인 evaluation.json 생성')
ISSUE_NUMBER=${ISSUE_URL##*/}
test "$ISSUE_NUMBER" -ge 1
echo "$ISSUE_URL"
```

Expected: 새 issue URL 한 줄과 숫자 `ISSUE_NUMBER`.

- [ ] **Step 2: `superpowers:using-git-worktrees`로 격리 worktree를 만든다**

`superpowers:using-git-worktrees`를 호출해 기존 worktree 위치와 repository 관례를 먼저 확인하고, native worktree 지원이 있으면 이를 우선한다. branch는 정확히 `feature/${ISSUE_NUMBER}-agent-harness-core`, base는 최신 `origin/main`으로 전달한다. 스킬이 반환한 절대 경로를 `WORKTREE`에 넣은 뒤 다음만 검증한다.

```bash
cd "$WORKTREE"
test "$(git branch --show-current)" = "feature/${ISSUE_NUMBER}-agent-harness-core"
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -z "$(git status --porcelain)"
```

Expected: 세 `test` 명령이 exit 0. 기존 `refactor/1-package-structure` worktree 상태는 변하지 않는다. 스킬이 격리 위치를 만들지 못하면 여기서 BLOCKED로 멈추고 임의 sibling 경로를 만들지 않는다.

- [ ] **Step 3: clean base의 환경과 기존 전체 테스트를 먼저 검증한다**

Run:

```bash
python3 -c 'import sys; assert sys.version_info >= (3, 13), sys.version'
java -version
docker info
./gradlew -q javaToolchains
./gradlew clean test --console plain
BASELINE_SHA=$(git rev-parse HEAD)
gh issue comment "$ISSUE_NUMBER" --body "Phase 0 clean baseline: ${BASELINE_SHA} / Python 3.13+ / Java 17 toolchain / Docker / ./gradlew clean test PASS. 알려진 oracle 공백은 issue 본문과 승인 설계에 유지한다."
```

Expected: `javaToolchains` 출력에 `Language Version: 17`, 전체 Gradle test PASS, issue에 base SHA가 기록된다. Docker daemon, Java 17 toolchain, Gradle wrapper 중 하나가 준비되지 않았거나 기존 test가 실패하면 제품·하네스 파일을 만들지 말고 BLOCKED 또는 FAIL 결과를 issue에 기록한 뒤 중단한다.

- [ ] **Step 4: 승인 문서와 부모 디렉터리를 clean worktree로 옮긴다**

Run:

```bash
mkdir -p docs/superpowers/specs docs/superpowers/plans harness/plans
```

원본 worktree의 다음 두 파일을 각각 읽고, `apply_patch`의 `*** Add File`로 `$WORKTREE`의 같은 상대 경로에 byte-for-byte 생성한다. shell copy, Python writer, 원본 파일 수정은 사용하지 않는다.

```text
/Users/han-yejin/IdeaProjects/coffee-order-system/docs/superpowers/specs/2026-07-14-agent-harness-hard-gate-design.md
/Users/han-yejin/IdeaProjects/coffee-order-system/docs/superpowers/plans/2026-07-14-agent-harness-core.md
```

Run:

```bash
shasum -a 256 \
  /Users/han-yejin/IdeaProjects/coffee-order-system/docs/superpowers/specs/2026-07-14-agent-harness-hard-gate-design.md \
  docs/superpowers/specs/2026-07-14-agent-harness-hard-gate-design.md
shasum -a 256 \
  /Users/han-yejin/IdeaProjects/coffee-order-system/docs/superpowers/plans/2026-07-14-agent-harness-core.md \
  docs/superpowers/plans/2026-07-14-agent-harness-core.md
```

Expected: 각 쌍의 SHA-256이 같다.

- [ ] **Step 5: manifest를 제품 파일보다 먼저 작성한다**

`apply_patch`로 `harness/plans/${ISSUE_NUMBER}.json`을 생성한다. 파일 경로와 아래 JSON의 `issue` 값에는 Step 1에서 얻은 같은 정수를 넣는다. 나머지 문자열과 배열 순서는 그대로 사용한다.

```json
{
  "issue": ISSUE_NUMBER,
  "targetBranch": "main",
  "objective": "origin/main 기준의 로컬 에이전트 하네스 코어로 계획, 범위, 기준점, 위험, 증거를 fail-closed 판정한다.",
  "allowedPaths": [
    "AGENTS.md",
    "docs/rules/conventions.md",
    "docs/rules/workflow.md",
    "docs/superpowers/plans/2026-07-14-agent-harness-core.md",
    "docs/superpowers/specs/2026-07-14-agent-harness-hard-gate-design.md",
    "harness/README.md",
    "harness/plan.example.json",
    "harness/risk-policy.json",
    "harness/tests/test_agent_harness.py",
    "scripts/agent-harness.py"
  ],
  "acceptanceCriteria": [
    "branch issue 번호와 manifest issue가 다르면 REPLAN_REQUIRED다.",
    "origin/main tip 또는 merge-base가 prepare 이후 바뀌면 REPLAN_REQUIRED다.",
    "committed, staged, unstaged, untracked, rename의 이전 경로와 새 경로를 모두 검사한다.",
    "allowedPaths 밖 변경, 미분류 경로, 미선언 위험은 REPLAN_REQUIRED다.",
    "기존 Flyway migration 수정 또는 삭제는 FAIL이다.",
    "Docker 또는 Java를 사용할 수 없으면 BLOCKED다.",
    "현재 plan, base tip, merge-base, HEAD, diff hash에 묶인 evaluation.json을 쓴다."
  ],
  "declaredRisks": [
    "scope",
    "completion"
  ],
  "contractChanges": [
    "scripts/agent-harness.py v1",
    "harness/README.md v1",
    "harness/plan.example.json v1",
    "harness/risk-policy.json v1",
    "harness/tests/test_agent_harness.py v1"
  ],
  "nonGoals": [
    "GitHub trusted/candidate workflow 추가",
    "branch protection 설정",
    "제품 Java 또는 Flyway migration 수정",
    "도메인 oracle와 mutation benchmark 구현"
  ]
}
```

- [ ] **Step 6: manifest 형식과 untracked 경로를 정확히 검증한다**

Run:

```bash
python3 -m json.tool "harness/plans/${ISSUE_NUMBER}.json" >/dev/null
git ls-files --others --exclude-standard | sort
```

Expected: JSON 검사 exit 0, untracked 출력은 다음 세 경로와 정확히 같다.

```text
docs/superpowers/plans/2026-07-14-agent-harness-core.md
docs/superpowers/specs/2026-07-14-agent-harness-hard-gate-design.md
harness/plans/<실행 시 확정된 issue 번호>.json
```

- [ ] **Step 7: 승인 문서와 bootstrap manifest를 첫 커밋으로 고정한다**

```bash
git add \
  docs/superpowers/specs/2026-07-14-agent-harness-hard-gate-design.md \
  docs/superpowers/plans/2026-07-14-agent-harness-core.md \
  "harness/plans/${ISSUE_NUMBER}.json"
git commit -m "docs: 에이전트 하네스 승인 범위를 고정"
```

Expected: 승인 문서 두 개와 manifest만 포함한 commit. 이 시점에는 판정기가 아직 없으므로 repository owner의 파일 범위 검토가 gate다.

---

### Task 2: Status, Manifest, Policy Validator

**Files:**
- Create: `scripts/agent-harness.py`
- Create: `harness/tests/test_agent_harness.py`
- Create: `harness/plan.example.json`
- Create: `harness/risk-policy.json`

**Interfaces:**
- Consumes: Task 1 manifest의 8개 필드와 고정 exit code
- Produces: `State`, `Plan`, `RiskRule`, `RiskPolicy`, `HarnessViolation`, `contract_change_path()`, `parse_plan()`, `load_risk_policy()`, `validate_plan_pattern()`, `path_matches()`

- [ ] **Step 1: validator 실패 테스트를 작성한다**

Run once before `apply_patch`:

```bash
mkdir -p harness/tests
```

`harness/tests/test_agent_harness.py`의 초기 내용은 다음 구조와 test name을 사용한다.

```python
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "agent-harness.py"
SPEC = importlib.util.spec_from_file_location("agent_harness", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("agent-harness.py를 load할 수 없습니다.")
HARNESS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HARNESS
SPEC.loader.exec_module(HARNESS)
SOURCE_POLICY = Path(__file__).resolve().parents[1] / "risk-policy.json"


def valid_plan_bytes(issue: int = 123) -> bytes:
    return json.dumps(
        {
            "issue": issue,
            "targetBranch": "main",
            "objective": "충전과 주문의 통합 동시성 검증",
            "allowedPaths": [
                "src/test/java/com/example/coffee/concurrency/CrossDomainConcurrencyIntegrationTest.java",
                "docs/logs/concurrency-test.md",
            ],
            "acceptanceCriteria": ["최종 잔액과 성공 이력 합계가 일치한다."],
            "declaredRisks": ["transaction", "concurrency"],
            "contractChanges": [],
            "nonGoals": ["운영 코드 변경", "락 전략 변경"],
        },
        ensure_ascii=False,
    ).encode("utf-8")


class StateAndPlanTest(unittest.TestCase):
    def test_state_values_equal_cli_exit_codes(self) -> None:
        self.assertEqual(0, HARNESS.State.PASS)
        self.assertEqual(1, HARNESS.State.FAIL)
        self.assertEqual(2, HARNESS.State.BLOCKED)
        self.assertEqual(3, HARNESS.State.REPLAN_REQUIRED)

    def test_parse_plan_accepts_exact_schema(self) -> None:
        plan = HARNESS.parse_plan(
            valid_plan_bytes(),
            relative_path="harness/plans/123.json",
            known_risks=frozenset({"transaction", "concurrency"}),
        )
        self.assertEqual(123, plan.issue)
        self.assertEqual("main", plan.target_branch)
        self.assertEqual(64, len(plan.plan_hash))

    def test_parse_plan_rejects_unknown_field(self) -> None:
        raw = json.loads(valid_plan_bytes())
        raw["baseSha"] = "self-declared"
        with self.assertRaisesRegex(HARNESS.HarnessViolation, "미지원 필드"):
            HARNESS.parse_plan(
                json.dumps(raw).encode(),
                relative_path="harness/plans/123.json",
                known_risks=frozenset({"transaction", "concurrency"}),
            )

    def test_parse_plan_rejects_boolean_issue(self) -> None:
        raw = json.loads(valid_plan_bytes())
        raw["issue"] = True
        with self.assertRaisesRegex(HARNESS.HarnessViolation, "issue"):
            HARNESS.parse_plan(
                json.dumps(raw).encode(),
                relative_path="harness/plans/123.json",
                known_risks=frozenset({"transaction", "concurrency"}),
            )

    def test_parse_plan_rejects_malformed_contract_changes(self) -> None:
        for declaration in (
            "not scripts/agent-harness.py changed",
            "scripts/agent-harness.py",
        ):
            with self.subTest(declaration=declaration):
                raw = json.loads(valid_plan_bytes())
                raw["contractChanges"] = [declaration]
                with self.assertRaisesRegex(HARNESS.HarnessViolation, "contractChanges") as caught:
                    HARNESS.parse_plan(
                        json.dumps(raw).encode(),
                        relative_path="harness/plans/123.json",
                        known_risks=frozenset({"transaction", "concurrency"}),
                    )
                self.assertEqual(HARNESS.State.REPLAN_REQUIRED, caught.exception.state)

    def test_plan_path_must_match_issue_number(self) -> None:
        with self.assertRaisesRegex(HARNESS.HarnessViolation, "plan 경로"):
            HARNESS.parse_plan(
                valid_plan_bytes(),
                relative_path="harness/plans/124.json",
                known_risks=frozenset({"transaction", "concurrency"}),
            )

    def test_broad_src_glob_requires_replan(self) -> None:
        raw = json.loads(valid_plan_bytes())
        raw["allowedPaths"] = ["src/**"]
        with self.assertRaisesRegex(HARNESS.HarnessViolation, "광범위") as caught:
            HARNESS.parse_plan(
                json.dumps(raw).encode(),
                relative_path="harness/plans/123.json",
                known_risks=frozenset({"transaction", "concurrency"}),
            )
        self.assertEqual(HARNESS.State.REPLAN_REQUIRED, caught.exception.state)

    def test_path_match_does_not_accept_sibling_prefix(self) -> None:
        self.assertTrue(HARNESS.path_matches("docs/logs/**", "docs/logs/order.md"))
        self.assertFalse(HARNESS.path_matches("docs/logs/**", "docs/logstash/order.md"))

    def test_policy_rejects_unknown_field(self) -> None:
        payload = json.loads(SOURCE_POLICY.read_text(encoding="utf-8"))
        payload["allowUnknown"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(HARNESS.HarnessViolation, "최상위 필드"):
                HARNESS.load_risk_policy(path)

    def test_policy_rejects_duplicate_pattern_across_rules(self) -> None:
        payload = json.loads(SOURCE_POLICY.read_text(encoding="utf-8"))
        payload["rules"][1]["patterns"] = [payload["rules"][0]["patterns"][0]]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(HARNESS.HarnessViolation, "중복 pattern"):
                HARNESS.load_risk_policy(path)

    def test_policy_rejects_unknown_implemented_check(self) -> None:
        payload = json.loads(SOURCE_POLICY.read_text(encoding="utf-8"))
        payload["implementedChecks"].append("oracle.unknown")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(HARNESS.HarnessViolation, "riskChecks에 없는"):
                HARNESS.load_risk_policy(path)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: test가 구현 부재로 실패하는지 확인한다**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s harness/tests -p 'test_*.py' -v
```

Expected: FAIL 또는 ERROR. 최초 원인은 `scripts/agent-harness.py`가 없거나 `State`가 없다는 메시지다.

- [ ] **Step 3: 최소 model과 manifest validator를 구현한다**

`scripts/agent-harness.py`에 다음 public model과 validator를 구현한다.

```python
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence


class State(IntEnum):
    PASS = 0
    FAIL = 1
    BLOCKED = 2
    REPLAN_REQUIRED = 3


class HarnessViolation(Exception):
    def __init__(self, state: State, check_id: str, reason: str) -> None:
        super().__init__(reason)
        self.state = state
        self.check_id = check_id
        self.reason = reason


@dataclass(frozen=True)
class Plan:
    issue: int
    target_branch: str
    objective: str
    allowed_paths: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    declared_risks: tuple[str, ...]
    contract_changes: tuple[str, ...]
    non_goals: tuple[str, ...]
    relative_path: str
    plan_hash: str


@dataclass(frozen=True)
class RiskRule:
    rule_id: str
    patterns: tuple[str, ...]
    risks: tuple[str, ...]


@dataclass(frozen=True)
class RiskPolicy:
    schema_version: int
    known_risks: frozenset[str]
    rules: tuple[RiskRule, ...]
    protected_patterns: tuple[str, ...]
    risk_checks: Mapping[str, tuple[str, ...]]
    implemented_checks: frozenset[str]


PLAN_FIELDS = {
    "issue",
    "targetBranch",
    "objective",
    "allowedPaths",
    "acceptanceCriteria",
    "declaredRisks",
    "contractChanges",
    "nonGoals",
}
FORBIDDEN_PLAN_PATTERNS = {
    "**",
    "src/**",
    "src/main/**",
    "src/main/java/**",
    "src/test/**",
    "docs/**",
    "harness/**",
    "scripts/**",
    ".github/**",
}


def string_array(raw: object, field: str, *, require_non_empty: bool) -> tuple[str, ...]:
    if not isinstance(raw, list) or any(not isinstance(value, str) for value in raw):
        raise HarnessViolation(State.FAIL, "plan.schema", f"{field}는 문자열 배열이어야 합니다.")
    values = tuple(value.strip() for value in raw)
    if any(not value for value in values):
        raise HarnessViolation(State.FAIL, "plan.schema", f"{field}에 빈 문자열을 허용하지 않습니다.")
    if len(values) != len(set(values)):
        raise HarnessViolation(State.FAIL, "plan.schema", f"{field}에 중복 값을 허용하지 않습니다.")
    if require_non_empty and not values:
        raise HarnessViolation(State.FAIL, "plan.schema", f"{field}는 비어 있을 수 없습니다.")
    return values


def contract_change_path(declaration: str) -> str:
    path, separator, version = declaration.rpartition(" ")
    if not separator or not path or re.fullmatch(r"v[1-9]\d*", version) is None:
        raise HarnessViolation(
            State.REPLAN_REQUIRED,
            "plan.contract-changes",
            "contractChanges는 '<정확한 경로> v<양의 정수>' 형식이어야 합니다: "
            f"{declaration}",
        )
    return path


def validate_plan_pattern(pattern: str) -> None:
    if pattern in FORBIDDEN_PLAN_PATTERNS:
        raise HarnessViolation(State.REPLAN_REQUIRED, "plan.scope", f"광범위 allowedPaths 금지: {pattern}")
    if pattern.startswith("/") or "\\" in pattern or "//" in pattern or ".." in pattern.split("/"):
        raise HarnessViolation(State.FAIL, "plan.schema", f"잘못된 경로: {pattern}")
    body = pattern[:-3] if pattern.endswith("/**") else pattern
    if not body or any(token in body for token in ("*", "?", "[", "]")):
        raise HarnessViolation(State.FAIL, "plan.schema", f"지원하지 않는 glob: {pattern}")


def path_matches(pattern: str, path: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(prefix + "/")
    return path == pattern


def parse_plan(raw: bytes, *, relative_path: str, known_risks: frozenset[str]) -> Plan:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HarnessViolation(State.FAIL, "plan.schema", f"JSON 해석 실패: {error}") from error
    if not isinstance(payload, dict):
        raise HarnessViolation(State.FAIL, "plan.schema", "manifest 최상위 값은 object여야 합니다.")
    unknown = sorted(set(payload) - PLAN_FIELDS)
    missing = sorted(PLAN_FIELDS - set(payload))
    if unknown:
        raise HarnessViolation(State.FAIL, "plan.schema", f"미지원 필드: {', '.join(unknown)}")
    if missing:
        raise HarnessViolation(State.FAIL, "plan.schema", f"누락 필드: {', '.join(missing)}")
    issue = payload["issue"]
    if type(issue) is not int or issue < 1:
        raise HarnessViolation(State.FAIL, "plan.schema", "issue는 1 이상의 정수여야 합니다.")
    if not isinstance(payload["targetBranch"], str):
        raise HarnessViolation(State.FAIL, "plan.schema", "targetBranch는 문자열이어야 합니다.")
    if payload["targetBranch"] != "main":
        raise HarnessViolation(State.REPLAN_REQUIRED, "plan.target", "targetBranch는 main이어야 합니다.")
    objective = payload["objective"]
    if not isinstance(objective, str) or not objective.strip():
        raise HarnessViolation(State.FAIL, "plan.schema", "objective는 비어 있지 않은 문자열이어야 합니다.")
    expected_path = f"harness/plans/{issue}.json"
    if relative_path != expected_path:
        raise HarnessViolation(State.FAIL, "plan.path", f"plan 경로는 {expected_path}여야 합니다.")
    allowed_paths = string_array(payload["allowedPaths"], "allowedPaths", require_non_empty=True)
    for pattern in allowed_paths:
        validate_plan_pattern(pattern)
    declared_risks = string_array(payload["declaredRisks"], "declaredRisks", require_non_empty=False)
    unknown_risks = sorted(set(declared_risks) - known_risks)
    if unknown_risks:
        raise HarnessViolation(State.FAIL, "plan.schema", f"미지원 위험: {', '.join(unknown_risks)}")
    contract_changes = string_array(
        payload["contractChanges"],
        "contractChanges",
        require_non_empty=False,
    )
    for declaration in contract_changes:
        contract_change_path(declaration)
    return Plan(
        issue=issue,
        target_branch="main",
        objective=objective.strip(),
        allowed_paths=allowed_paths,
        acceptance_criteria=string_array(payload["acceptanceCriteria"], "acceptanceCriteria", require_non_empty=True),
        declared_risks=declared_risks,
        contract_changes=contract_changes,
        non_goals=string_array(payload["nonGoals"], "nonGoals", require_non_empty=True),
        relative_path=relative_path,
        plan_hash=hashlib.sha256(raw).hexdigest(),
    )


POLICY_FIELDS = {
    "schemaVersion",
    "knownRisks",
    "rules",
    "protectedPatterns",
    "riskChecks",
    "implementedChecks",
}
RULE_FIELDS = {"id", "patterns", "risks"}


def policy_error(reason: str) -> HarnessViolation:
    return HarnessViolation(State.FAIL, "policy.schema", reason)


def policy_string_array(raw: object, field: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(raw, list) or any(not isinstance(value, str) for value in raw):
        raise policy_error(f"{field}는 문자열 배열이어야 합니다.")
    values = tuple(value.strip() for value in raw)
    if any(not value for value in values):
        raise policy_error(f"{field}에 빈 문자열을 허용하지 않습니다.")
    if len(values) != len(set(values)):
        raise policy_error(f"{field}에 중복 값을 허용하지 않습니다.")
    if not allow_empty and not values:
        raise policy_error(f"{field}는 비어 있을 수 없습니다.")
    return values


def validate_policy_pattern(pattern: str) -> None:
    if pattern.startswith("/") or "\\" in pattern or "//" in pattern or ".." in pattern.split("/"):
        raise policy_error(f"잘못된 policy 경로: {pattern}")
    body = pattern[:-3] if pattern.endswith("/**") else pattern
    if not body or any(token in body for token in ("*", "?", "[", "]")):
        raise policy_error(f"지원하지 않는 policy glob: {pattern}")


def load_risk_policy(path: Path) -> RiskPolicy:
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise policy_error(f"policy 읽기 실패: {error}") from error
    if not isinstance(payload, dict) or set(payload) != POLICY_FIELDS:
        raise policy_error("policy 최상위 필드가 고정 schema와 다릅니다.")
    if type(payload["schemaVersion"]) is not int or payload["schemaVersion"] != 1:
        raise policy_error("schemaVersion은 정수 1이어야 합니다.")
    known_risks = frozenset(policy_string_array(payload["knownRisks"], "knownRisks"))
    if not isinstance(payload["rules"], list) or not payload["rules"]:
        raise policy_error("rules는 비어 있지 않은 배열이어야 합니다.")
    rules: list[RiskRule] = []
    seen_ids: set[str] = set()
    seen_patterns: set[str] = set()
    for index, raw_rule in enumerate(payload["rules"]):
        if not isinstance(raw_rule, dict) or set(raw_rule) != RULE_FIELDS:
            raise policy_error(f"rules[{index}] 필드가 고정 schema와 다릅니다.")
        rule_id = raw_rule["id"]
        if not isinstance(rule_id, str) or not rule_id.strip() or rule_id in seen_ids:
            raise policy_error(f"rules[{index}].id가 비었거나 중복입니다.")
        seen_ids.add(rule_id)
        patterns = policy_string_array(raw_rule["patterns"], f"rules[{index}].patterns")
        for pattern in patterns:
            validate_policy_pattern(pattern)
            if pattern in seen_patterns:
                raise policy_error(f"rules 전체에서 중복 pattern: {pattern}")
            seen_patterns.add(pattern)
        risks = policy_string_array(raw_rule["risks"], f"rules[{index}].risks", allow_empty=True)
        unknown = sorted(set(risks) - known_risks)
        if unknown:
            raise policy_error(f"rules[{index}]의 미지원 위험: {', '.join(unknown)}")
        rules.append(RiskRule(rule_id.strip(), patterns, risks))
    protected_patterns = policy_string_array(payload["protectedPatterns"], "protectedPatterns")
    for pattern in protected_patterns:
        validate_policy_pattern(pattern)
    raw_checks = payload["riskChecks"]
    if not isinstance(raw_checks, dict) or set(raw_checks) != known_risks:
        raise policy_error("riskChecks key는 knownRisks와 정확히 같아야 합니다.")
    risk_checks: dict[str, tuple[str, ...]] = {}
    seen_check_ids: set[str] = set()
    for risk in sorted(known_risks):
        check_ids = policy_string_array(raw_checks[risk], f"riskChecks.{risk}")
        duplicated = sorted(set(check_ids).intersection(seen_check_ids))
        if duplicated:
            raise policy_error(f"riskChecks 전체에서 중복 check ID: {', '.join(duplicated)}")
        seen_check_ids.update(check_ids)
        risk_checks[risk] = check_ids
    implemented_checks = frozenset(
        policy_string_array(payload["implementedChecks"], "implementedChecks")
    )
    known_check_ids = {check_id for checks in risk_checks.values() for check_id in checks}
    unknown_checks = sorted(implemented_checks - known_check_ids)
    if unknown_checks:
        raise policy_error(f"riskChecks에 없는 implementedChecks: {', '.join(unknown_checks)}")
    return RiskPolicy(
        schema_version=1,
        known_risks=known_risks,
        rules=tuple(rules),
        protected_patterns=protected_patterns,
        risk_checks=risk_checks,
        implemented_checks=implemented_checks,
    )


def load_plan(root: Path, plan_path: Path, policy: RiskPolicy) -> Plan:
    absolute = plan_path if plan_path.is_absolute() else root / plan_path
    try:
        relative = absolute.resolve().relative_to(root.resolve()).as_posix()
        raw = absolute.read_bytes()
    except (OSError, ValueError) as error:
        raise HarnessViolation(State.FAIL, "plan.path", f"plan 읽기 실패: {error}") from error
    return parse_plan(raw, relative_path=relative, known_risks=policy.known_risks)
```

위 `load_risk_policy(path: Path) -> RiskPolicy`는 다음 규칙을 정확히 검증한다.

- 최상위 필드: `schemaVersion`, `knownRisks`, `rules`, `protectedPatterns`, `riskChecks`, `implementedChecks`
- `schemaVersion`: 정수 `1`
- 각 rule 필드: `id`, `patterns`, `risks`
- policy pattern: exact 또는 trailing `/**`; plan의 broad-pattern 금지는 적용하지 않음
- 모든 rule risk와 `riskChecks` key는 `knownRisks`에 포함
- 모든 risk는 `riskChecks` entry를 하나 가짐
- 중복 id, pattern, risk, check ID를 거부

형식 위반은 fallback 없이 `FAIL / policy.schema`다.

- [ ] **Step 4: 고정 policy와 example manifest를 작성한다**

`harness/plan.example.json`:

```json
{
  "issue": 123,
  "targetBranch": "main",
  "objective": "충전과 주문의 통합 동시성 검증",
  "allowedPaths": [
    "src/test/java/com/example/coffee/concurrency/CrossDomainConcurrencyIntegrationTest.java",
    "docs/logs/concurrency-test.md"
  ],
  "acceptanceCriteria": [
    "최종 잔액과 성공 충전 합계와 성공 주문 금액 합계가 일치한다.",
    "성공 주문 수와 USE 이력 수가 일치한다."
  ],
  "declaredRisks": [
    "transaction",
    "concurrency"
  ],
  "contractChanges": [],
  "nonGoals": [
    "운영 코드 변경",
    "락 전략 변경"
  ]
}
```

`harness/risk-policy.json`:

```json
{
  "schemaVersion": 1,
  "knownRisks": [
    "scope",
    "architecture",
    "api",
    "migration",
    "transaction",
    "concurrency",
    "async",
    "multi-instance",
    "completion"
  ],
  "rules": [
    {
      "id": "harness-core",
      "patterns": [
        "harness/README.md",
        "harness/plan.example.json",
        "harness/risk-policy.json",
        "harness/tests/test_agent_harness.py",
        "scripts/agent-harness.py"
      ],
      "risks": ["scope", "completion"]
    },
    {
      "id": "agent-router",
      "patterns": ["AGENTS.md"],
      "risks": ["completion"]
    },
    {
      "id": "project-documents",
      "patterns": ["README.md", "CLAUDE.md", "docs/**"],
      "risks": ["completion"]
    },
    {
      "id": "api-contract-document",
      "patterns": ["docs/api-spec.md"],
      "risks": ["api"]
    },
    {
      "id": "table-contract-document",
      "patterns": ["docs/table-spec.md"],
      "risks": ["migration"]
    },
    {
      "id": "architecture-document",
      "patterns": ["ARCHITECTURE.md"],
      "risks": ["architecture"]
    },
    {
      "id": "application-entry",
      "patterns": ["src/main/java/com/example/coffee/CoffeeApplication.java"],
      "risks": ["architecture", "async"]
    },
    {
      "id": "common-boundary",
      "patterns": ["src/main/java/com/example/coffee/common/**"],
      "risks": ["architecture", "api"]
    },
    {
      "id": "menu-boundary",
      "patterns": ["src/main/java/com/example/coffee/menu/**"],
      "risks": ["architecture", "api", "migration"]
    },
    {
      "id": "order-boundary",
      "patterns": ["src/main/java/com/example/coffee/order/**"],
      "risks": ["architecture", "api", "migration", "transaction", "concurrency", "async"]
    },
    {
      "id": "point-boundary",
      "patterns": ["src/main/java/com/example/coffee/point/**"],
      "risks": ["architecture", "api", "migration", "transaction", "concurrency"]
    },
    {
      "id": "flyway-migration",
      "patterns": ["src/main/resources/db/migration/**"],
      "risks": ["migration"]
    },
    {
      "id": "application-config",
      "patterns": ["src/main/resources/application.yaml"],
      "risks": ["async", "multi-instance"]
    },
    {
      "id": "application-test",
      "patterns": ["src/test/**"],
      "risks": ["completion"]
    },
    {
      "id": "build-system",
      "patterns": ["build.gradle", "settings.gradle", "gradlew", "gradlew.bat", "gradle/**"],
      "risks": ["completion"]
    },
    {
      "id": "multi-instance-runtime",
      "patterns": ["Dockerfile", "compose.yaml", "nginx/**", "scripts/multi-instance-smoke.sh"],
      "risks": ["multi-instance", "completion"]
    }
  ],
  "protectedPatterns": [
    "scripts/agent-harness.py",
    "harness/**",
    ".github/workflows/trusted-harness-gate.yml",
    ".github/workflows/quality-gate.yml",
    "harness/contracts/**",
    "docs/contracts/**"
  ],
  "riskChecks": {
    "scope": ["scope.allowed-paths", "risk.classification", "risk.declaration"],
    "architecture": ["oracle.architecture"],
    "api": ["oracle.api-contract"],
    "migration": ["oracle.migration-fresh", "oracle.migration-upgrade"],
    "transaction": ["oracle.transaction"],
    "concurrency": ["oracle.cross-domain-concurrency"],
    "async": ["oracle.async-isolation"],
    "multi-instance": ["oracle.multi-instance"],
    "completion": ["harness.unit", "gradle.test"]
  },
  "implementedChecks": [
    "scope.allowed-paths",
    "risk.classification",
    "risk.declaration",
    "harness.unit",
    "gradle.test"
  ]
}
```

- [ ] **Step 5: validator test와 JSON parse를 통과시킨다**

Run:

```bash
python3 -m json.tool harness/plan.example.json >/dev/null
python3 -m json.tool harness/risk-policy.json >/dev/null
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s harness/tests -p 'test_*.py' -v
```

Expected: JSON 두 개와 모든 `StateAndPlanTest` PASS.

- [ ] **Step 6: bootstrap validator를 커밋한다**

```bash
git add scripts/agent-harness.py harness/plan.example.json harness/risk-policy.json harness/tests/test_agent_harness.py
git commit -m "feat: 하네스 manifest와 policy 검증 추가"
```

Expected: 현재 worktree clean. 이 커밋까지는 최초 trust-root bootstrap 수동 검토 대상이다.

---

### Task 3: Git Base, Branch, Clean Prepare, Plan Lock

**Files:**
- Modify: `scripts/agent-harness.py`
- Modify: `harness/tests/test_agent_harness.py`

**Interfaces:**
- Consumes: `Plan`, `HarnessViolation`, `harness/risk-policy.json`
- Produces: `GitContext`, `PlanLock`, `find_git_root()`, `resolve_local_git_context()`, `collect_worktree_paths()`, `run_prepare_preflight()`, `prepare()`

- [ ] **Step 1: 실제 임시 origin을 쓰는 Git 테스트를 추가한다**

다음 import와 fixture를 `harness/tests/test_agent_harness.py`에 추가한다. 실제 임시 bare origin을 사용하므로 fetch와 merge-base를 mock하지 않는다.
Task 2의 `if __name__ == "__main__": unittest.main()` 블록은 파일 맨 아래로 이동하고, 이후 task에서도 항상 마지막에 유지한다.

```python
import subprocess


def fixture_plan_bytes(issue: int) -> bytes:
    return json.dumps(
        {
            "issue": issue,
            "targetBranch": "main",
            "objective": "임시 저장소의 하네스 판정 검증",
            "allowedPaths": ["AGENTS.md"],
            "acceptanceCriteria": ["현재 diff만 판정한다."],
            "declaredRisks": ["completion"],
            "contractChanges": [],
            "nonGoals": ["제품 코드 변경"],
        },
        ensure_ascii=False,
    ).encode("utf-8")


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def passing_preflight(root: Path) -> tuple[HARNESS.CheckResult, ...]:
    return (HARNESS.CheckResult("environment.fixture", HARNESS.State.PASS, str(root)),)


class GitFixture:
    def __init__(self, issue: int) -> None:
        self.issue = issue
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.origin = self.base / "origin.git"
        self.root = self.base / "work"
        subprocess.run(("git", "init", "--bare", str(self.origin)), check=True, capture_output=True)
        subprocess.run(("git", "clone", str(self.origin), str(self.root)), check=True, capture_output=True)
        git(self.root, "config", "user.name", "Harness Test")
        git(self.root, "config", "user.email", "harness@example.com")
        (self.root / "harness/plans").mkdir(parents=True)
        (self.root / "harness/risk-policy.json").write_bytes(SOURCE_POLICY.read_bytes())
        (self.root / "src/main/resources/db/migration").mkdir(parents=True)
        (self.root / "src/main/resources/db/migration/V1__fixture.sql").write_text("create table fixture(id bigint);\n", encoding="utf-8")
        self.plan_path = self.root / f"harness/plans/{issue}.json"
        self.plan_path.write_bytes(fixture_plan_bytes(issue))
        (self.root / "AGENTS.md").write_text("# fixture\n", encoding="utf-8")
        (self.root / "tracked.txt").write_text("base\n", encoding="utf-8")
        (self.root / "rename-old.txt").write_text("rename\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", "fixture base")
        git(self.root, "branch", "-M", "main")
        git(self.root, "push", "-u", "origin", "main")
        subprocess.run(
            ("git", "--git-dir", str(self.origin), "symbolic-ref", "HEAD", "refs/heads/main"),
            check=True,
            capture_output=True,
        )
        git(self.root, "checkout", "-b", f"feature/{issue}-agent-harness-core")

    def close(self) -> None:
        self.temp.cleanup()

    def policy(self):
        return HARNESS.load_risk_policy(self.root / "harness/risk-policy.json")

    def plan(self):
        return HARNESS.load_plan(self.root, self.plan_path, self.policy())

    def advance_origin_main_without_merging(self) -> None:
        other = self.base / "other"
        subprocess.run(("git", "clone", str(self.origin), str(other)), check=True, capture_output=True)
        git(other, "config", "user.name", "Harness Test")
        git(other, "config", "user.email", "harness@example.com")
        (other / "main.txt").write_text("advanced\n", encoding="utf-8")
        git(other, "add", "main.txt")
        git(other, "commit", "-m", "advance main")
        git(other, "push", "origin", "main")

    def create_all_change_kinds(self) -> None:
        (self.root / "committed.txt").write_text("committed\n", encoding="utf-8")
        git(self.root, "add", "committed.txt")
        git(self.root, "commit", "-m", "committed change")
        (self.root / "staged.txt").write_text("staged\n", encoding="utf-8")
        git(self.root, "add", "staged.txt")
        git(self.root, "mv", "rename-old.txt", "rename-new.txt")
        (self.root / "tracked.txt").write_text("unstaged\n", encoding="utf-8")
        (self.root / "untracked.txt").write_text("untracked\n", encoding="utf-8")

    def prepare_and_add_outside_path(self) -> None:
        state, _ = HARNESS.prepare(self.root, self.plan_path, preflight=passing_preflight)
        if state != HARNESS.State.PASS:
            raise AssertionError(f"fixture prepare 실패: {state}")
        (self.root / "outside.md").write_text("outside\n", encoding="utf-8")

    def prepare_scope_only_change(self) -> None:
        state, _ = HARNESS.prepare(self.root, self.plan_path, preflight=passing_preflight)
        if state != HARNESS.State.PASS:
            raise AssertionError(f"fixture prepare 실패: {state}")
        (self.root / "AGENTS.md").write_text("# changed\n", encoding="utf-8")
```

다음 여섯 `def` 블록을 같은 파일의 `GitStateTest(unittest.TestCase)` body에 한 단계 들여써 추가한다.

```python
def test_branch_must_contain_matching_issue(self) -> None:
    with self.assertRaisesRegex(HARNESS.HarnessViolation, "issue 번호") as caught:
        HARNESS.validate_branch("feature/124-agent-harness-core", 123)
    self.assertEqual(HARNESS.State.REPLAN_REQUIRED, caught.exception.state)


def test_prepare_rejects_second_dirty_path(self) -> None:
    fixture = GitFixture(issue=123)
    self.addCleanup(fixture.close)
    (fixture.root / "outside.md").write_text("범위 밖", encoding="utf-8")
    state, checks = HARNESS.prepare(fixture.root, fixture.plan_path, preflight=passing_preflight)
    self.assertEqual(HARNESS.State.REPLAN_REQUIRED, state)
    self.assertIn("outside.md", " ".join(check.reason for check in checks))


def test_prepare_accepts_only_selected_plan_as_dirty(self) -> None:
    fixture = GitFixture(issue=123)
    self.addCleanup(fixture.close)
    fixture.plan_path.write_bytes(fixture.plan_path.read_bytes() + b"\n")
    state, _ = HARNESS.prepare(fixture.root, fixture.plan_path, preflight=passing_preflight)
    self.assertEqual(HARNESS.State.PASS, state)


def test_prepare_records_base_tip_and_merge_base(self) -> None:
    fixture = GitFixture(issue=123)
    self.addCleanup(fixture.close)
    state, _ = HARNESS.prepare(fixture.root, fixture.plan_path, preflight=passing_preflight)
    self.assertEqual(HARNESS.State.PASS, state)
    lock = json.loads((fixture.root / "build/harness/plan.lock.json").read_text())
    self.assertRegex(lock["baseTipSha"], r"^[0-9a-f]{40}$")
    self.assertRegex(lock["mergeBaseSha"], r"^[0-9a-f]{40}$")


def test_prepare_environment_block_does_not_write_lock(self) -> None:
    fixture = GitFixture(issue=123)
    self.addCleanup(fixture.close)
    blocked = lambda root: (
        HARNESS.CheckResult("environment.python", HARNESS.State.PASS, str(root)),
        HARNESS.CheckResult("environment.java", HARNESS.State.PASS, str(root)),
        HARNESS.CheckResult("environment.docker", HARNESS.State.BLOCKED, "daemon off"),
        HARNESS.CheckResult("environment.java17-toolchain", HARNESS.State.PASS, str(root)),
    )
    state, _ = HARNESS.prepare(fixture.root, fixture.plan_path, preflight=blocked)
    self.assertEqual(HARNESS.State.BLOCKED, state)
    self.assertFalse((fixture.root / "build/harness/plan.lock.json").exists())


def test_lock_base_tip_change_requires_replan_when_merge_base_is_unchanged(self) -> None:
    fixture = GitFixture(issue=123)
    self.addCleanup(fixture.close)
    state, _ = HARNESS.prepare(fixture.root, fixture.plan_path, preflight=passing_preflight)
    self.assertEqual(HARNESS.State.PASS, state)
    old_lock = HARNESS.load_plan_lock(fixture.root / "build/harness/plan.lock.json")
    fixture.advance_origin_main_without_merging()
    policy = HARNESS.load_risk_policy(fixture.root / "harness/risk-policy.json")
    plan = HARNESS.load_plan(fixture.root, fixture.plan_path, policy)
    context = HARNESS.resolve_local_git_context(fixture.root, plan)
    self.assertEqual(old_lock.merge_base_sha, context.merge_base_sha)
    with self.assertRaisesRegex(HARNESS.HarnessViolation, "base tip") as caught:
        HARNESS.validate_plan_lock(old_lock, plan, context)
    self.assertEqual(HARNESS.State.REPLAN_REQUIRED, caught.exception.state)
```

`GitFixture`는 clone 직후 `main`에 policy와 manifest를 commit/push하고 `feature/123-agent-harness-core`를 생성한다. manifest는 `valid_plan_bytes(123)`, policy는 Task 2의 실제 `harness/risk-policy.json` bytes를 복사한다. `advance_origin_main_without_merging()`는 두 번째 clone에서 `main.txt`를 commit/push한다. 테스트는 merge-base 고정과 base tip 이동을 함께 증명해야 한다.

- [ ] **Step 2: Git 테스트가 함수 부재로 실패하는지 확인한다**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s harness/tests -p 'test_*.py' -v
```

Expected: 새 test가 `validate_branch`, `prepare`, `PlanLock` 중 아직 없는 이름으로 FAIL 또는 ERROR.

- [ ] **Step 3: Git identity와 lock model을 구현한다**

`scripts/agent-harness.py`에 다음 model과 함수 계약을 추가한다.

```python
@dataclass(frozen=True)
class GitContext:
    branch: str
    target_branch: str
    base_tip_sha: str
    merge_base_sha: str
    candidate_head_sha: str
    tested_revision_sha: str


@dataclass(frozen=True)
class PlanLock:
    schema_version: int
    issue: int
    plan_path: str
    plan_hash: str
    target_branch: str
    branch: str
    base_tip_sha: str
    merge_base_sha: str


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    state: State
    reason: str
    command: tuple[str, ...] = ()
    exit_code: int | None = None
    duration_ms: int | None = None


BRANCH_PATTERN = re.compile(
    r"^(feature|fix|refactor|docs)/([1-9][0-9]*)-([a-z0-9]+(?:-[a-z0-9]+)*)$"
)


def validate_branch(branch: str, issue: int) -> None:
    match = BRANCH_PATTERN.fullmatch(branch)
    if match is None:
        raise HarnessViolation(State.REPLAN_REQUIRED, "git.branch", f"허용되지 않은 branch: {branch}")
    if int(match.group(2)) != issue:
        raise HarnessViolation(State.REPLAN_REQUIRED, "git.branch", "branch issue 번호와 manifest issue가 다릅니다.")


def run_git(root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ("git", *args),
        cwd=root,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise HarnessViolation(State.BLOCKED, "git.repository", detail or f"git {' '.join(args)} 실패")
    return completed.stdout


def find_git_root(start: Path) -> Path:
    output = run_git(start, "rev-parse", "--show-toplevel")
    return Path(output.decode().strip()).resolve()


def resolve_local_git_context(root: Path, plan: Plan) -> GitContext:
    try:
        run_git(root, "fetch", "--quiet", "origin", plan.target_branch)
    except HarnessViolation as error:
        raise HarnessViolation(State.BLOCKED, "git.base", f"origin/main fetch 실패: {error.reason}") from error
    branch = run_git(root, "branch", "--show-current").decode().strip()
    if not branch:
        raise HarnessViolation(State.REPLAN_REQUIRED, "git.branch", "detached HEAD에서는 로컬 하네스를 실행할 수 없습니다.")
    validate_branch(branch, plan.issue)
    base_tip = run_git(root, "rev-parse", f"refs/remotes/origin/{plan.target_branch}").decode().strip()
    merge_base = run_git(root, "merge-base", "HEAD", base_tip).decode().strip()
    head = run_git(root, "rev-parse", "HEAD").decode().strip()
    invalid = [name for name, value in (("base tip", base_tip), ("merge-base", merge_base), ("HEAD", head)) if not re.fullmatch(r"[0-9a-f]{40}", value)]
    if invalid:
        raise HarnessViolation(State.FAIL, "git.base", f"잘못된 SHA: {', '.join(invalid)}")
    return GitContext(branch, plan.target_branch, base_tip, merge_base, head, head)
```

`run_git()`의 fetch 실패는 `git.base / BLOCKED`로 다시 감싸 이유를 구분한다. SHA는 `^[0-9a-f]{40}$` 정규식으로 모두 검증한다.

- [ ] **Step 4: clean rule과 원자적 lock 쓰기를 구현한다**

다음 함수로 `git diff --cached`, unstaged diff, untracked를 합친다. name-status가 `R` 또는 `C`로 시작하면 old와 new path를 모두 포함한다.

```python
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def parse_name_status(raw: bytes) -> tuple[str, ...]:
    tokens = raw.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    paths: list[str] = []
    index = 0
    while index < len(tokens):
        status = tokens[index].decode("ascii")
        index += 1
        path_count = 2 if status.startswith(("R", "C")) else 1
        if index + path_count > len(tokens):
            raise HarnessViolation(State.FAIL, "git.diff", "name-status 출력이 불완전합니다.")
        for token in tokens[index:index + path_count]:
            paths.append(token.decode("utf-8", errors="surrogateescape"))
        index += path_count
    return tuple(paths)


def parse_nul_paths(raw: bytes) -> tuple[str, ...]:
    return tuple(
        token.decode("utf-8", errors="surrogateescape")
        for token in raw.split(b"\0")
        if token
    )


def collect_worktree_paths(root: Path) -> tuple[str, ...]:
    paths: set[str] = set()
    paths.update(parse_name_status(run_git(root, "diff", "--cached", "--name-status", "-z", "--find-renames", "--")))
    paths.update(parse_name_status(run_git(root, "diff", "--name-status", "-z", "--find-renames", "--")))
    paths.update(parse_nul_paths(run_git(root, "ls-files", "--others", "--exclude-standard", "-z")))
    return tuple(sorted(paths))


def write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.replace(path)


def plan_lock_payload(lock: PlanLock) -> dict[str, object]:
    return {
        "schemaVersion": lock.schema_version,
        "issue": lock.issue,
        "planPath": lock.plan_path,
        "planHash": lock.plan_hash,
        "targetBranch": lock.target_branch,
        "branch": lock.branch,
        "baseTipSha": lock.base_tip_sha,
        "mergeBaseSha": lock.merge_base_sha,
    }


def make_plan_lock(plan: Plan, context: GitContext) -> PlanLock:
    return PlanLock(
        1,
        plan.issue,
        plan.relative_path,
        plan.plan_hash,
        plan.target_branch,
        context.branch,
        context.base_tip_sha,
        context.merge_base_sha,
    )


def load_plan_lock(path: Path) -> PlanLock:
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HarnessViolation(State.REPLAN_REQUIRED, "plan.lock", f"plan lock 읽기 실패: {error}") from error
    expected = {
        "schemaVersion", "issue", "planPath", "planHash", "targetBranch",
        "branch", "baseTipSha", "mergeBaseSha",
    }
    if not isinstance(payload, dict) or set(payload) != expected:
        raise HarnessViolation(State.REPLAN_REQUIRED, "plan.lock", "plan lock schema가 다릅니다.")
    if type(payload["schemaVersion"]) is not int or type(payload["issue"]) is not int:
        raise HarnessViolation(State.REPLAN_REQUIRED, "plan.lock", "plan lock 정수 field type이 잘못됐습니다.")
    string_fields = expected - {"schemaVersion", "issue"}
    if any(not isinstance(payload[field], str) or not payload[field] for field in string_fields):
        raise HarnessViolation(State.REPLAN_REQUIRED, "plan.lock", "plan lock 문자열 field type이 잘못됐습니다.")
    lock = PlanLock(
        payload["schemaVersion"], payload["issue"], payload["planPath"], payload["planHash"],
        payload["targetBranch"], payload["branch"], payload["baseTipSha"], payload["mergeBaseSha"],
    )
    if (
        lock.schema_version != 1
        or not re.fullmatch(r"[0-9a-f]{64}", lock.plan_hash)
        or not SHA_PATTERN.fullmatch(lock.base_tip_sha)
        or not SHA_PATTERN.fullmatch(lock.merge_base_sha)
    ):
        raise HarnessViolation(State.REPLAN_REQUIRED, "plan.lock", "plan lock version 또는 SHA가 잘못됐습니다.")
    return lock


def validate_plan_lock(lock: PlanLock, plan: Plan, context: GitContext) -> None:
    comparisons = (
        (lock.issue, plan.issue, "issue"),
        (lock.plan_path, plan.relative_path, "plan path"),
        (lock.plan_hash, plan.plan_hash, "plan hash"),
        (lock.target_branch, plan.target_branch, "target branch"),
        (lock.branch, context.branch, "branch"),
        (lock.base_tip_sha, context.base_tip_sha, "base tip"),
        (lock.merge_base_sha, context.merge_base_sha, "merge-base"),
    )
    changed = [label for locked, current, label in comparisons if locked != current]
    if changed:
        raise HarnessViolation(State.REPLAN_REQUIRED, "plan.lock", f"prepare 이후 변경됨: {', '.join(changed)}")


def blocked_environment_check(root: Path, check_id: str, command: tuple[str, ...]) -> CheckResult:
    started = time.monotonic()
    completed = subprocess.run(command, cwd=root, check=False, capture_output=True, text=True)
    duration_ms = round((time.monotonic() - started) * 1000)
    output = (completed.stdout + "\n" + completed.stderr).strip()
    state = State.PASS if completed.returncode == 0 else State.BLOCKED
    return CheckResult(check_id, state, output[-4000:] or "출력 없음", command, completed.returncode, duration_ms)


def run_prepare_preflight(root: Path) -> tuple[CheckResult, ...]:
    results: list[CheckResult] = []
    python_state = State.PASS if sys.version_info >= (3, 13) else State.BLOCKED
    results.append(CheckResult("environment.python", python_state, sys.version.split()[0]))
    java = shutil.which("java")
    docker = shutil.which("docker")
    gradlew = root / "gradlew"
    if java is None:
        results.append(CheckResult("environment.java", State.BLOCKED, "java binary를 찾을 수 없습니다."))
    else:
        results.append(blocked_environment_check(root, "environment.java", (java, "-version")))
    if docker is None:
        results.append(CheckResult("environment.docker", State.BLOCKED, "docker binary를 찾을 수 없습니다."))
    else:
        results.append(blocked_environment_check(root, "environment.docker", (docker, "info")))
    if not gradlew.is_file() or not os.access(gradlew, os.X_OK):
        results.append(CheckResult("environment.java17-toolchain", State.BLOCKED, "실행 가능한 ./gradlew가 없습니다."))
    else:
        toolchains = blocked_environment_check(
            root,
            "environment.java17-toolchain",
            ("./gradlew", "-q", "javaToolchains"),
        )
        if toolchains.state is State.PASS and re.search(r"Language Version:\s*17\b", toolchains.reason) is None:
            toolchains = CheckResult(
                toolchains.check_id,
                State.BLOCKED,
                "Java 17 toolchain을 찾을 수 없습니다.",
                toolchains.command,
                toolchains.exit_code,
                toolchains.duration_ms,
            )
        results.append(toolchains)
    return tuple(results)


def prepare(
    root: Path,
    plan_path: Path,
    *,
    preflight: Callable[[Path], tuple[CheckResult, ...]] = run_prepare_preflight,
) -> tuple[State, tuple[CheckResult, ...]]:
    try:
        policy = load_risk_policy(root / "harness/risk-policy.json")
        plan = load_plan(root, plan_path, policy)
        context = resolve_local_git_context(root, plan)
        dirty = set(collect_worktree_paths(root))
        unexpected = sorted(dirty - {plan.relative_path})
        if unexpected:
            raise HarnessViolation(
                State.REPLAN_REQUIRED,
                "git.clean",
                f"prepare 전에 plan 외 변경이 있습니다: {', '.join(unexpected)}",
            )
        environment_checks = preflight(root)
        non_pass = next((check for check in environment_checks if check.state is not State.PASS), None)
        if non_pass is not None:
            return non_pass.state, environment_checks
        lock = make_plan_lock(plan, context)
        write_json_atomic(root / "build/harness/plan.lock.json", plan_lock_payload(lock))
        check = CheckResult("prepare", State.PASS, "plan, branch, base tip, merge-base를 잠갔습니다.")
        return State.PASS, environment_checks + (check,)
    except HarnessViolation as violation:
        return violation.state, (CheckResult(violation.check_id, violation.state, violation.reason),)
    except Exception as error:
        reason = f"{type(error).__name__}: {error}"
        return State.FAIL, (CheckResult("harness.internal", State.FAIL, reason),)


class CliParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise HarnessViolation(State.FAIL, "cli.arguments", message)


def build_parser() -> argparse.ArgumentParser:
    parser = CliParser(prog="agent-harness.py")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("plan", type=Path)
    return parser


def print_checks(checks: Iterable[CheckResult]) -> None:
    for check in checks:
        print(f"[{check.state.name}] {check.check_id}: {check.reason}")


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = build_parser().parse_args(argv)
        root = find_git_root(Path.cwd())
        state, checks = prepare(root, arguments.plan)
        print_checks(checks)
        return int(state)
    except HarnessViolation as violation:
        print(f"[{violation.state.name}] {violation.check_id}: {violation.reason}", file=sys.stderr)
        return int(violation.state)
    except Exception as error:
        print(f"[FAIL] harness.internal: {type(error).__name__}: {error}", file=sys.stderr)
        return int(State.FAIL)


if __name__ == "__main__":
    raise SystemExit(main())
```

`resolve_local_git_context()`에서 fetch 실패는 `git.base / BLOCKED`로 다시 감싸고, 계산한 세 SHA는 `SHA_PATTERN`으로 검증한다. `validate_plan_lock()`은 schema, issue, plan path/hash, target, branch, base tip, merge-base 전부를 비교한다. 이 task의 CLI는 `prepare`만 노출하며 Task 5에서 같은 함수들을 `evaluate`까지 지원하도록 교체한다.

- [ ] **Step 5: Git test를 통과시킨다**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s harness/tests -p 'test_*.py' -v
```

Expected: Task 2와 Task 3 test 모두 PASS. 임시 원격 테스트 뒤 실제 worktree에 새 파일이 남지 않는다.

- [ ] **Step 6: prepare 구현을 커밋한 뒤 실제 lock을 만든다**

```bash
git add scripts/agent-harness.py harness/tests/test_agent_harness.py
git commit -m "feat: 하네스 기준점 잠금과 prepare 추가"
python3 scripts/agent-harness.py prepare "harness/plans/${ISSUE_NUMBER}.json"
```

Expected: `[PASS] prepare` 출력, exit 0, `build/harness/plan.lock.json` 생성, `git status --short`는 빈 출력.

---

### Task 4: Full Diff Scope, Risk, Protected Paths

**Files:**
- Modify: `scripts/agent-harness.py`
- Modify: `harness/tests/test_agent_harness.py`

**Interfaces:**
- Consumes: `Plan`, `RiskPolicy`, `GitContext`, `path_matches()`
- Produces: `RiskClassification`, `collect_local_changed_paths()`, `scope_violations()`, `classify_risks()`, `validate_risk_declarations()`, `validate_contract_changes()`, `validate_existing_migrations_immutable()`

- [ ] **Step 1: 범위·위험 회귀 test를 추가한다**

`make_plan()`과 `make_policy()`는 module-level helper로 추가한다. 이어지는 아홉 `def test_...` 블록은 `ScopeRiskTest(unittest.TestCase)` body에 한 단계 들여써 추가한다.

```python
def make_plan(
    *,
    allowed_paths: tuple[str, ...] = ("AGENTS.md",),
    declared_risks: tuple[str, ...] = ("completion",),
    contract_changes: tuple[str, ...] = (),
) -> HARNESS.Plan:
    return HARNESS.Plan(
        issue=123,
        target_branch="main",
        objective="fixture",
        allowed_paths=allowed_paths,
        acceptance_criteria=("fixture 통과",),
        declared_risks=declared_risks,
        contract_changes=contract_changes,
        non_goals=("제품 변경",),
        relative_path="harness/plans/123.json",
        plan_hash="0" * 64,
    )


def make_policy(rules: tuple[HARNESS.RiskRule, ...] | None = None) -> HARNESS.RiskPolicy:
    selected_rules = rules or (
        HARNESS.RiskRule("agent", ("AGENTS.md",), ("completion",)),
    )
    risks = frozenset({"scope", "architecture", "api", "migration", "transaction", "concurrency", "async", "multi-instance", "completion"})
    return HARNESS.RiskPolicy(
        schema_version=1,
        known_risks=risks,
        rules=selected_rules,
        protected_patterns=("scripts/agent-harness.py",),
        risk_checks={risk: (f"oracle.{risk}",) for risk in risks},
        implemented_checks=frozenset(),
    )


def test_selected_plan_is_implicitly_in_scope(self) -> None:
    plan = make_plan(allowed_paths=("AGENTS.md",))
    self.assertEqual((), HARNESS.scope_violations((plan.relative_path, "AGENTS.md"), plan))


def test_scope_reports_tracked_and_untracked_outside_paths(self) -> None:
    plan = make_plan(allowed_paths=("AGENTS.md",))
    violations = HARNESS.scope_violations(("AGENTS.md", "README.md", "new.txt"), plan)
    self.assertEqual(("README.md", "new.txt"), violations)


def test_risk_classification_unions_overlapping_rules(self) -> None:
    policy = make_policy(
        rules=(
            HARNESS.RiskRule("java", ("src/main/java/**",), ("architecture",)),
            HARNESS.RiskRule("order", ("src/main/java/com/example/coffee/order/**",), ("async",)),
        )
    )
    result = HARNESS.classify_risks(("src/main/java/com/example/coffee/order/OrderService.java",), policy)
    self.assertEqual(("architecture", "async"), result.detected_risks)
    self.assertEqual((), result.unclassified_paths)


def test_api_spec_change_detects_api_risk(self) -> None:
    policy = HARNESS.load_risk_policy(SOURCE_POLICY)
    result = HARNESS.classify_risks(("docs/api-spec.md",), policy)
    self.assertEqual(("api", "completion"), result.detected_risks)


def test_table_spec_change_detects_migration_risk(self) -> None:
    policy = HARNESS.load_risk_policy(SOURCE_POLICY)
    result = HARNESS.classify_risks(("docs/table-spec.md",), policy)
    self.assertEqual(("completion", "migration"), result.detected_risks)


def test_unmatched_path_requires_replan(self) -> None:
    result = HARNESS.classify_risks(("unknown/new.file",), make_policy())
    with self.assertRaisesRegex(HARNESS.HarnessViolation, "미분류") as caught:
        HARNESS.validate_risk_declarations(make_plan(), result)
    self.assertEqual(HARNESS.State.REPLAN_REQUIRED, caught.exception.state)


def test_undeclared_detected_risk_requires_replan(self) -> None:
    classification = HARNESS.RiskClassification(("api",), ())
    with self.assertRaisesRegex(HARNESS.HarnessViolation, "미선언") as caught:
        HARNESS.validate_risk_declarations(make_plan(declared_risks=("scope",)), classification)
    self.assertEqual(HARNESS.State.REPLAN_REQUIRED, caught.exception.state)


def test_protected_path_requires_contract_change(self) -> None:
    plan = make_plan(contract_changes=())
    with self.assertRaisesRegex(HARNESS.HarnessViolation, "contractChanges") as caught:
        HARNESS.validate_contract_changes(("scripts/agent-harness.py",), plan, make_policy())
    self.assertEqual(HARNESS.State.REPLAN_REQUIRED, caught.exception.state)


def test_protected_path_rejects_near_match_and_sentence_declarations(self) -> None:
    for declaration in (
        "scripts/agent-harness.py-malicious v1",
        "not scripts/agent-harness.py changed",
    ):
        with self.subTest(declaration=declaration):
            plan = make_plan(contract_changes=(declaration,))
            with self.assertRaisesRegex(HARNESS.HarnessViolation, "contractChanges") as caught:
                HARNESS.validate_contract_changes(("scripts/agent-harness.py",), plan, make_policy())
            self.assertEqual(HARNESS.State.REPLAN_REQUIRED, caught.exception.state)


def test_protected_path_accepts_exact_versioned_declaration(self) -> None:
    plan = make_plan(contract_changes=("scripts/agent-harness.py v1",))
    HARNESS.validate_contract_changes(("scripts/agent-harness.py",), plan, make_policy())


def test_existing_migration_change_fails_but_new_migration_is_allowed(self) -> None:
    fixture = GitFixture(issue=123)
    self.addCleanup(fixture.close)
    plan = fixture.plan()
    context = HARNESS.resolve_local_git_context(fixture.root, plan)
    existing = "src/main/resources/db/migration/V1__fixture.sql"
    new = "src/main/resources/db/migration/V2__new.sql"
    with self.assertRaisesRegex(HARNESS.HarnessViolation, "기존 Flyway migration") as caught:
        HARNESS.validate_existing_migrations_immutable(fixture.root, context, (existing,))
    self.assertEqual(HARNESS.State.FAIL, caught.exception.state)
    HARNESS.validate_existing_migrations_immutable(fixture.root, context, (new,))
```

임시 Git fixture에는 다음 한 test를 추가한다.

```python
def test_changed_paths_include_committed_staged_unstaged_untracked_and_rename(self) -> None:
    fixture = GitFixture(issue=123)
    self.addCleanup(fixture.close)
    fixture.create_all_change_kinds()
    context = HARNESS.resolve_local_git_context(fixture.root, fixture.plan())
    paths = HARNESS.collect_local_changed_paths(fixture.root, context.merge_base_sha)
    self.assertTrue({
        "committed.txt",
        "staged.txt",
        "tracked.txt",
        "untracked.txt",
        "rename-old.txt",
        "rename-new.txt",
    }.issubset(paths))
```

- [ ] **Step 2: 새 test가 함수 부재로 실패하는지 확인한다**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s harness/tests -p 'test_*.py' -v
```

Expected: `scope_violations` 또는 `RiskClassification` 부재로 FAIL 또는 ERROR.

- [ ] **Step 3: scope와 risk 판정 함수를 구현한다**

```python
@dataclass(frozen=True)
class RiskClassification:
    detected_risks: tuple[str, ...]
    unclassified_paths: tuple[str, ...]


def scope_violations(changed_paths: Iterable[str], plan: Plan) -> tuple[str, ...]:
    violations = {
        path
        for path in changed_paths
        if path != plan.relative_path
        and not any(path_matches(pattern, path) for pattern in plan.allowed_paths)
    }
    return tuple(sorted(violations))


def classify_risks(changed_paths: Iterable[str], policy: RiskPolicy, plan_path: str = "") -> RiskClassification:
    detected: set[str] = set()
    unclassified: list[str] = []
    for path in sorted(set(changed_paths)):
        if path == plan_path:
            continue
        matches = [rule for rule in policy.rules if any(path_matches(pattern, path) for pattern in rule.patterns)]
        if not matches:
            unclassified.append(path)
            continue
        for rule in matches:
            detected.update(rule.risks)
    return RiskClassification(tuple(sorted(detected)), tuple(unclassified))


def validate_risk_declarations(plan: Plan, classification: RiskClassification) -> None:
    if classification.unclassified_paths:
        joined = ", ".join(classification.unclassified_paths)
        raise HarnessViolation(State.REPLAN_REQUIRED, "risk.classification", f"미분류 변경 경로: {joined}")
    undeclared = sorted(set(classification.detected_risks) - set(plan.declared_risks))
    if undeclared:
        raise HarnessViolation(State.REPLAN_REQUIRED, "risk.declaration", f"미선언 위험: {', '.join(undeclared)}")


def validate_contract_changes(changed_paths: Iterable[str], plan: Plan, policy: RiskPolicy) -> None:
    declared_paths = {
        contract_change_path(declaration)
        for declaration in plan.contract_changes
    }
    protected = sorted(
        path
        for path in changed_paths
        if path != plan.relative_path
        and any(path_matches(pattern, path) for pattern in policy.protected_patterns)
    )
    if protected and not plan.contract_changes:
        raise HarnessViolation(
            State.REPLAN_REQUIRED,
            "trust-root.contract",
            f"보호 경로 변경은 contractChanges 선언이 필요합니다: {', '.join(protected)}",
        )
    undeclared = [
        path
        for path in protected
        if path not in declared_paths
    ]
    if undeclared:
        raise HarnessViolation(
            State.REPLAN_REQUIRED,
            "trust-root.contract",
            "contractChanges에 '<정확한 경로> v<양의 정수>' 형식의 보호 경로가 없습니다: "
            f"{', '.join(undeclared)}",
        )


def validate_existing_migrations_immutable(
    root: Path,
    context: GitContext,
    changed_paths: Iterable[str],
) -> None:
    prefix = "src/main/resources/db/migration/"
    existing: list[str] = []
    for path in changed_paths:
        if not path.startswith(prefix):
            continue
        completed = subprocess.run(
            ("git", "cat-file", "-e", f"{context.merge_base_sha}:{path}"),
            cwd=root,
            check=False,
            capture_output=True,
        )
        if completed.returncode == 0:
            existing.append(path)
    if existing:
        raise HarnessViolation(
            State.FAIL,
            "migration.immutable",
            f"기존 Flyway migration은 수정하거나 삭제할 수 없습니다: {', '.join(sorted(existing))}",
        )


def collect_local_changed_paths(root: Path, merge_base_sha: str) -> tuple[str, ...]:
    paths: set[str] = set()
    paths.update(
        parse_name_status(
            run_git(root, "diff", "--name-status", "-z", "--find-renames", merge_base_sha, "HEAD", "--")
        )
    )
    paths.update(
        parse_name_status(
            run_git(root, "diff", "--cached", "--name-status", "-z", "--find-renames", "--")
        )
    )
    paths.update(
        parse_name_status(
            run_git(root, "diff", "--name-status", "-z", "--find-renames", "--")
        )
    )
    paths.update(parse_nul_paths(run_git(root, "ls-files", "--others", "--exclude-standard", "-z")))
    return tuple(sorted(paths))
```

`collect_local_changed_paths()`는 merge-base→HEAD committed diff, staged diff, unstaged diff, untracked를 합친다. 앞 task의 `parse_name_status()`가 `R*`와 `C*`의 두 경로를 모두 반환하므로 삭제, rename old/new도 결과에 남는다.

- [ ] **Step 4: 전체 test를 통과시킨다**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s harness/tests -p 'test_*.py' -v
```

Expected: 모든 test PASS.

- [ ] **Step 5: 범위·위험 판정기를 커밋한다**

```bash
git add scripts/agent-harness.py harness/tests/test_agent_harness.py
git commit -m "feat: 전체 diff 범위와 위험 분류 게이트 추가"
```

---

### Task 5: Required Checks, Diff Hash, Evaluation Evidence

**Files:**
- Modify: `scripts/agent-harness.py`
- Modify: `harness/tests/test_agent_harness.py`

**Interfaces:**
- Consumes: valid `PlanLock`, current `GitContext`, changed paths와 `RiskClassification`
- Produces: `Evaluation`, `compute_diff_hash()`, `aggregate_state()`, `run_required_checks()`, `evaluate()`, `build/harness/evaluation.json`

- [ ] **Step 1: evidence와 상태 우선순위 test를 추가한다**

다음 다섯 `def test_...` 블록을 `EvaluationTest(unittest.TestCase)` body에 한 단계 들여써 추가한다.

```python
def test_aggregate_state_priority_is_replan_fail_blocked_pass(self) -> None:
    checks = (
        HARNESS.CheckResult("pass", HARNESS.State.PASS, "ok"),
        HARNESS.CheckResult("blocked", HARNESS.State.BLOCKED, "docker 없음"),
        HARNESS.CheckResult("fail", HARNESS.State.FAIL, "test 실패"),
        HARNESS.CheckResult("replan", HARNESS.State.REPLAN_REQUIRED, "범위 초과"),
    )
    self.assertEqual(HARNESS.State.REPLAN_REQUIRED, HARNESS.aggregate_state(checks))


def test_invalid_cli_arguments_return_fail_not_blocked(self) -> None:
    completed = subprocess.run(
        (sys.executable, str(SCRIPT)),
        check=False,
        capture_output=True,
        text=True,
    )
    self.assertEqual(1, completed.returncode)
    self.assertIn("[FAIL] cli.arguments", completed.stderr)


def test_diff_hash_changes_when_untracked_content_changes(self) -> None:
    fixture = GitFixture(issue=123)
    self.addCleanup(fixture.close)
    context = HARNESS.resolve_local_git_context(fixture.root, fixture.plan())
    path = fixture.root / "untracked.txt"
    path.write_text("one", encoding="utf-8")
    first = HARNESS.compute_diff_hash(fixture.root, context, ("untracked.txt",))
    path.write_text("two", encoding="utf-8")
    second = HARNESS.compute_diff_hash(fixture.root, context, ("untracked.txt",))
    self.assertNotEqual(first, second)


def test_evaluate_writes_evidence_when_scope_requires_replan(self) -> None:
    fixture = GitFixture(issue=123)
    self.addCleanup(fixture.close)
    fixture.prepare_and_add_outside_path()
    evaluation = HARNESS.evaluate(
        fixture.root,
        fixture.plan_path,
        check_runner=lambda root, ids: (),
    )
    self.assertEqual(HARNESS.State.REPLAN_REQUIRED, evaluation.state)
    payload = json.loads((fixture.root / "build/harness/evaluation.json").read_text())
    self.assertEqual("REPLAN_REQUIRED", payload["state"])
    self.assertIn("outside.md", payload["changedPaths"])
    self.assertEqual(64, len(payload["diffHash"]))


def test_evaluation_contains_all_phase_one_identity_fields(self) -> None:
    fixture = GitFixture(issue=123)
    self.addCleanup(fixture.close)
    fixture.prepare_scope_only_change()
    passing = lambda root, ids: tuple(
        HARNESS.CheckResult(check_id, HARNESS.State.PASS, "통과") for check_id in ids
    )
    evaluation = HARNESS.evaluate(fixture.root, fixture.plan_path, check_runner=passing)
    payload = evaluation.to_dict()
    for field in (
        "baseTipSha",
        "mergeBaseSha",
        "candidateHeadSha",
        "testedRevisionSha",
        "planPath",
        "planHash",
        "declaredRisks",
        "detectedRisks",
        "changedPaths",
        "diffHash",
        "checks",
    ):
        self.assertIn(field, payload)


def test_evaluate_replans_when_head_changes_during_checks(self) -> None:
    fixture = GitFixture(issue=123)
    self.addCleanup(fixture.close)
    fixture.prepare_scope_only_change()

    def committing_runner(root: Path, ids: tuple[str, ...]) -> tuple[HARNESS.CheckResult, ...]:
        git(root, "add", "AGENTS.md")
        git(root, "commit", "-m", "same diff new head")
        return tuple(HARNESS.CheckResult(check_id, HARNESS.State.PASS, "통과") for check_id in ids)

    evaluation = HARNESS.evaluate(fixture.root, fixture.plan_path, check_runner=committing_runner)
    self.assertEqual(HARNESS.State.REPLAN_REQUIRED, evaluation.state)
    freshness = [check for check in evaluation.checks if check.check_id == "evidence.freshness"]
    self.assertEqual(HARNESS.State.REPLAN_REQUIRED, freshness[-1].state)
```

- [ ] **Step 2: 새 test의 red 상태를 확인한다**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s harness/tests -p 'test_*.py' -v
```

Expected: `Evaluation`, `compute_diff_hash`, `aggregate_state` 부재로 FAIL 또는 ERROR.

- [ ] **Step 3: evidence model과 deterministic diff hash를 구현한다**

`Evaluation.to_dict()`는 다음 JSON field 이름을 정확히 사용한다.

```json
{
  "schemaVersion": 1,
  "state": "PASS",
  "baseTipSha": "40-hex",
  "mergeBaseSha": "40-hex",
  "candidateHeadSha": "40-hex",
  "testedRevisionSha": "40-hex",
  "planPath": "harness/plans/123.json",
  "planHash": "64-hex",
  "declaredRisks": ["scope"],
  "detectedRisks": ["scope"],
  "changedPaths": ["AGENTS.md"],
  "diffHash": "64-hex",
  "checks": [
    {
      "id": "scope.allowed-paths",
      "state": "PASS",
      "reason": "모든 변경 경로가 허용 범위에 포함됨",
      "command": [],
      "exitCode": null,
      "durationMs": null
    }
  ]
}
```

문자열 `40-hex`, `64-hex`를 산출물에 쓰지 않는다. 각각 실행 시 계산한 실제 SHA와 SHA-256 값이 들어가야 한다.

`compute_diff_hash()`는 다음 byte sequence를 SHA-256에 순서대로 넣는다.

1. `git diff --binary --no-ext-diff <mergeBaseSha> --` stdout
2. 정렬한 untracked path마다 UTF-8 path bytes, NUL, file bytes, NUL
3. symlink는 target 문자열 bytes를 file bytes 대신 사용

이 방식으로 staged·unstaged tracked content와 untracked content를 모두 identity에 묶는다.

```python
@dataclass(frozen=True)
class Evaluation:
    schema_version: int
    state: State
    base_tip_sha: str | None
    merge_base_sha: str | None
    candidate_head_sha: str | None
    tested_revision_sha: str | None
    plan_path: str
    plan_hash: str | None
    declared_risks: tuple[str, ...]
    detected_risks: tuple[str, ...]
    changed_paths: tuple[str, ...]
    diff_hash: str | None
    checks: tuple[CheckResult, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "state": self.state.name,
            "baseTipSha": self.base_tip_sha,
            "mergeBaseSha": self.merge_base_sha,
            "candidateHeadSha": self.candidate_head_sha,
            "testedRevisionSha": self.tested_revision_sha,
            "planPath": self.plan_path,
            "planHash": self.plan_hash,
            "declaredRisks": list(self.declared_risks),
            "detectedRisks": list(self.detected_risks),
            "changedPaths": list(self.changed_paths),
            "diffHash": self.diff_hash,
            "checks": [
                {
                    "id": check.check_id,
                    "state": check.state.name,
                    "reason": check.reason,
                    "command": list(check.command),
                    "exitCode": check.exit_code,
                    "durationMs": check.duration_ms,
                }
                for check in self.checks
            ],
        }


STATE_PRIORITY = {
    State.PASS: 0,
    State.BLOCKED: 1,
    State.FAIL: 2,
    State.REPLAN_REQUIRED: 3,
}


def aggregate_state(checks: Iterable[CheckResult]) -> State:
    states = [check.state for check in checks]
    return max(states, key=STATE_PRIORITY.__getitem__) if states else State.PASS


def compute_diff_hash(root: Path, context: GitContext, changed_paths: Iterable[str]) -> str:
    digest = hashlib.sha256()
    digest.update(
        run_git(root, "diff", "--binary", "--no-ext-diff", context.merge_base_sha, "--")
    )
    untracked = set(parse_nul_paths(run_git(root, "ls-files", "--others", "--exclude-standard", "-z")))
    for relative in sorted(untracked.intersection(changed_paths)):
        path = root / relative
        digest.update(relative.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
        else:
            digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
```

- [ ] **Step 4: check runner와 fail-closed evaluate를 구현한다**

항상 실행할 command는 다음 두 개다.

```python
HARNESS_TEST_COMMAND = (
    sys.executable,
    "-m",
    "unittest",
    "discover",
    "-s",
    "harness/tests",
    "-p",
    "test_*.py",
    "-v",
)
GRADLE_TEST_COMMAND = ("./gradlew", "clean", "test", "--console", "plain")
```

실행 순서와 상태는 다음으로 고정한다.

1. lock, scope, risk classification, risk declaration, protected contract, diff hash-before
2. `harness.unit`
3. Python 3.13+, `java -version`, `./gradlew -q javaToolchains`의 Java 17, `docker info` preflight; 하나라도 없거나 실행 불가면 `environment.* / BLOCKED`
4. 환경이 준비됐을 때만 `gradle.test`
5. detected와 declared risk 합집합의 `riskChecks` 중 `implementedChecks`에 없는 ID가 있으면 각 ID를 `BLOCKED`로 기록
6. 검증 후 다시 fetch·resolve한 base tip, merge-base, HEAD, plan hash, changed paths, diff hash 중 하나라도 시작 값과 다르면 `evidence.freshness / REPLAN_REQUIRED`
7. 모든 check를 `REPLAN_REQUIRED > FAIL > BLOCKED > PASS` 순으로 집계
8. 상태와 관계없이 `evaluation.json`을 원자적으로 기록

command는 `shell=False`, repo root cwd, `PYTHONDONTWRITEBYTECODE=1`, stdout/stderr capture로 실행한다. `harness.unit` non-zero는 FAIL이다. Docker preflight가 성공한 뒤 Gradle non-zero는 FAIL이다. Gradle output에 `Could not find a valid Docker environment`가 있으면 BLOCKED로 분류한다.

```python
def execute_command(root: Path, check_id: str, command: tuple[str, ...]) -> CheckResult:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    duration_ms = round((time.monotonic() - started) * 1000)
    output = (completed.stdout + "\n" + completed.stderr).strip()
    reason = output[-4000:] if output else "출력 없음"
    if completed.returncode == 0:
        return CheckResult(check_id, State.PASS, reason, command, 0, duration_ms)
    state = State.BLOCKED if "Could not find a valid Docker environment" in output else State.FAIL
    return CheckResult(check_id, state, reason, command, completed.returncode, duration_ms)


def run_required_checks(root: Path, check_ids: tuple[str, ...]) -> tuple[CheckResult, ...]:
    results: list[CheckResult] = []
    for check_id in check_ids:
        if check_id == "harness.unit":
            results.append(execute_command(root, check_id, HARNESS_TEST_COMMAND))
            continue
        if check_id == "gradle.test":
            environment_results = run_prepare_preflight(root)
            results.extend(environment_results)
            environment_ready = all(result.state is State.PASS for result in environment_results)
            if environment_ready:
                results.append(execute_command(root, check_id, GRADLE_TEST_COMMAND))
            else:
                results.append(CheckResult(check_id, State.BLOCKED, "Java 또는 Docker preflight가 BLOCKED입니다."))
            continue
        results.append(CheckResult(check_id, State.BLOCKED, f"아직 구현되지 않은 필수 oracle: {check_id}"))
    return tuple(results)


def required_check_ids(plan: Plan, classification: RiskClassification, policy: RiskPolicy) -> tuple[str, ...]:
    risks = set(plan.declared_risks).union(classification.detected_risks)
    check_ids = {"harness.unit", "gradle.test"}
    for risk in risks:
        check_ids.update(policy.risk_checks[risk])
    inline_ids = {"scope.allowed-paths", "risk.classification", "risk.declaration"}
    order = ["harness.unit", "gradle.test"]
    order.extend(sorted(check_ids - inline_ids - set(order)))
    return tuple(order)


def evaluate(
    root: Path,
    plan_path: Path,
    *,
    check_runner: Callable[[Path, tuple[str, ...]], tuple[CheckResult, ...]] = run_required_checks,
) -> Evaluation:
    plan: Plan | None = None
    context: GitContext | None = None
    classification = RiskClassification((), ())
    changed_paths: tuple[str, ...] = ()
    diff_hash: str | None = None
    checks: list[CheckResult] = []
    try:
        policy = load_risk_policy(root / "harness/risk-policy.json")
        plan = load_plan(root, plan_path, policy)
        context = resolve_local_git_context(root, plan)
        lock = load_plan_lock(root / "build/harness/plan.lock.json")
        validate_plan_lock(lock, plan, context)
        checks.append(CheckResult("plan.lock", State.PASS, "현재 plan과 Git 기준점이 lock과 일치합니다."))

        changed_paths = collect_local_changed_paths(root, context.merge_base_sha)
        diff_hash = compute_diff_hash(root, context, changed_paths)

        validate_existing_migrations_immutable(root, context, changed_paths)
        checks.append(CheckResult("migration.immutable", State.PASS, "기존 Flyway migration이 변경되지 않았습니다."))

        outside = scope_violations(changed_paths, plan)
        if outside:
            raise HarnessViolation(
                State.REPLAN_REQUIRED,
                "scope.allowed-paths",
                f"allowedPaths 밖 변경: {', '.join(outside)}",
            )
        checks.append(CheckResult("scope.allowed-paths", State.PASS, "모든 변경 경로가 허용 범위에 포함됩니다."))

        classification = classify_risks(changed_paths, policy, plan.relative_path)
        validate_risk_declarations(plan, classification)
        checks.append(CheckResult("risk.classification", State.PASS, "모든 변경 경로가 policy로 분류됩니다."))
        checks.append(CheckResult("risk.declaration", State.PASS, "감지된 위험이 manifest 선언에 포함됩니다."))

        validate_contract_changes(changed_paths, plan, policy)
        checks.append(CheckResult("trust-root.contract", State.PASS, "보호 경로 선언이 contractChanges와 일치합니다."))

        ids = required_check_ids(plan, classification, policy)
        checks.extend(check_runner(root, ids))

        ending_plan_hash = hashlib.sha256((root / plan.relative_path).read_bytes()).hexdigest()
        ending_context = resolve_local_git_context(root, plan)
        ending_paths = collect_local_changed_paths(root, ending_context.merge_base_sha)
        after = compute_diff_hash(root, ending_context, ending_paths)
        identity_changed = (
            ending_context != context
            or ending_plan_hash != plan.plan_hash
            or ending_paths != changed_paths
            or after != diff_hash
        )
        if identity_changed:
            checks.append(
                CheckResult(
                    "evidence.freshness",
                    State.REPLAN_REQUIRED,
                    "검증 중 base tip, merge-base, HEAD, plan 또는 diff가 변경됐습니다.",
                )
            )
        else:
            checks.append(CheckResult("evidence.freshness", State.PASS, "검증 전후 base, HEAD, plan, 경로와 diff identity가 같습니다."))
    except HarnessViolation as violation:
        checks.append(CheckResult(violation.check_id, violation.state, violation.reason))
    except Exception as error:
        checks.append(CheckResult("harness.internal", State.FAIL, f"{type(error).__name__}: {error}"))

    state = aggregate_state(checks)
    evaluation = Evaluation(
        schema_version=1,
        state=state,
        base_tip_sha=context.base_tip_sha if context else None,
        merge_base_sha=context.merge_base_sha if context else None,
        candidate_head_sha=context.candidate_head_sha if context else None,
        tested_revision_sha=context.tested_revision_sha if context else None,
        plan_path=plan.relative_path if plan else str(plan_path),
        plan_hash=plan.plan_hash if plan else None,
        declared_risks=plan.declared_risks if plan else (),
        detected_risks=classification.detected_risks,
        changed_paths=changed_paths,
        diff_hash=diff_hash,
        checks=tuple(checks),
    )
    write_json_atomic(root / "build/harness/evaluation.json", evaluation.to_dict())
    return evaluation
```

- [ ] **Step 5: CLI argument 오류와 내부 예외를 fail-closed로 연결한다**

CLI:

```text
python3 scripts/agent-harness.py prepare harness/plans/<issue>.json
python3 scripts/agent-harness.py evaluate harness/plans/<issue>.json
```

`argparse.ArgumentParser.error()`를 override해 기본 exit 2를 쓰지 않는다. 잘못된 command, 누락 plan, 추가 argument는 `[FAIL] cli.arguments: ...`를 stderr에 출력하고 exit 1이다. 예상하지 못한 예외는 traceback을 성공 출력에 섞지 않고 `[FAIL] harness.internal: <ExceptionType>: <message>`와 exit 1로 끝낸다.

Task 3의 `CliParser`, `build_parser`, `print_checks`, `main`, 마지막 `if __name__ == "__main__"` 블록을 아래 코드로 교체한다. 같은 이름을 중복 정의하지 않는다.

```python
class CliParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise HarnessViolation(State.FAIL, "cli.arguments", message)


def build_parser() -> argparse.ArgumentParser:
    parser = CliParser(prog="agent-harness.py")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "evaluate"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("plan", type=Path)
    return parser


def print_checks(checks: Iterable[CheckResult]) -> None:
    for check in checks:
        print(f"[{check.state.name}] {check.check_id}: {check.reason}")


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = build_parser().parse_args(argv)
        root = find_git_root(Path.cwd())
        if arguments.command == "prepare":
            state, checks = prepare(root, arguments.plan)
            print_checks(checks)
            return int(state)
        evaluation = evaluate(root, arguments.plan)
        print_checks(evaluation.checks)
        return int(evaluation.state)
    except HarnessViolation as violation:
        print(f"[{violation.state.name}] {violation.check_id}: {violation.reason}", file=sys.stderr)
        return int(violation.state)
    except Exception as error:
        print(f"[FAIL] harness.internal: {type(error).__name__}: {error}", file=sys.stderr)
        return int(State.FAIL)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: test와 실제 evaluate를 검증한다**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s harness/tests -p 'test_*.py' -v
BEFORE_STATUS=$(git status --short --untracked-files=all)
python3 scripts/agent-harness.py evaluate "harness/plans/${ISSUE_NUMBER}.json"
python3 -m json.tool build/harness/evaluation.json >/dev/null
AFTER_STATUS=$(git status --short --untracked-files=all)
test "$BEFORE_STATUS" = "$AFTER_STATUS"
```

Expected:

- unittest 전부 PASS
- Docker와 Java가 준비되었고 Gradle test가 성공하면 evaluate exit 0과 `state=PASS`
- Docker가 꺼져 있으면 exit 2와 `state=BLOCKED`; 이 경우 Docker를 시작한 뒤 같은 evaluate를 다시 실행해 PASS를 확인
- evidence 생성 전후 status가 같고 `git status` 기준 미커밋 변경 경로는 `scripts/agent-harness.py`, `harness/tests/test_agent_harness.py` 두 개뿐이다. evaluator의 `changedPaths`는 전체 브랜치 diff이므로 이 두 경로만을 뜻하지 않는다. `build/harness`는 ignored다.

- [ ] **Step 7: evidence 판정기를 커밋하고 commit 후 다시 평가한다**

```bash
git add scripts/agent-harness.py harness/tests/test_agent_harness.py
git commit -m "feat: 실행 증거와 완료 상태 판정 추가"
python3 scripts/agent-harness.py evaluate "harness/plans/${ISSUE_NUMBER}.json"
test -z "$(git status --porcelain)"
```

Expected: commit으로 HEAD가 바뀐 뒤 새 `candidateHeadSha`와 `testedRevisionSha`를 기록한 PASS evidence. 이전 evidence 재사용 금지.

---

### Task 6: Operator README and Thin AGENTS Router

**Files:**
- Create: `harness/README.md`
- Modify: `AGENTS.md:14-38`
- Modify: `docs/rules/workflow.md:1-64`
- Modify: `docs/rules/conventions.md:3-9`
- Modify: `harness/tests/test_agent_harness.py`

**Interfaces:**
- Consumes: Task 5의 실제 CLI와 evidence field
- Produces: 에이전트가 읽는 최소 진입점과 문서/CLI drift 회귀 test

- [ ] **Step 1: 문서와 CLI가 어긋나면 실패하는 test를 작성한다**

다음 `def test_...` 블록을 `DocumentationTest(unittest.TestCase)` body에 한 단계 들여써 추가한다.

```python
def test_readme_documents_only_supported_commands_and_states(self) -> None:
    root = Path(__file__).resolve().parents[2]
    readme = (root / "harness/README.md").read_text(encoding="utf-8")
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    for command in (
        "python3 scripts/agent-harness.py prepare harness/plans/<issue>.json",
        "python3 scripts/agent-harness.py evaluate harness/plans/<issue>.json",
    ):
        self.assertIn(command, readme)
    for state in ("PASS", "FAIL", "BLOCKED", "REPLAN_REQUIRED"):
        self.assertIn(state, readme)
    self.assertIn("harness/README.md", agents)
    self.assertNotIn("integrity --ci", readme)
    self.assertNotIn("evaluate --ci", readme)


def test_workflow_and_conventions_use_manifest_gate(self) -> None:
    root = Path(__file__).resolve().parents[2]
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    workflow = (root / "docs/rules/workflow.md").read_text(encoding="utf-8")
    conventions = (root / "docs/rules/conventions.md").read_text(encoding="utf-8")
    order = "Plan → Issue → Branch → Manifest → Prepare → Generate → Evaluate → Explain"
    self.assertIn(order, agents)
    self.assertIn(order, workflow)
    self.assertIn("feature|fix|refactor|docs", workflow)
    self.assertIn("PASS=0", workflow)
    self.assertIn("기존 Flyway migration은 수정하거나 삭제하지 않는다", conventions)
    self.assertIn("allowedPaths", conventions)
```

- [ ] **Step 2: 문서 부재로 test가 실패하는지 확인한다**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s harness/tests -p 'test_*.py' -v
```

Expected: `harness/README.md` 부재로 ERROR 또는 FAIL.

- [ ] **Step 3: `harness/README.md`를 작성한다**

문서 순서와 사실을 다음으로 고정한다.

```markdown
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
```

- [ ] **Step 4: root `AGENTS.md`를 얇게 연결한다**

문서 라우팅 표의 `기능 구현·브랜치·검증 흐름 확인` 다음에 다음 행 하나를 추가한다.

```markdown
| 에이전트 작업 범위·검증 게이트 확인 | [`harness/README.md`][harness-readme] |
```

문서 라우팅 표 바로 아래에 reference target을 한 번 추가한다.

```markdown
[harness-readme]: harness/README.md
```

`## 구현 게이트`의 기존 순서 문장과 6단계 목록을 다음 8단계로 교체한다.

```markdown
기능 작업은 `Plan → Issue → Branch → Manifest → Prepare → Generate → Evaluate → Explain` 순서를 따른다.

1. **Plan**: 사용자가 목적·불변식·트랜잭션 경계·예외 케이스·완료 조건을 설명한다. AI는 반례를 찾는다.
2. **Issue**: 확정한 Plan, 범위, 완료 조건과 검증 방법으로 GitHub 이슈를 생성한다. 이슈가 없으면 코드 변경을 시작하지 않는다.
3. **Branch**: 최신 `origin/main`에서 이슈 번호를 포함한 branch와 clean worktree를 만든다.
4. **Manifest**: 제품 파일보다 먼저 `harness/plans/{issue}.json`에 목적·허용 경로·위험·계약 변경·비목표를 고정한다.
5. **Prepare**: `python3 scripts/agent-harness.py prepare harness/plans/<issue>.json`이 `PASS`한 뒤에만 생성 작업을 시작한다.
6. **Generate**: manifest의 allowedPaths 안에서 확정한 범위의 코드와 테스트만 작성한다.
7. **Evaluate**: 실제 MySQL Testcontainers와 하네스 검증을 실행하고 결과를 기록한다.
8. **Explain**: 선택 이유, 동시 요청, 실패 시 롤백을 사용자가 설명할 수 있어야 완료한다.
```

교체한 8단계 아래, 마지막 “문서에 없는 판단…” 문장 앞에 다음 라우팅 문단을 유지·추가한다.

```markdown
하네스가 적용되는 작업은 제품 파일 수정 전 `python3 scripts/agent-harness.py prepare harness/plans/<issue>.json`, 완료 선언 전 `python3 scripts/agent-harness.py evaluate harness/plans/<issue>.json`을 실행한다. 현재 base tip·merge-base·HEAD·plan·diff에 연결된 `PASS` evidence가 없으면 검증 완료라고 말하지 않는다. 상세 규칙은 [`harness/README.md`][harness-readme]를 따른다.
```

위 구현 게이트 교체와 새 하네스 라우팅 행 외의 기존 라우팅 행은 수정하지 않는다.

- [ ] **Step 5: workflow와 conventions를 실행 계약에 맞춘다**

`docs/rules/workflow.md`의 첫 문장과 구현 흐름을 다음 계약으로 수정한다.

```markdown
기능은 `Plan → Issue → Branch → Manifest → Prepare → Generate → Evaluate → Explain` 순서로 진행합니다. 상태 관리는 이 문서에서, machine-readable 범위는 `harness/plans/{issue}.json`에서, 실제 시도와 증거는 `docs/logs/{기능}.md`에서 관리합니다.
```

`## Plan`, `## Issue`, `## Branch`, 새 `## Manifest`, `## Prepare`를 다음 순서와 책임으로 교체한다.

```markdown
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
- 하나의 branch는 하나의 issue만 처리합니다.

## Manifest

- 제품 파일보다 먼저 `harness/plans/{issue}.json`을 작성합니다.
- objective, allowedPaths, acceptanceCriteria, declaredRisks, contractChanges, nonGoals를 기록합니다.
- 범위나 위험이 바뀌면 manifest를 자동 확대하지 않고 REPLAN_REQUIRED로 돌아갑니다.

## Prepare

- 최신 `origin/main`의 clean worktree에서 `python3 scripts/agent-harness.py prepare harness/plans/{issue}.json`을 실행합니다.
- 선택한 plan 외 dirty 경로, branch·issue 불일치, base 확인 실패, Python·Java 17·Docker 환경 부재를 PASS로 처리하지 않습니다.
- prepare가 `PASS=0`일 때만 allowedPaths 안의 파일을 변경합니다.
```

`## Evaluate`를 다음 상태 계약으로 보강한다.

```markdown
- 완료 선언 전 `python3 scripts/agent-harness.py evaluate harness/plans/{issue}.json`을 실행합니다.
- 상태는 `PASS=0`, `FAIL=1`, `BLOCKED=2`, `REPLAN_REQUIRED=3`입니다.
- FAIL은 최소 수정 뒤 다시 검증하고, BLOCKED는 환경이나 oracle을 준비하며, REPLAN_REQUIRED는 manifest와 사람의 범위 검토로 돌아갑니다.
- 현재 base tip·merge-base·HEAD·plan·diff에 연결된 PASS evidence만 완료 근거입니다.
```

기존 마지막 merge 문장은 다음으로 교체한다.

```markdown
검증이 끝난 변경은 pull request로만 `main`에 병합합니다. Phase 1A와 Phase 1B bootstrap은 repository owner가 수동 검토하고, Phase 1B canary 뒤에는 required checks를 모두 통과해야 합니다. 커밋·병합은 사용자가 요청한 범위에서만 수행합니다.
```

`docs/rules/conventions.md`의 `## 문서 작성`과 `## 커밋 메시지` 사이에 다음 section을 추가한다.

```markdown
## 작업 격리와 변경 범위

- 최신 `origin/main`에서 issue 전용 clean worktree와 `feature|fix|refactor|docs/{이슈번호}-{slug}` branch를 사용한다.
- 제품 파일보다 먼저 `harness/plans/{issue}.json`을 작성하고 모든 변경 경로를 좁은 allowedPaths에 연결한다.
- 선택한 plan 외 dirty 파일이 있으면 prepare하지 않으며 기존 변경을 자동 stash하거나 삭제하지 않는다.
- 기존 Flyway migration은 수정하거나 삭제하지 않는다. schema 변경은 새 migration과 fresh·upgrade 검증으로 추가한다.
- harness, contract, 필수 oracle와 workflow 변경은 contractChanges에 선언하고 trust-root 검토를 받는다.
```

- [ ] **Step 6: 문서 회귀 test와 링크를 검증한다**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s harness/tests -p 'test_*.py' -v
test -f harness/README.md
rg -n 'harness/README.md|agent-harness.py (prepare|evaluate)|Manifest|PASS=0' \
  AGENTS.md harness/README.md docs/rules/workflow.md docs/rules/conventions.md
git diff --check
```

Expected: 모든 test PASS, 링크 대상 존재, prepare/evaluate 두 명령만 노출, whitespace 오류 없음.

- [ ] **Step 7: 문서 라우팅을 커밋한다**

```bash
git add AGENTS.md harness/README.md docs/rules/workflow.md docs/rules/conventions.md harness/tests/test_agent_harness.py
git commit -m "docs: 에이전트 하네스 사용 규칙 연결"
```

---

### Task 7: Adversarial Verification and Phase 1A Handoff

**Files:**
- Verify only: 모든 manifest `allowedPaths` 파일
- Evidence only: `build/harness/plan.lock.json`, `build/harness/evaluation.json`

**Interfaces:**
- Consumes: commit된 Phase 1A 후보 HEAD
- Produces: 정상 PASS와 네 가지 fail-closed 반례의 실제 exit code 증거

- [ ] **Step 1: clean candidate에서 전체 검증을 다시 실행한다**

```bash
test -z "$(git status --porcelain)"
python3 scripts/agent-harness.py prepare "harness/plans/${ISSUE_NUMBER}.json"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s harness/tests -p 'test_*.py' -v
python3 scripts/agent-harness.py evaluate "harness/plans/${ISSUE_NUMBER}.json"
python3 -m json.tool build/harness/evaluation.json >/dev/null
git diff --check origin/main...HEAD
```

Expected: Docker와 Java가 준비된 환경에서 전부 exit 0, evaluation `state=PASS`, worktree clean.

- [ ] **Step 2: 테스트가 실제로 실행됐는지 증거를 확인한다**

```bash
python3 -c 'import json; from pathlib import Path; p=json.loads(Path("build/harness/evaluation.json").read_text()); ids={c["id"] for c in p["checks"]}; assert p["state"]=="PASS"; assert {"harness.unit","gradle.test"} <= ids; assert p["candidateHeadSha"]==p["testedRevisionSha"]'
test "$(git rev-parse HEAD)" = "$(python3 -c 'import json; print(json.load(open("build/harness/evaluation.json"))["candidateHeadSha"])')"
```

Expected: 두 명령 exit 0.

- [ ] **Step 3: 임시 worktree에서 범위 밖 변경을 공격한다**

별도 임시 branch와 worktree를 현재 candidate HEAD에서 만들고 prepare를 먼저 통과시킨다. 그 뒤 `apply_patch`로 `outside.txt`에 `scope attack` 한 줄을 추가하고 evaluate한다. 원래 worktree는 수정하지 않는다.

```bash
ATTACK_DIR=$(mktemp -d)/scope-attack
git worktree add -b "feature/${ISSUE_NUMBER}-scope-attack" "$ATTACK_DIR" HEAD
cd "$ATTACK_DIR"
python3 scripts/agent-harness.py prepare "harness/plans/${ISSUE_NUMBER}.json"
```

현재 `$ATTACK_DIR` 아래 `outside.txt`를 다음 patch로 생성한다.

```diff
*** Begin Patch
*** Add File: outside.txt
+scope attack
*** End Patch
```

Run:

```bash
set +e
python3 scripts/agent-harness.py evaluate "harness/plans/${ISSUE_NUMBER}.json"
EVALUATE_STATUS=$?
set -e
test "$EVALUATE_STATUS" = "3"
python3 -c 'import json; assert json.load(open("build/harness/evaluation.json"))["state"]=="REPLAN_REQUIRED"'
cd -
git worktree remove --force "$ATTACK_DIR"
git branch -d "feature/${ISSUE_NUMBER}-scope-attack"
```

Expected: evaluate exit 3과 `REPLAN_REQUIRED`. 원래 worktree는 clean 상태를 유지한다.

- [ ] **Step 4: unit test의 네 핵심 반례를 단독 실행한다**

```bash
PYTHONPATH=harness/tests PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v \
  test_agent_harness.StateAndPlanTest.test_broad_src_glob_requires_replan \
  test_agent_harness.GitStateTest.test_prepare_rejects_dirty_path_other_than_selected_plan \
  test_agent_harness.GitStateTest.test_plan_lock_detects_base_tip_drift_even_when_merge_base_is_same \
  test_agent_harness.ScopeRiskTest.test_unclassified_path_requires_replan_before_declaration_check
```

Expected: 4 tests, all PASS.

- [ ] **Step 5: 변경 범위가 manifest와 일치하는지 마지막으로 확인한다**

```bash
git diff --name-only origin/main...HEAD | sort
git log --oneline --decorate origin/main..HEAD
git status --short
```

Expected changed paths exactly:

```text
AGENTS.md
docs/rules/conventions.md
docs/rules/workflow.md
docs/superpowers/plans/2026-07-14-agent-harness-core.md
docs/superpowers/specs/2026-07-14-agent-harness-hard-gate-design.md
harness/README.md
harness/plan.example.json
harness/plans/<실행 시 확정된 issue 번호>.json
harness/risk-policy.json
harness/tests/test_agent_harness.py
scripts/agent-harness.py
```

Expected: 관련 없는 제품 코드, migration, GitHub workflow, 기존 dirty PR 파일이 없다. 새 수정이 생기지 않았으므로 이 task에서는 추가 commit을 만들지 않는다.

---

## Phase 1A Acceptance Gate

다음 조건을 모두 만족해야 이 계획만 완료됐다고 말할 수 있다.

1. 실제 issue 번호, branch 번호, manifest 번호가 같다.
2. clean `origin/main` worktree에서 시작했다.
3. 변경 전 Python 3.13+, Java 17 toolchain, Docker, clean-base 전체 Gradle test 결과를 issue에 기록했다.
4. 승인 설계와 이 구현계획이 bootstrap PR에 포함됐다.
5. plan 이외 dirty 파일이 있는 prepare가 exit 3이다.
6. base tip만 이동하고 merge-base가 같아도 lock 검증이 exit 3이다.
7. committed·staged·unstaged·untracked·rename old/new를 모두 수집한다.
8. 범위 밖, 미분류, 미선언 위험과 보호 경로 무선언 변경이 exit 3이다.
9. 기존 Flyway migration 변경은 exit 1이다.
10. Python harness unit과 전체 Gradle test가 실제 실행된다.
11. 환경 부재와 미구현 domain oracle는 exit 2이며 PASS로 바뀌지 않는다.
12. evaluate 도중 base tip, merge-base, HEAD, plan 또는 diff가 움직이면 exit 3이다.
13. evaluation identity가 현재 base tip, merge-base, HEAD, plan hash, diff hash와 일치한다.
14. 현재 dirty refactor worktree와 PR #2의 파일을 건드리지 않았다.
15. Phase 1B CI와 Phase 2 oracle를 구현한 것처럼 README나 PR에 쓰지 않았다.

## Follow-up Plan Boundary

Phase 1A merge 뒤 다음 구현계획은 `docs/superpowers/plans/2026-07-14-agent-harness-ci-trust-gate.md`로 별도 작성한다. 그 계획은 기본 브랜치의 Phase 1A 판정기만 실행하는 `integrity --ci`, read-only candidate의 `evaluate --ci`, owner `/approve-harness <planHash> <headSha>`, head와 test-merge SHA의 trusted status, canary PR, 두 required context 설정만 다룬다. Phase 1B가 merge되기 전에는 일반 제품 PR에 “GitHub hard gate 적용 완료”라고 표현하지 않는다.

`src/AGENTS.md`와 `scripts/check-doc-context.py`는 `origin/main`에 존재하지 않고 현재 PR #2의 package 구조와 직접 연결되므로 Phase 1A에 가짜 기존 파일로 추가하지 않는다. PR #2의 package 기준선이 확정된 뒤 별도 context-router plan에서 `src/AGENTS.md`, checker, package 영향 매트릭스를 함께 도입한다. `docs/rules/workflow.md`와 `docs/rules/conventions.md`는 현재 plan의 Task 6에서 동기화하므로 그 후속 plan으로 미루지 않는다.
