# 에이전트 하네스 하드 게이트 설계

- 작성일: 2026-07-14
- 상태: 사용자 승인 완료, live `origin/main` 대조와 구현 단위 분리 반영
- 대상 저장소: coffee-order-system
- 범위: 에이전트 변경의 계획, 범위 통제, 위험 감지, 검증, 완료 판정

> 구현계획 보정(2026-07-14): live `origin/main`에는 `.github/**`, `scripts/check-doc-context.py`, `src/AGENTS.md`가 없고 이 파일들은 현재 dirty refactor worktree에만 있다. 따라서 그 worktree를 bootstrap 기준으로 사용하지 않는다. 아래 Phase 1 설계 범위는 독립 검증 가능한 Phase 1A 로컬 코어와 Phase 1B CI trust gate 두 PR로 실행하며, 두 bootstrap PR 전체를 repository owner가 수동 검토한다. hard gate는 Phase 1B merge와 canary 검증 뒤부터 적용한다. 상세 실행 순서는 [`2026-07-14-agent-harness-core.md`](../plans/2026-07-14-agent-harness-core.md)를 따른다.

## 1. 배경

현재 저장소에는 AGENTS.md, 문서 라우팅, Plan → Issue → Branch → Generate → Evaluate → Explain 흐름, MySQL Testcontainers 테스트, 문서 링크 검사와 CI가 있다. 그러나 최근 전체 구조와 API 리뷰에서 다음 결함이 발견됐다.

1. 하나의 refactor 브랜치에 패키지 이동, API 검증, migration, CI와 평가 문서 변경이 함께 섞였다.
2. order와 ranking 패키지가 서로 의존했지만 문서 링크·컨텍스트 검사는 이를 발견하지 못했다.
3. 충전 오류 코드와 공통 오류 wrapper가 문서·코드·실제 HTTP 동작에서 달랐다.
4. V5 migration은 기존 주문 데이터의 시간대 전제를 주석으로만 설명하고 실행을 차단하지 않았다.
5. 충전과 주문이 같은 사용자에서 경쟁하는 통합 동시성 테스트가 없었다.
6. 다중 인스턴스 smoke는 상태 요청이 실제로 앱 경계를 넘었는지 증명하지 못했다.
7. 외부 전송 테스트는 Async 제거로 응답이 지연되는 회귀를 잡지 못했다.

공통 원인은 규칙 부족이 아니다. 현재 규칙 대부분이 Markdown 지침과 자기신고형 체크리스트이며, 실제 diff와 런타임 증거를 기준으로 실패시키는 실행형 게이트가 부족하다.

## 2. 목표

하네스는 다음을 보장한다.

1. 변경 작업은 plan manifest에 고정된 목적과 파일 범위에서만 진행한다.
2. 에이전트가 선언한 위험뿐 아니라 실제 diff에서 발견한 위험도 검증한다.
3. 아키텍처, API 계약, migration, 동시성, 비동기 전송과 다중 인스턴스 제약을 결정론적 검사로 보호한다.
4. 실행하지 않은 테스트, Docker 미기동, 누락된 증거를 PASS로 처리하지 않는다.
5. 완료 판정은 현재 base·candidate head·tested revision·plan·diff에 연결된 검증 증거로만 한다.
6. 로컬과 candidate CI는 동일한 후보 판정기를 사용하고, 별도 trusted gate가 기본 브랜치 판정기로 무결성을 검사한다.

## 3. 비목표

1. 외부 에이전트 오케스트레이션 서버를 운영하지 않는다.
2. 에이전트의 모든 잘못된 코드 생성을 원천적으로 막는다고 주장하지 않는다.
3. Redis, Kafka 등 제품 인프라를 하네스 검증을 위해 추가하지 않는다.
4. 모든 Java 문법을 분석하는 범용 정적 분석기를 새로 만들지 않는다.
5. 정상적인 설계 변경을 자동 승인하지 않는다. 범위와 계약 변경의 승인은 사람의 책임이다.

목표는 결함 생성을 완전히 금지하는 것이 아니라, 결함 있는 변경의 완료 선언과 main 병합을 차단하는 것이다. 로컬 Git commit 자체는 신뢰성 있게 금지한다고 주장하지 않는다.

## 4. 검토한 접근

### 4.1 문서와 PR 체크리스트 강화

