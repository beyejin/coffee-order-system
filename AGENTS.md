# AGENTS.md

이 저장소에서 작업하는 AI 에이전트가 따라야 할 최소 규칙과 문서 라우터입니다.

## 항상 적용

- K사 서버 개발 사전과제이며, 구현보다 `왜 이렇게 설계했는가`를 설명하는 것이 중요하다.
- 모든 설명·문서·커밋은 한국어로 작성한다.
- 작업 전 실제 코드와 관련 문서를 읽고, 구현되지 않은 내용을 완료된 것처럼 말하지 않는다.
- 문서와 코드가 다르면 버그다. 설계 변경은 문서를 먼저 갱신한 뒤 구현한다.
- 요구사항에 없는 기능과 인프라는 문제를 증명할 근거가 생기기 전에는 추가하지 않는다.
- 핵심 설계와 비즈니스 로직은 사용자가 설명할 수 있어야 한다. AI는 반례·테스트·리뷰로 이를 돕는다.

## 문서 라우팅

| 작업 | 먼저 읽을 문서 |
|---|---|
| 현재 범위와 진행 상태 확인 | [`README.md`](README.md) |
| 설계 배경과 기술 선택 검토 | [`docs/strategy.md`](docs/strategy.md) |
| 테이블·컬럼·제약 확인 | [`docs/table-spec.md`](docs/table-spec.md) |
| API 요청·응답·에러 확인 | [`docs/api-spec.md`](docs/api-spec.md) |
| 도메인 불변식과 미확정 결정 확인 | [`docs/rules/policy.md`](docs/rules/policy.md) |
| 기능 구현·브랜치·검증 흐름 확인 | [`docs/rules/workflow.md`](docs/rules/workflow.md) |
| 문서·커밋 작성 규칙 확인 | [`docs/rules/conventions.md`](docs/rules/conventions.md) |
| 이전 시도와 실제 검증 결과 확인 | [`docs/logs/`](docs/logs/README.md) |

## 구현 게이트

기능 작업은 `Plan → Generate → Evaluate → Explain` 순서를 따른다.

1. **Plan**: 사용자가 불변식·트랜잭션 경계·예외 케이스를 설명한다. AI는 반례를 찾는다.
2. **Generate**: 확정한 범위의 코드와 테스트만 작성한다.
3. **Evaluate**: 실제 MySQL Testcontainers로 실행하고 결과를 기록한다.
4. **Explain**: 선택 이유, 동시 요청, 실패 시 롤백을 사용자가 설명할 수 있어야 완료한다.

문서에 없는 판단이나 `policy.md`의 미확정 항목이 필요하면 구현 전에 질문한다.
