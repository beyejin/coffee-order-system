# 브랜치 전략 (Branch)

개인 프로젝트지만 기능 단위로 작업을 분리해 커밋 이력을 명확하게 남긴다. PR은 열지 않는다 — 리뷰어가 없고, 커밋 메시지 자체가 이미 변경 근거를 담기 때문이다 (`conventions.md` 참고).

## 브랜치 이름

`feature/{기능}` — `api-spec.md`의 API 단위와 맞춘다.

예: `feature/menu-list`, `feature/point-charge`, `feature/order`, `feature/popular-menu`

동시성 테스트처럼 특정 API에 속하지 않는 작업은 `feature/{주제}`로 자유롭게 명명한다 (예: `feature/concurrency-test`).

## 흐름

1. **Plan 시작 시** `main`에서 분기한다: `git switch -c feature/{기능} main`
2. 구현 중 커밋은 이 브랜치 위에 계속 쌓는다.
3. **Evaluate 통과 후** `main`으로 되돌아가 병합한다: `git switch main && git merge --no-ff feature/{기능}`
   - `--no-ff`로 병합 커밋을 남겨, 나중에도 "이 기능이 어느 범위의 커밋들로 이루어졌는지" 로그에서 구분 가능하게 한다.
4. 병합 후 로컬 브랜치는 삭제해도 되고 남겨도 된다 (기록 목적이면 유지).

## 예외 — 문서 전용 변경

`docs/*.md`만 바꾸는 커밋(설계 문서 갱신, 이 저장소의 규칙 문서 자체 수정 등)은 브랜치를 만들지 않고 `main`에 직접 커밋한다. 브랜치 전략은 **코드 변경**(구현)에만 적용한다 — 문서 작업까지 브랜치로 나누면 오히려 오버헤드만 커진다.

## main 직접 커밋 금지 (코드 한정)

코드(`src/`)를 변경하는 커밋은 `feature/{기능}` 브랜치 위에서만 만든다. `main`에 코드를 직접 커밋하지 않는다.
