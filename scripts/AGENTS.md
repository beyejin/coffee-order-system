# scripts 작업 라우터

스크립트는 검증 절차를 자동화하는 최소 도구입니다. 실행 조건이나 판정 기준을 바꾸면 관련 README·로그와 함께 수정합니다.

| 스크립트 | 목적 | 실행 조건 | 검증 명령·성공 기준 |
|---|---|---|---|
| [`check-doc-context.py`](check-doc-context.py) | 로컬 Markdown 링크와 `src/AGENTS.md` 컨텍스트 커버리지 검사 | 저장소 루트, Python 3 | `python3 scripts/check-doc-context.py` → 두 항목 모두 `[PASS]` |
| [`multi-instance-smoke.sh`](multi-instance-smoke.sh) | nginx를 경유한 두 앱 인스턴스 분산과 공유 MySQL 상태 검증 | `curl`, Python 3, Docker Compose, 고유 `COMPOSE_PROJECT_NAME`의 fresh DB, 전체 compose stack 기동 | `./scripts/multi-instance-smoke.sh` → HTTP·upstream·공유 DB `SMOKE PASS` 3줄 |

다중 인스턴스 검증은 [`README.md`](../README.md)의 환경 변수 설정과 기동·정리 순서를 그대로 사용합니다. 실패·성공 증거는 [`docs/logs/multi-instance.md`](../docs/logs/multi-instance.md)에 기록합니다.

스크립트가 검증하는 제품 동작을 바꾸지 말고, 제품 계약이 먼저 바뀐 경우에만 스크립트의 기대값을 동기화합니다.