구현 비용은 가장 낮지만 현재 문제를 반복한다. 에이전트가 체크했다고 기록하면 통과할 수 있고, 순환 의존이나 테스트 증명 공백을 실행으로 판별하지 못한다. 채택하지 않는다.

### 4.2 저장소 내부 fail-closed 하네스

작업 계획을 machine-readable manifest로 만들고, Python 표준 라이브러리 기반 판정기가 범위와 위험을 감지해 관련 검증을 실행한다. 로컬과 CI가 같은 명령을 사용한다. 현재 저장소 규모와 기술 스택에 맞으므로 채택한다.

### 4.3 외부 planner/generator/evaluator 서버

역할 격리와 감사에는 가장 강하지만 별도 서비스, 권한, 실행 큐와 운영 비용이 필요하다. 이번 과제에는 과도하므로 후속 확장으로 남긴다.

## 5. 하네스 구조

제안 구조는 다음과 같다.

    harness/
    ├── README.md
    ├── plan.example.json
    ├── risk-policy.json
    ├── contracts/
    │   └── architecture.json
    ├── mutations/
    │   └── known-defect-*.patch
    └── plans/
        └── <issue-number>.json

    docs/
    └── contracts/
        └── api-contract.json

    scripts/
    ├── agent-harness.py
    └── check-doc-context.py

    build/
    └── harness/
        ├── plan.lock.json
        └── evaluation.json

check-doc-context.py는 링크와 AGENTS.md 컨텍스트 커버리지 검사만 유지한다. 새로운 agent-harness.py가 기존 검사와 위험별 테스트를 순서대로 실행한다.

build/harness 아래 파일은 실행 증거이며 커밋하지 않는다.

risk-policy.json은 변경 경로·import에서 위험을 감지하는 규칙과 각 위험의 필수 check ID·테스트 클래스를 함께 관리한다. 새 제품 경로가 어떤 위험에도 분류되지 않으면 기본값은 통과가 아니라 REPLAN_REQUIRED다.

### 5.1 신뢰 경계

후보 PR이 변경한 판정기로 자신을 검증하면 fail-closed가 아니다. 따라서 다음 두 계층을 분리한다.

1. trusted integrity gate: 기본 브랜치에 이미 병합된 agent-harness.py, risk-policy.json과 contract를 사용한다. `pull_request_target`에서 후보 commit을 worktree로 checkout하지 않고 Git object와 diff 데이터로만 읽어 범위, 기준점, 보호 파일과 판정기 무결성을 검사하며 후보 Java, Gradle, script를 실행하지 않는다.
2. candidate runtime gate: 기본 read-only 권한과 secret이 없는 일반 `pull_request` runner에서 후보 코드의 판정기, Gradle 테스트와 Compose smoke를 실행한다.

GitHub는 `pull_request_target`에서 후보 코드를 checkout한 뒤 실행하는 패턴을 보안 위험으로 경고한다. trusted integrity gate는 [GitHub의 공식 안전 지침](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)에 따라 후보 트리를 실행하지 않는다. trusted workflow 선언은 `contents: read`, `pull-requests: read`, `issues: read`, `statuses: write`만 요청하고 secret은 사용하지 않는다. `statuses: write`는 아래의 trusted 판정 결과를 후보 head commit에 기록하는 용도로만 사용한다.

