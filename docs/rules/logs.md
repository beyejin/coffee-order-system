# 개발 로그 (Logs)

Evaluate 단계에서의 **실행 이력·증거**를 남기는 방법이다. 두 역할을 한다:

1. **피드백 센서** — 실패 후 재시도할 때, 이전에 뭘 시도했고 왜 실패했는지 참고한다 (특히 세션이 끊기거나 컨텍스트가 압축된 뒤 재개할 때 중요).
2. **증거** — "이 기능이 실제로 이렇게 동작했다"를 튜터에게 보일 수 있는 근거.

> `docs/strategy.md`·`erd.md`·`api-spec.md`는 **스펙(계획·현재 상태)**이고, 로그는 **실행 증거(raw 이력)**다. 서로 안 겹친다 — 스펙은 덮어쓰고, 로그는 append-only로 쌓는다.

## 위치 & 이름

```
docs/logs/{기능}.md      예: docs/logs/point-charge.md, docs/logs/order.md, docs/logs/concurrency-test.md
```

`branch.md`의 브랜치 이름과 1:1로 맞춘다 (`feature/{기능}` ↔ `docs/logs/{기능}.md`).

## 무엇을 기록하나

- **성공·실패 매 시도를 모두** 기록한다 (append-only, 지우거나 고치지 않는다). 실패를 빼면 같은 실수를 반복하기 쉽다.
- 각 기록은 짧은 요약으로 남긴다. 테스트 로그 원문을 통째로 붙여넣지 않는다 — 노이즈는 판단을 방해한다.
- 백엔드 증거로는 **API 요청/응답 샘플**이 가장 핵심이다. 필요하면 테스트 결과 요약, DB before/after 샘플도 남긴다.

## 템플릿

```markdown
# point-charge — 로그

## Attempt 1 — 2026-07-11  ❌ FAIL
- 시도: 포인트 충전 API 구현
- 결과: `amount = 0` 요청이 400이 아니라 200으로 처리됨
- 원인: 검증 조건이 `amount < 0`으로만 되어 있어 0을 걸러내지 못함
- 다음: `amount <= 0` 검증으로 수정

## Attempt 2 — 2026-07-11  ✅ PASS
- 시도: 검증 조건을 `amount <= 0`으로 수정
- 결과: 통합 테스트 전체 통과 (Testcontainers MySQL)
- 증거:
  - `POST /users/1/points/charge {"amount": 0}` → `400 {"error":{"code":"INVALID_CHARGE_AMOUNT"}}`
  - `POST /users/1/points/charge {"amount": 10000}` → `200 {"data":{"userId":1,"balance":10000}}`
```

## 언제 쓰나

`workflow.md`의 Evaluate 단계마다 시도 결과를 이 파일에 추가한다 — 통과한 시도도 남긴다 (마지막에 통과했다는 사실 자체가 증거).
