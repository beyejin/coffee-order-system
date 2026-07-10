# AGENTS.md

이 저장소에서 작업하는 AI 에이전트(Claude Code, Codex 등)가 따라야 할 규칙입니다.
아래는 라우팅 표입니다 — 상황에 맞는 문서를 그때그때 읽으세요. 이 파일 자체는 항상 적용되는 최소 규칙만 담습니다.

## 항상 적용

- K사 서버 개발 채용 사전과제 — 커피숍 주문 시스템. "왜 이렇게 설계했는가"를 설명하는 것이 평가 핵심.
- 모든 설명·문서·커밋은 한국어로 작성한다.
- 문서에 근거 없는 판단은 추측하지 말고 먼저 질문한다.
- 코드와 문서가 다르게 동작하면 버그다 — `docs/*.md`가 항상 진실의 원천이다.

## 라우팅 표 — 지금 뭘 하려는지에 따라 읽을 문서

| 지금 하려는 일 | 읽을 문서 |
|---|---|
| 테이블 구조가 궁금하다 | [`docs/table-spec.md`](docs/table-spec.md) |

[//]: # (| 기능을 구현하려 한다 &#40;Plan/Generate/Evaluate 단계, 브랜치, 로그 규칙이 궁금하다&#41; | [`docs/rules/workflow.md`]&#40;docs/rules/workflow.md&#41; |)

[//]: # (| 문서를 쓰거나 커밋 메시지를 작성한다 | [`docs/rules/conventions.md`]&#40;docs/rules/conventions.md&#41; |)

[//]: # (| 도메인 규칙이 맞는지 헷갈린다 &#40;Order에 status 넣어도 되나? 등&#41;, 동시성/이벤트전송/인기메뉴 같은 보류 항목을 건드리려 한다 | [`docs/rules/policy.md`]&#40;docs/rules/policy.md&#41; |)

[//]: # (| API 요청/응답/에러코드가 궁금하다 | [`docs/api-spec.md`]&#40;docs/api-spec.md&#41; |)

[//]: # (| 설계 배경, 트레이드오프, 기술 선택 이유가 궁금하다 | [`docs/strategy.md`]&#40;docs/strategy.md&#41; |)
