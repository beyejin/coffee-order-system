# 에이전트 VCS 권한 및 Docker 레이아웃 구현 계획

> **에이전트 작업자용:** REQUIRED SUB-SKILL: 이 계획을 작업별로 구현하려면 `superpowers:subagent-driven-development`(권장) 또는 `superpowers:executing-plans`를 사용합니다. 단계 추적에는 체크박스(`- [ ]`) 구문을 사용합니다.

**목표:** 오케스트레이션 계약에서 에이전트 VCS capability를 명시하고, 빌드 컨텍스트와 런타임 서비스를 변경하지 않은 채 애플리케이션 Dockerfile을 `docker/Dockerfile`로 이동합니다.

**아키텍처:** `harness/orchestration-policy.json`을 기계 판독 가능한 기준 원본으로 유지하고, `docs/ai/orchestration-policy.md`와 `harness/README.md`에서 같은 계약을 설명합니다. `implementation` role은 product-file 변경과 로컬 commit을 담당하고, `main-orchestrator`의 provider runtime은 push와 merge를 담당합니다. Compose는 저장소 루트를 빌드 컨텍스트로 유지하며 `docker/Dockerfile`을 명시합니다.

**기술 스택:** JSON, Markdown, Python `unittest`, Docker Compose, Gradle/Spring Boot.

## 전역 제약 조건

- 네 개의 고정 role 슬롯인 `implementation`, `verification`, `qa`, `pr-review`를 유지합니다.
- `implementation`을 유일한 product-file 작성자로 유지하고 reviewer는 read-only로 둡니다.
- GitHub token, 저장소, branch-protection, operating-system credential은 변경하지 않습니다.
- Docker Compose service topology, 빌드 컨텍스트, 환경 변수, 런타임 동작을 변경하지 않습니다.
- 모든 변경 경로는 `harness/plans/issue-8-agent-vcs-docker.json`의 `allowedPaths` 안에 있어야 합니다.

---

### 작업 1: 테스트로 VCS capability 계약 고정

**파일:**
- 수정: `harness/tests/test_orchestration_policy.py:8-141`
- 읽기: `harness/orchestration-policy.json`

**인터페이스:**
- 입력: 네 role과 `main-orchestrator`를 키로 사용하는 `policy["vcsCapabilities"]`.
- 출력: `read`, `writeProductFiles`, `writeScope`, `commit`, `push`, `merge`에 대한 결정적 검증.

- [ ] **단계 1: 실패하는 capability-matrix test 추가**

다음의 정확한 구조를 기대하는 테스트를 추가합니다.

```python
expected = {
    "implementation": {
        "read": True,
        "writeProductFiles": True,
        "writeScope": "manifest.allowedPaths",
        "commit": True,
        "push": False,
        "merge": False,
    },
    "verification": {
        "read": True,
        "writeProductFiles": False,
        "writeScope": "none",
        "commit": False,
        "push": False,
        "merge": False,
    },
    "qa": {
        "read": True,
        "writeProductFiles": False,
        "writeScope": "none",
        "commit": False,
        "push": False,
        "merge": False,
    },
    "pr-review": {
        "read": True,
        "writeProductFiles": False,
        "writeScope": "none",
        "commit": False,
        "push": False,
        "merge": False,
    },
    "main-orchestrator": {
        "read": True,
        "writeProductFiles": False,
        "writeScope": "none",
        "commit": False,
        "push": True,
        "merge": True,
    },
}
assert self.policy["vcsCapabilities"] == expected
```

- [ ] **단계 2: 집중 테스트 실행 및 실패 확인**

실행: `python3 -m unittest discover -s harness/tests -p 'test_orchestration_policy.py'`

예상: 아직 `vcsCapabilities`가 없으므로 FAIL.

- [ ] **단계 3: 테스트 범위 고정**

GitHub 자격 증명이나 shell 권한에 대한 검증은 추가하지 않습니다. 이는
JSON workflow 계약 밖의 런타임 범위입니다.

### 작업 2: policy와 사람이 읽을 수 있는 계약 추가

**파일:**
- 수정: `harness/orchestration-policy.json:80-106`
- 수정: `docs/ai/orchestration-policy.md:12-35`
- 수정: `harness/README.md:9-24`

**인터페이스:**
- 입력: 작업 1의 정확히 같은 matrix.
- 출력: 기계 판독 가능한 `vcsCapabilities`와 이에 대응하는 사람이 읽을 수 있는 문서.

- [ ] **단계 1: role 정의 뒤에 `vcsCapabilities` 추가**

테스트가 실행 가능한 계약이 되도록 작업 1의 정확히 같은 matrix를 사용합니다. 하위
호환성을 위해 `roles[*].writeScope`와 `mainOrchestrator.canMerge`는 변경하지 않습니다.

- [ ] **단계 2: 다섯 주체와 자격 증명 경계 문서화**

`actor`, `repo read`, `product file write`, `local commit`, `branch push`, `PR merge` 열을
사용하는 표를 추가합니다. JSON은 workflow capability를 설명하며, 실제 GitHub 자격 증명이
최종 강제 계층으로 남는다고 명시합니다.