`pull_request_target`의 기본 `GITHUB_SHA`는 PR head가 아니라 base 브랜치 commit이다. 따라서 workflow job 결과를 그대로 required check로 삼지 않고, trusted workflow가 `github.event.pull_request.head.sha`에 `trusted-harness-integrity` commit status를 pending 후 success·failure로 직접 기록한다. GitHub는 required check가 [최신 PR commit SHA에서 성공](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks#required-check-needs-to-succeed-against-the-latest-commit-sha)해야 한다고 명시한다.

2026-07-14 확인 기준 이 저장소의 직접 collaborator는 소유자 `beyejin` 한 명이다. GitHub에서는 [PR 작성자가 자신의 PR을 승인할 수 없으므로](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/approving-a-pull-request-with-required-reviews), CODEOWNERS required review를 사용하지 않는다. 대신 하네스·contract·oracle·workflow 변경 PR은 기본 브랜치의 기존 gate와 새 mutation suite를 통과하고, 소유자가 PR에 `/approve-harness <planHash> <headSha>` 댓글을 직접 남겨야 한다. trusted workflow는 댓글 작성자가 repository owner인지, hash와 SHA가 현재 plan·head와 일치하는지 검증한다. 새 commit이 추가되면 이전 댓글은 자동으로 무효다. 새 판정기는 병합된 뒤 다음 PR부터 trusted 기준이 되며, 기존 판정기와 호환되지 않는 변경은 두 PR로 나눈다.

## 6. Plan manifest

에이전트는 제품 코드보다 먼저 harness/plans/<issue-number>.json 하나만 작성한다.

필수 필드는 다음과 같다.

    {
      "issue": 123,
      "targetBranch": "main",
      "objective": "충전과 주문의 통합 동시성 검증",
      "allowedPaths": [
        "src/test/java/com/example/coffee/domain/concurrency/**",
        "docs/logs/concurrency-test.md"
      ],
      "acceptanceCriteria": [
        "충전과 주문을 동시에 실행한다",
        "최종 잔액과 CHARGE/USE 이력 합계가 일치한다"
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

규칙은 다음과 같다. 작은 고정 manifest에 범용 JSON Schema engine을 추가하지 않는다. agent-harness.py의 명시적 필드 validator를 단일 실행 정본으로 두고, plan.example.json은 예시로만 사용한다.

1. src/**처럼 도메인을 구분하지 못하는 광범위 wildcard는 허용하지 않는다.
2. targetBranch는 이 저장소에서 main만 허용한다.
3. 로컬 prepare는 origin/main을 fetch한 뒤 `git merge-base HEAD origin/main`으로 base SHA를 직접 계산한다. 네트워크나 원격 ref 확인이 불가능하면 BLOCKED다.
4. CI는 GitHub PR event의 base ref와 fetch-depth 0 checkout에서 merge-base를 계산한다. manifest가 base SHA를 자기선언하지 않는다.
5. branch 이름의 issue 번호와 manifest issue가 일치해야 한다.
6. 허용 branch 형식은 feature/<issue>-<slug>, fix/<issue>-<slug>, refactor/<issue>-<slug>, docs/<issue>-<slug>다.
7. prepare는 기존 변경을 자동 stash하거나 삭제하지 않는다.
8. prepare 시 작업 트리는 선택한 plan 파일 외에는 깨끗해야 한다.
9. prepare가 plan hash와 직접 계산한 base SHA를 build/harness/plan.lock.json에 고정한다.
10. plan이 변경되거나 merge-base가 이동하면 REPLAN_REQUIRED로 돌아간다.
11. contractChanges가 비어 있지 않으면 해당 contract·oracle·mutation 변경 범위를 명시하고, 소유자 댓글의 plan hash·head SHA 일치를 trusted gate가 검증해야 한다.
12. CI는 최종 manifest와 diff의 일관성을 검증한다.

plan hash는 문서가 바뀌지 않았음을 증명하지만, 사람이 구현 전에 승인했다는 사실을 증명하지는 못한다. v1은 사전 인간 승인의 기계적 강제를 보장하지 않고, 최종 PR 리뷰가 plan·diff·evidence를 함께 승인하게 한다.

## 7. 상태 머신

하네스는 네 상태만 사용한다.

| 상태 | 의미 |
|---|---|
| PASS | 현재 base·candidate head·tested revision·plan·diff에 대해 모든 필수 검증이 실행되고 성공 |
| FAIL | 구현, 계약 또는 테스트가 결정론적 검증에서 실패 |
| BLOCKED | Docker, Java 등 검증 환경이 없어 결과를 판단할 수 없음 |
| REPLAN_REQUIRED | 허용 범위 밖 변경, 새 위험, plan 또는 base 변경 |

Docker가 실행되지 않거나 Testcontainers가 시작되지 않으면 테스트 실패로 뭉개지 않고 BLOCKED로 기록한다. 어떤 경우에도 PASS로 대체하지 않는다.

CLI exit code는 PASS=0, FAIL=1, BLOCKED=2, REPLAN_REQUIRED=3으로 고정한다. CI는 이유를 구분하면서도 0이 아닌 모든 상태에서 병합을 차단한다.

## 8. 실행 흐름

### 8.1 Prepare

실행 명령:

    python3 scripts/agent-harness.py prepare harness/plans/<issue>.json

수행 항목:

1. 실제 Git root, branch, target branch와 merge-base 확인
2. manifest 필수 필드·타입·허용값 검증
3. branch와 issue 번호 일치 확인
4. plan 파일 외 기존 변경 유무 확인
5. Docker, Java, Python과 필수 명령 상태 확인
6. plan hash와 base SHA 잠금

Prepare가 PASS하기 전에는 제품 파일을 수정하지 않는다.

### 8.2 Generate

에이전트는 allowedPaths 안에서만 작업한다. 다음 경로는 기본 보호 대상이다.

- 선택한 plan을 제외한 harness/**
- scripts/agent-harness.py
- docs/contracts/**
- 필수 oracle·test 파일
- .github/workflows/trusted-harness-gate.yml
- .github/workflows/quality-gate.yml
- plan.lock.json
- plan의 base 시점에 이미 존재하던 Flyway migration

계약 변경 작업에서 oracle 또는 contract를 수정해야 한다면 plan의 contractChanges에 명시하고 trusted integrity gate와 소유자 hash 승인을 받아야 한다.

### 8.3 Evaluate

실행 명령:

    python3 scripts/agent-harness.py evaluate harness/plans/<issue>.json

수행 항목:

1. 직접 계산한 merge-base와 현재 HEAD 또는 작업 트리의 전체 diff 수집
2. untracked 파일 포함 allowedPaths 검사
3. 변경 경로와 import에서 실제 위험 자동 감지; 분류되지 않은 제품 경로는 REPLAN_REQUIRED
4. detectedRisks가 declaredRisks의 부분집합이 아니면 필요한 검사를 진단용으로 실행해도 최종 상태는 REPLAN_REQUIRED
5. 일치하면 declaredRisks와 detectedRisks의 합집합으로 검증 계획 계산
6. 전체 Gradle 테스트와 위험별 추가 검증 실행
7. required check ID, 필수 테스트 클래스와 JUnit testcase 실행 여부 확인
8. skipped test와 실행되지 않은 명령 확인
9. 검증 전·후 diff hash 재계산; 중간에 변경되면 REPLAN_REQUIRED
10. evaluation.json 생성

기능 결함은 FAIL로 Generate에 되돌린다. 허용 범위나 설계가 달라졌다면 자동으로 범위를 넓히지 않고 REPLAN_REQUIRED로 되돌린다.

## 9. 위험 감지와 강제 검증

| 위험 | 감지 기준 | 필수 검증 |
|---|---|---|
| scope | allowedPaths 밖 tracked 또는 untracked 변경 | 즉시 REPLAN_REQUIRED |
| architecture | domain 패키지, import, ARCHITECTURE.md 변경 | 허용 의존 그래프와 순환 검사 |
| api | controller, dto, ErrorCode, handler, api-spec 변경 | method, request, 2xx, 오류 wrapper·코드, OpenAPI 계약 |
| migration | migration, entity, table-spec 변경 | 기존 migration 불변, fresh와 data-bearing upgrade |
| transaction | service, event listener, repository의 transaction boundary 변경 | 원자성과 롤백 |
| concurrency | User 잔액, repository lock, 충전·주문 변경 | 혼합 충전·주문 동시성 |
| async | event, listener, DataPlatformClient, EnableAsync 변경 | after-commit, 응답 지연 격리, rollback no-send |
| multi-instance | compose, nginx, smoke 또는 상태 API 변경 | 요청별 upstream과 공유 DB workflow |
| completion | README나 workflow를 완료 상태로 변경 | 동일한 diff의 나머지 check PASS |

에이전트가 위험을 선언하지 않아도 실제 경로가 위험을 감지하면 검증 대상에서 제거할 수 없다. 필수 테스트·oracle 파일 삭제나 해당 JUnit testcase 미실행은 테스트 suite의 나머지가 성공해도 FAIL이다.

저장소 규모가 작으므로 위험 선별은 전체 테스트를 줄이는 용도로 사용하지 않는다. `./gradlew clean test`는 항상 실행하고, 위험별 oracle·upgrade·Compose 검증을 추가한다.

## 10. 결함별 oracle

### 10.1 작업 범위 혼합

diff의 모든 파일은 plan의 allowedPaths와 요구사항에 연결되어야 한다. 범위 밖 변경은 자동 수정하지 않고 REPLAN_REQUIRED로 처리한다.

### 10.2 도메인 의존성

harness/contracts/architecture.json에 허용 방향을 기록한다.

- order는 ranking과 infra에 의존할 수 없다.
- ranking은 order의 조회 경계에 의존할 수 있다.
- global은 domain에 의존할 수 없다.
- infra는 order가 공개한 이벤트와 포트에만 의존한다.

초기 버전은 Java import 그래프를 검사하는 작은 Python 판정기를 사용한다. 프로젝트가 모듈화되거나 규칙이 복잡해질 때만 ArchUnit 도입을 검토한다.

### 10.3 API 계약

docs/contracts/api-contract.json을 네 API의 method·path, 요청 필수 필드·schema, 2xx 응답 schema, 실패 wrapper·HTTP status·error code의 machine-readable 정본으로 둔다. docs/api-spec.md는 설명 문서이며 판정기가 contract JSON과 문서 표의 일치를 확인한다. 해당 contract은 보호 경로다.

ApiErrorContractIntegrationTest는 최소한 다음을 검증한다.

- 0 이하 충전 금액
- null과 누락 필드
- 잘못된 JSON
- 지원하지 않는 Content-Type
- 없는 사용자와 메뉴
- 포인트 부족과 overflow
- 모든 실패 응답의 success=false, data=null, error.code와 message

OpenApiContractTest는 실제 `/v3/api-docs`를 contract JSON과 비교해 method, request, 2xx response, 400, 404, 409, 415 schema를 검증한다.

### 10.4 Migration

기존 migration 파일은 수정·삭제할 수 없다. 기본 규칙은 plan·PR당 새 migration 하나다. 분리가 불가능하면 contractChanges에 명시하고 각 신규 migration 직전 버전마다 data-bearing upgrade를 실행한다. 새 migration이 추가되면 다음 두 경로를 모두 실행한다.

1. 빈 DB에서 V1부터 최신까지 적용
2. 직전 버전까지 적용한 뒤 실제 경계 데이터를 넣고 최신으로 업그레이드

V5 시간대 검증은 V4 상태에 비UTC session으로 최근 7일 경계 주문을 넣고, 최신 migration 후 의미가 보존되거나 명시적으로 적용이 차단되는지 확인한다. 테이블, FK, 인덱스와 주문 수 보존도 함께 검사한다.

### 10.5 혼합 동시성

CrossDomainConcurrencyIntegrationTest는 같은 사용자에 충전과 주문을 하나의 latch로 동시에 실행한다.

최종 검증식은 다음과 같다.

    최종 잔액 = 초기 잔액 + 성공 충전 합계 - 성공 주문 금액 합계

성공 주문 수와 USE 이력 수, CHARGE 이력 수와 성공 충전 수가 각각 일치해야 한다.

### 10.6 비동기 외부 전송

OrderAsyncIsolationTest는 test client를 latch로 차단한다. 전송 latch를 해제하기 전에 HTTP 주문 응답과 DB commit이 완료되어야 한다.

강제 rollback 시에는 시간 기반 sleep으로 no-send를 추정하지 않는다. 테스트용 recording executor가 외부 전송 task 제출 횟수를 기록하고, rollback 완료 후 제출 횟수가 0임을 확인한다. 응답 격리는 blocking client latch를 풀기 전에 HTTP 응답과 DB commit이 완료되는지로 Async 제거를 검출한다.

### 10.7 다중 인스턴스

multi-instance-smoke.sh는 인스턴스 경계 검증과 load balancing 검증을 분리한다. 상태 workflow는 테스트용 app1·app2 직접 endpoint를 사용해 대상을 고정한다. 별도 load-balancing check만 Nginx의 `$upstream_addr` 응답 헤더로 두 upstream이 모두 사용되었는지 확인한다. healthcheck·connection timing에 round-robin 순서를 의존하지 않는다.

최소 성공 기준:

1. 충전과 주문이 서로 다른 인스턴스에서 처리된다.
2. 인기 조회는 앞선 주문을 처리하지 않은 인스턴스에서 실행된다.
3. 최종 공유 DB의 잔액, 주문 수와 CHARGE/USE 이력이 일치한다.
4. 두 앱이 서로 다른 DB를 사용하도록 변형하면 smoke가 실패한다.

## 11. Evidence

evaluate는 build/harness/evaluation.json에 다음을 기록한다.

- base SHA, candidate head SHA와 실제 테스트한 revision SHA
- plan 경로와 SHA-256 hash
- declaredRisks와 detectedRisks
- 변경 파일과 diff hash
- 실행한 check ID와 명령
- exit code, 테스트 수, skipped 수와 실행 시간
- Docker와 Testcontainers 시작 여부
- 최종 상태와 실패 이유

evaluation.json의 base SHA, candidate head SHA, tested revision SHA, plan hash, diff hash 중 하나라도 현재 작업과 다르면 완료 증거로 사용할 수 없다. 로컬에서는 candidate head와 tested revision이 현재 HEAD이다. PR CI에서는 candidate head와 GitHub의 test merge revision을 둘 다 기록한다. 커밋 전 로컬 검증 후 commit으로 HEAD가 바뀌면 다시 검증하거나 CI 증거를 사용한다. 원본 JUnit XML과 Compose 로그는 CI artifact로 보존한다.

## 12. 기존 파일 변경

### AGENTS.md

상세 규칙을 추가하지 않는다. 다음 두 명령과 완료 금지만 안내하고 harness/README.md로 라우팅한다.

- 작업 전 prepare
- 완료 전 evaluate
- 현재 base·candidate head·tested revision·plan·diff evidence가 PASS가 아니면 완료 선언 금지

### docs/rules/workflow.md

자유 형식 Plan을 plan manifest로 대체하고 Prepare, Generate, Evaluate 상태 전이와 REPLAN_REQUIRED 조건을 정의한다.

### docs/rules/conventions.md

clean baseline, issue 번호가 있는 branch, allowedPaths, 기존 migration 불변, 보호 경로 규칙을 정의한다.

### src/AGENTS.md

변경 영향 매트릭스를 추가한다.

- User와 UserRepository 변경 → point, order, mixed concurrency
- OrderRepository 변경 → order와 ranking
- global/error 변경 → 모든 API 오류 계약
- event와 dataplatform 변경 → order async isolation
- migration과 entity 변경 → fresh와 upgrade test

### scripts/check-doc-context.py

수정하지 않는다. 현재 단일 책임을 유지한다.

### .github/workflows/trusted-harness-gate.yml

`pull_request_target` 또는 trust-root 승인 댓글의 `issue_comment`에서 기본 브랜치의 workflow와 판정기를 실행한다. 숫자 PR 번호로 후보 commit을 Git object로만 fetch하고, checkout·worktree 생성 없이 diff와 파일 내용을 데이터로 읽어 다음을 검증한다.

- event base ref에서 계산한 merge-base와 전체 변경 범위
- allowedPaths, 미분류 경로와 미선언 위험
- 기존 migration, 필수 test·oracle·contract 삭제
- trusted workflow·판정기 변경 여부와 contractChanges 선언
- trust-root 변경 시 repository owner 댓글의 plan hash·candidate head SHA 일치
- required check job name 중복과 workflow path filter 여부

후보 트리의 script, Gradle, Java와 Docker는 실행하지 않는다. 시작 시 candidate head SHA에 `trusted-harness-integrity=pending`을 기록하고, 모든 종료 경로의 마지막 단계에서 success 또는 failure를 같은 SHA에 기록한다. 예상하지 못한 중단으로 최종 status가 없으면 required check는 pending으로 남아 병합을 차단한다.

### .github/workflows/quality-gate.yml

candidate workflow는 `contents: read`만 선언하고 secret은 사용하지 않으며 fetch-depth를 0으로 설정한다. 후보 workflow가 `statuses: write` 또는 `checks: write`를 요청하면 trusted gate가 해당 diff를 탐지해 실패한다. 다만 이 검사는 권한 요청을 사전에 막는 권한 상한이 아니라, 잘못된 workflow 변경을 병합 전에 검출하는 장치다. 로컬 plan.lock을 가정하지 않고 `prepare --ci`가 event base ref, candidate head와 test merge revision에서 lock을 새로 만든 뒤 `evaluate --ci`를 실행한다. 후보 코드의 전체 Gradle 테스트와 위험별 oracle, Compose smoke를 실행하고 evaluation.json, JUnit과 Compose 로그를 artifact로 업로드한다.

trusted-harness-integrity commit status와 candidate-runtime-gate check는 서로 고유한 context를 사용하고 둘 모두 required로 지정한다. path filter로 workflow 전체를 skip하지 않는다.

### .github/pull_request_template.md

자기신고 체크박스 대신 다음을 요구한다.

- plan manifest 경로
- 목적과 non-goals
- 자동 감지된 위험 목록
- trust-root 변경 시 소유자 승인 댓글
- trusted-harness-integrity·candidate-runtime-gate 결과와 evidence artifact 링크

### docs/agent-evaluation.md

수동 성공 기록에서 manifest 기반 adversarial benchmark 결과로 전환한다.

## 13. GitHub 설정

저장소 파일만으로 병합을 강제할 수 없으므로 다음 branch protection을 설정한다.

1. main 직접 push 금지
2. pull request 필수
3. trusted-harness-integrity와 candidate-runtime-gate를 고유한 required status check로 지정
4. branch가 최신 main 기준으로 검증되어야 병합 허용
5. Actions 기본 `GITHUB_TOKEN` 권한은 read-only로 설정하고, 후보 workflow의 status·check write 요청은 trusted gate에서 실패
6. 하네스 신뢰 경계 변경은 소유자 hash·SHA 댓글 승인 필수
7. 현재 collaborator가 한 명이므로 required approving review와 CODEOWNERS required review는 설정하지 않음
8. 관리자 우회는 제출 전까지 사용하지 않음

GitHub는 required check가 skip되어도 success로 보고할 수 있고 중복 job 이름은 병합 판정을 모호하게 할 수 있으므로, [required status check 공식 지침](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)에 따라 context를 고유하게 유지하고 조건부 skip을 사용하지 않는다. 일반 제품 plan 목적은 소유자의 최종 병합 판단이 담당하고, 하네스 신뢰 경계 변경만 외부 댓글 증거를 기계적으로 강제한다.

## 14. 하네스 자체 검증

알려진 결함을 재현하는 mutation을 관리한다.

1. order → ranking 의존 재도입
2. 충전 오류 코드 불일치
3. 기존 주문이 있는 migration 위험
4. 사용자 락 제거
5. Async 제거
6. app2를 app1과 다른 DB에 연결
7. allowedPaths 밖 파일 추가
8. allowedPaths 안의 미분류 제품 파일 추가
9. 필수 테스트·oracle 삭제
10. 필수 테스트 skip
11. 이전 candidate head·plan·diff의 stale evidence 재사용
12. candidate 판정기를 always PASS로 변경
13. mutation patch의 대상 hash 불일치
14. trusted status를 candidate head가 아닌 base SHA에 기록
15. candidate workflow에 `statuses: write`를 추가

mutation suite는 임시 Git worktree에서만 patch를 적용하며 다음을 확인한다.

1. 정상 기준선에서 oracle PASS
2. mutation 적용 전 target hash 일치 확인
3. patch 적용 자체의 성공과 의도한 diff 생성 확인
4. mutation 적용 후 지정된 check ID가 지정된 이유로 FAIL했을 때만 검출 성공으로 판정
5. mutation 복원 후 다시 PASS

일반 제품 PR에서는 결정론적 gate만 실행한다. harness, contracts 또는 oracle 변경 시 mutation suite를 필수 실행하고, 정기 benchmark에서 독립 초기 문맥의 에이전트가 mutation을 실제로 복구하는 성공률을 별도로 측정한다.

## 15. 도입 순서

### Phase 0. Bootstrap 격리

현재 dirty refactor branch를 하네스 기준선으로 삼지 않는다. 기존 변경을 임의로 커밋·stash·삭제하지 않고, 마지막 clean base에서 별도 issue branch를 만든다. 기존 테스트 결과와 알려진 결함을 기록하되 통과하는 테스트를 green baseline과 혼동하지 않는다.

### Phase 1A. Local trust core

현재 PR에는 plan validator, allowedPaths, branch·issue, base tip·merge-base·plan lock, 전체 diff, risk·protected path, 기존 migration 불변성과 최소 local evidence만 도입한다. trusted·candidate workflow와 branch protection은 포함하지 않는다. 기본 브랜치 판정기가 아직 없으므로 이 PR 전체를 repository owner가 수동 검토한다. 도메인 oracle의 성공을 거짓으로 가정하지 않고, 실행되지 않은 검증은 BLOCKED로 남긴다.

### Phase 1B. CI trust gate

별도 다음 PR에서 trusted·candidate workflow, 최소 CI evidence·artifact, 고유 status context와 canary를 도입한다. 이 PR도 새 trusted workflow가 아직 기본 브랜치에 없으므로 bootstrap 전체를 repository owner가 수동 검토한다. Phase 1B merge와 canary 검증 뒤 두 check를 required로 설정하며, 그 이후 일반 제품 PR부터 hard gate를 적용한다.

### Phase 2A. Deterministic oracle trust roots

Phase 1A/1B gate 위에서 구조, API, migration, mixed concurrency, async isolation, stateful multi-instance oracle를 각각 제품 수정과 분리된 trust-root plan·PR로 먼저 도입한다. 각 oracle PR 전체를 repository owner가 수동 검토하고, oracle이 겨냥한 제품 수정은 그 trust-root PR에 섞지 않는다. 병합된 oracle은 다음 PR부터 trusted gate로 사용한다.

### Phase 2B. Green baseline product fixes

알려진 제품 결함을 서로 분리된 plan·PR로 수정하고, 이미 기본 브랜치에 있는 해당 oracle과 Phase 1A/1B gate를 통과한다. 필요한 oracle이 아직 없으면 제품 수정 PR을 시작하지 않고 Phase 2A를 먼저 수행한다. 임시 PASS allowlist는 두지 않으며, 전체 MySQL 테스트와 다중 인스턴스 smoke가 통과한 clean HEAD만 green baseline으로 고정한다.

### Phase 3. Evidence와 PR 통합 확장

완전한 evaluation.json, 장기 artifact 보존과 PR template 연결을 추가한다. Phase 1B에서 설정한 required check와 branch protection은 유지하며, 이 단계에서 최초 연결을 다시 주장하지 않는다.

### Phase 4. Harness benchmark

6개 제품 결함 mutation, 9개 하네스 fail-open mutation과 manifest 기반 agent evaluation을 추가한다.

## 16. 완료 조건

다음 조건을 모두 만족하면 하네스 도입이 완료된다.

1. 알려진 15개 mutation이 각각 의도한 gate에서 지정된 이유로 실패한다.
2. 정상 기준선은 로컬과 CI에서 모두 PASS한다.
3. 허용 범위 밖 파일을 추가하면 REPLAN_REQUIRED가 된다.
4. 선언하지 않은 위험도 diff에서 자동 감지된다.
5. Docker 미기동은 PASS가 아니라 BLOCKED로 기록된다.
6. 기존 migration 수정과 테스트·oracle 삭제는 실패한다.
7. evaluation.json의 base SHA, candidate head SHA, tested revision SHA, plan hash와 diff hash가 현재 작업과 일치한다.
8. README나 workflow 완료 표시가 diff에 있으면, 그 동일한 diff를 대상으로 실행 중인 evaluate의 모든 다른 check가 PASS해야 최종 PASS를 낼 수 있다.
9. GitHub에서 trusted-harness-integrity와 candidate-runtime-gate 둘 중 하나라도 통과하지 않은 PR은 main에 병합할 수 없다.

## 17. 설계상 한계

1. allowedPaths와 risk-policy는 새 폴더와 기능이 생길 때 유지보수가 필요하다.
2. 사람의 사전 목적 승인을 로컬 파일만으로 신뢰성 있게 서명할 수는 없다. PR 리뷰와 branch protection은 병합 승인을 담당한다.
3. MySQL과 Compose 검증으로 로컬·CI 실행 시간이 늘어난다.
4. 자동 검사만으로 설계 의도를 완전히 판단할 수 없으므로 Explain 단계와 사람의 리뷰는 유지한다.
5. agent-harness.py 자체와 oracle 변경은 일반 제품 변경보다 높은 검토 수준이 필요하며, 새 판정기가 자신의 정당성을 단독으로 증명할 수는 없다.
6. 위협 모델은 일반적인 LLM 코딩 실수와 근거 없는 완료 판정이다. 악의적인 후보 빌드 코드의 runner 공격까지 방어한다고 주장하지 않으며, 이 때문에 trusted workflow는 후보 코드를 실행하지 않는다.
7. 같은 저장소의 candidate workflow와 trusted workflow는 모두 GitHub Actions App을 사용한다. [workflow가 요청하는 `GITHUB_TOKEN` 권한](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository)을 악의적인 후보가 높여 동일 status context를 위조하는 공격은 v1이 완전히 차단하지 못한다. 이 위협까지 포함하려면 기본 브랜치 전용 환경에 격리한 별도 GitHub App credential로 trusted status를 기록하고 branch protection의 expected source를 그 App으로 고정해야 한다.
