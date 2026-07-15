# 개발 방법 (Conventions)

## 문서 작성

- 설계를 바꾸는 코드 변경 전에는 관련 `docs/*.md`(진실의 원천)를 먼저 갱신한다. 문서 주도 개발(document-driven development)이 원칙이다 — 코드가 문서를 따라가야지, 문서가 코드를 사후 설명해서는 안 된다.
- 모든 문서는 한국어로 작성한다. 코드 식별자·기술 용어는 영어를 유지해도 된다.
- `docs/strategy.md` 5장의 전략 상태는 선택·학습 단계·미확정을 구분한다. 결정이 바뀌면 관련 문서와 함께 갱신한다.

## 작업 격리와 변경 범위

- 최신 `origin/main`에서 issue 전용 clean worktree와 `(feature|fix|refactor|docs)/{이슈번호}-{lowercase-kebab}` branch를 사용한다.
- 제품 파일보다 먼저 `harness/plans/{issue}.json`을 작성하고 모든 변경 경로를 좁은 allowedPaths에 연결한다.
- 선택한 plan 외 dirty 파일이 있으면 prepare하지 않으며 기존 변경을 자동 stash하거나 삭제하지 않는다.
- 기존 Flyway migration은 수정하거나 삭제하지 않는다. schema 변경은 새 migration과 fresh·upgrade 검증으로 추가한다.
- harness, contract, 필수 oracle와 workflow 변경은 contractChanges에 선언하고 trust-root 검토를 받는다.

## 작업 게시와 완료 기준

- 로컬 `main`에 직접 커밋하거나 병합하지 않는다. 모든 변경은 최신 `origin/main`에서 만든 issue 전용 branch에서 시작한다.
- 한 작업은 하나의 issue, branch, manifest와 PR로 추적한다.
- 변경 범위 테스트를 통과한 뒤 커밋하고, 최종 커밋 HEAD에서 하네스를 다시 평가한다.
- 평가를 통과한 branch를 push하고 `main` 대상 Ready for review PR을 만든 상태를 기본 완료로 본다.
- Draft PR은 사용자가 명시적으로 요청한 경우에만 사용한다.
- 사용자가 명시적으로 `local-only` 또는 push 금지를 요청한 경우에만 PR 생성을 생략하고 branch·commit과 원격 미게시 상태를 보고한다.
- 사용자의 일반 변경 요청은 Commit과 Publish까지 포함한다. Merge는 별도 요청이 있을 때만 수행한다.
- CI와 리뷰 전에는 merge하지 않으며 사용자가 요청하지 않은 자동 merge를 수행하지 않는다.

## 패키지 구조

- `domain/{도메인}` 아래에 `controller`, `dto`, `entity`, `repository`, `service`를 둔다.
- 전역 설정·예외·공통 응답은 각각 `global/config`, `global/error`, `global/response`에 둔다.
- 외부 시스템 구현은 `infra/{외부시스템}`에 두고, 도메인 패키지에 인프라 구현을 섞지 않는다.
- 패키지 이동만을 위한 리팩터링에서는 API 계약, DB 스키마, 비즈니스 로직을 변경하지 않는다.

## 커밋 메시지

Conventional Commits 형식(`type: 설명`)을 한국어로 작성한다.

| type | 용도 |
|---|---|
| `feat` | 기능 추가 |
| `fix` | 버그 수정 |
| `test` | 테스트 추가/수정 |
| `docs` | 문서 변경 |
| `refactor` | 동작 변화 없는 구조 개선 |
| `chore` | 빌드/설정 등 그 외 |

예: `feat: 포인트 충전 API 구현`, `test: 동시 주문 시나리오 테스트 추가`, `docs: ERD에 인덱스 설계 추가`

## 커밋과 기능 로그의 역할

- 커밋은 어떤 파일을 왜 변경했는지 기록합니다.
- `docs/logs/{기능}.md`는 실제 실패·원인·검증 결과·배운 점만 기록합니다. 파일 생성 목록이나 커밋 내용은 반복하지 않습니다.
- 설계 판단과 트레이드오프는 `docs/strategy.md`에 남깁니다. 기능 로그가 설계의 정본을 대신하지 않습니다.