- [ ] **단계 3: provider runtime 연결**

`harness/README.md`에 clean HEAD와 evaluate PASS 이후 `scripts/agent-publish.py`가
`main-orchestrator`의 push/PR/선택적 merge 경로를 수행한다고 명시합니다.

- [ ] **단계 4: 집중 테스트 실행 및 통과 확인**

실행: `python3 -m unittest discover -s harness/tests -p 'test_orchestration_policy.py'`

예상: 실패 0개의 PASS.

### 작업 3: Dockerfile 이동 및 risk classification 갱신

**파일:**
- 삭제: `Dockerfile`
- 생성: 기존 20줄 내용을 변경하지 않은 `docker/Dockerfile`
- 수정: `compose.yaml:32-33,56-57`
- 수정: `harness/risk-policy.json:321-327`

**인터페이스:**
- 입력: 루트 빌드 컨텍스트와 기존 Dockerfile `COPY` instructions.
- 출력: `docker/Dockerfile`을 명시적으로 해석하는 `docker compose` services.

- [ ] **단계 1: 내용을 변경하지 않고 파일 이동**

결과물인 `docker/Dockerfile`에는 `FROM eclipse-temurin:17-jdk-jammy`,
`WORKDIR /workspace`, root-context `COPY` 경로, builder `bootJar` 명령,
최종 JRE entrypoint가 유지되어야 합니다.

- [ ] **단계 2: 두 Compose build를 명시적으로 지정**

각 `build: .`을 다음으로 교체합니다.

```yaml
build:
  context: .
  dockerfile: docker/Dockerfile
```

- [ ] **단계 3: rename 양쪽 경로의 classification 지정**

rename-source 분류를 위해 multi-instance risk pattern인 `Dockerfile`을
유지하고 새 경로인 `docker/Dockerfile`을 추가합니다. 두 경로 모두
`multi-instance-runtime`으로 분류되어야 합니다.

- [ ] **단계 4: Compose 파싱 검증**

실행: `docker compose config`

예상: exit code 0이며 `app1`과 `app2`가 모두 저장소 루트를 context로 사용하면서
`docker/Dockerfile`을 해석합니다.

### 작업 4: 전체 검증 및 최종 확정

**파일:**
- 확인: `harness/plans/issue-8-agent-vcs-docker.json`의 모든 변경 경로

**인터페이스:**
- 입력: 작업 1~3에서 변경한 policy, docs, test, Docker, risk.
- 출력: 최종 commit HEAD에 연결된 최신 harness 평가 증거.

- [ ] **단계 1: 서식 및 policy 검사 실행**

실행:

```bash
python3 -m json.tool harness/orchestration-policy.json
python3 -m json.tool harness/risk-policy.json
python3 -m unittest discover -s harness/tests -p 'test_orchestration_policy.py'
docker compose config
git diff --check
```

예상: 모든 명령이 exit 0.

- [ ] **단계 2: 전체 Gradle 테스트 모음 실행**

실행: `./gradlew test --console plain`

예상: `BUILD SUCCESSFUL`이며 실패 테스트가 0개입니다.

- [ ] **단계 3: 검증된 변경 커밋**

단계 1~2의 검사와 테스트가 통과한 뒤 최종 diff 범위를 확인하고, 검증된 변경만 stage하여
다음 commit을 생성합니다.

```bash
git add Dockerfile docker/Dockerfile compose.yaml harness/README.md \
  harness/orchestration-policy.json harness/plans/issue-8-agent-vcs-docker.json \
  harness/risk-policy.json harness/tests/test_orchestration_policy.py \
  docs/ai/orchestration-policy.md \
  docs/superpowers/specs/2026-07-16-agent-vcs-permissions-docker-layout-design.md \
  docs/superpowers/plans/2026-07-16-agent-vcs-permissions-docker-layout.md
git commit -m "feat: 에이전트 VCS 권한과 Docker 경로 명시"
```

- [ ] **단계 4: 최종 clean commit HEAD에서 harness 평가 실행**

단계 3의 commit이 끝난 뒤 작업 폴더가 clean한 최종 commit HEAD에서 다음 명령을
실행합니다. evaluate는 commit 전에 실행하지 않습니다.

실행: `python3 scripts/agent-harness.py evaluate harness/plans/issue-8-agent-vcs-docker.json`

예상: scope, risk, contract, harness, Gradle, oracle, evidence 검사에서 `[PASS]`입니다.

- [ ] **단계 5: 최종 diff 및 status 확인**

실행: `git status --short`, `git diff --stat`, `test ! -e Dockerfile`.

예상: manifest 허용 경로만 변경되어 있고 루트 `Dockerfile`은 없으며
`docker/Dockerfile`은 존재합니다.

- [ ] **단계 6: 최신 evaluate PASS 이후에만 게시**

실행: `python3 scripts/agent-publish.py harness/plans/issue-8-agent-vcs-docker.json`

예상: 이슈 브랜치가 push되고 `Closes #8`을 포함한 `main` 대상 non-draft Ready for review
PR이 생성됩니다.
