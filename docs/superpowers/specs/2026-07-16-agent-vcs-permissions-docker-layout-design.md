# 에이전트 VCS 권한과 Docker 경로 설계

## 목표

에이전트 역할별로 저장소 읽기, 제품 파일 쓰기, 로컬 commit, branch push,
PR merge 권한을 machine-readable 정책에 명시하고, 애플리케이션 Dockerfile을
`docker/` 디렉터리 아래에 둔다.

## 현재 문제

`harness/orchestration-policy.json`은 role별 `writer`, `readOnly`, `canApprove`,
`writeScope`와 main orchestrator의 merge 권한은 정의하지만, Git 동작별
`read`·`commit`·`push`·`merge` capability는 별도 필드로 정의하지 않는다.
커밋 절차는 `AGENTS.md`, branch push와 PR provider 호출은
`scripts/agent-publish.py`에 분산되어 있어 역할 계약만 읽고는 실제 VCS 경계를
한눈에 확인하기 어렵다.

현재 루트의 `Dockerfile`은 `compose.yaml`의 `build: .` 암묵 규칙으로 선택된다.
파일을 `docker/Dockerfile`로 이동하면 두 app 서비스가 사용할 Dockerfile을
Compose에 명시해야 한다.

## 설계

### 1. VCS capability 계약

`harness/orchestration-policy.json`에 `vcsCapabilities`를 추가한다.

| actor | 저장소 read | 제품 파일 write | local commit | branch push | PR merge |
|---|---:|---|---:|---:|---:|
| `implementation` | 가능 | `manifest.allowedPaths` | 가능 | 불가 | 불가 |
| `verification` | 가능 | 불가 | 불가 | 불가 | 불가 |
| `qa` | 가능 | 불가 | 불가 | 불가 | 불가 |
| `pr-review` | 가능 | 불가 | 불가 | 불가 | 불가 |
| `main-orchestrator` | 가능 | 불가 | 불가 | 가능 | 가능 |

`implementation`은 검증된 변경을 local commit까지 만들고, `main-orchestrator`의
provider runtime만 branch push와 merge를 수행한다. reviewer는 저장소를 읽고
검증할 수 있지만 파일·commit·push·merge를 수행하지 않는다.

이 capability는 workflow 계약이며 운영체제의 shell 권한이나 GitHub token의
실제 권한을 상승시키지 않는다. 실제 원격 push·PR·merge 가능 여부는
credential과 GitHub repository 설정이 최종적으로 결정한다.

### 2. 문서와 검증

사람용 계약인 `docs/ai/orchestration-policy.md`에 동일한 표와 runtime 권한
분리 원칙을 추가한다. `harness/README.md`에는 machine-readable 정본과
`agent-publish.py`의 역할을 연결한다. `harness/tests/test_orchestration_policy.py`
는 capability 전체 매트릭스와 main orchestrator의 push·merge 경계를 고정한다.

### 3. Docker 경로

루트 `Dockerfile`을 `docker/Dockerfile`로 이동한다. `compose.yaml`의 `app1`과
`app2`는 다음 build 설정을 사용한다.

```yaml
build:
  context: .
  dockerfile: docker/Dockerfile
```

build context는 루트로 유지하므로 `gradlew`, `gradle/`, `src/`, `.dockerignore`
의 기존 COPY 동작과 서비스 런타임은 바뀌지 않는다. `harness/risk-policy.json`
의 multi-instance-runtime 패턴도 `docker/Dockerfile`로 갱신한다.

## 비목표

- GitHub token, branch protection, repository 권한을 자동 변경하지 않는다.
- 제품 애플리케이션에 사용자 인증·인가를 추가하지 않는다.
- Compose 서비스 목록, 네트워크, 환경 변수, 애플리케이션 런타임 동작을 바꾸지 않는다.

## 완료 검증

- JSON policy 단위 테스트가 capability 표와 일치한다.
- `python3 scripts/agent-harness.py evaluate ...`가 PASS한다.
- `docker compose config`가 PASS하고 두 app의 Dockerfile 경로가 `docker/Dockerfile`이다.
- `./gradlew test --console plain`이 PASS한다.
