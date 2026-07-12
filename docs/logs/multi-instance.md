# multi-instance — 로그

## Plan — 2026-07-12
- 구성: nginx gateway 하나가 동일 이미지의 `app1`, `app2`로 요청을 분산하고 두 앱은 하나의 MySQL을 공유한다.
- 상태: 앱은 세션·로컬 상태를 사용하지 않으며 잔액·주문·인기 집계의 정본은 공유 MySQL이다.
- 시간: MySQL, JDBC session, 두 JVM 모두 UTC를 사용한다.
- 검증: `docker compose -p coffee-multi-verify up -d --build --wait`로 실제 기동한 뒤 gateway를 통해 필수 API 4개를 호출한다.
- 분산 증거: nginx access log의 서로 다른 `upstream` 주소와 각 앱 컨테이너 IP를 대조한다.
- 공유 상태 증거: 한 upstream을 통해 충전하고 다른 upstream을 포함한 gateway 요청으로 주문·인기 메뉴 결과가 같은 DB 상태를 반영하는지 확인한다.
- 정리: 검증 후 `docker compose -p coffee-multi-verify down -v`로 컨테이너·네트워크·검증 볼륨을 제거한다.
- 범위 제외: 배포 플랫폼, Kafka, Redis는 추가하지 않는다.

## Attempt 1 — 2026-07-12 ❌ FAIL
- 현상: Apple Silicon에서 `eclipse-temurin:17-jdk-alpine` builder image를 찾지 못해 애플리케이션 이미지 빌드가 시작되지 않았다.
- 원인: 해당 태그가 현재 Docker platform용 manifest를 제공하지 않았다.
- 다음: 멀티 아키텍처 Temurin Jammy 이미지로 변경하고 runtime에는 health check용 curl만 설치한다.

## Attempt 2 — 2026-07-12 ✅ PASS
- 기동: `DB_PORT=13316 GATEWAY_PORT=18080 docker compose -p coffee-multi-verify up -d --build --wait` 성공. MySQL, `app1`, `app2`가 healthy이고 nginx가 시작됐다.
- 호환: 별도 프로젝트에서 `docker compose up -d --wait mysql`을 실행했을 때 실행 서비스 목록이 `mysql` 하나뿐임을 확인해 기존 MySQL 단독 실행 흐름을 유지했다.
- 메뉴: gateway `GET /menus` 4회 모두 200으로 메뉴 3개를 반환했다.
- 충전: `POST /users/1/points/charge`를 `app2(172.18.0.3)`가 처리해 잔액 10,000P를 반환했다.
- 주문: `POST /orders`를 `app1(172.18.0.4)`이 처리해 주문 ID 1, 결제금액 4,500P, 잔액 5,500P를 반환했다.
- 인기: `GET /menus/popular`를 다시 `app2`가 처리해 아메리카노 주문 수 1건을 반환했다.
- 분산 증거: nginx access log에서 `upstream=172.18.0.3:8080`과 `upstream=172.18.0.4:8080`을 모두 확인했고, container inspect 결과 각각 `app2`, `app1` IP와 일치했다.
- 공유 DB: MySQL에서 사용자 잔액 5,500P, 주문 1건, 포인트 이력 2건(`CHARGE`, `USE`), 주문의 사용자 1·메뉴 1·가격 4,500P를 확인했다.
- 회귀: `./gradlew clean test --console plain` 성공, 전체 29개 테스트가 통과했다. `docker compose config`와 `git diff --check`도 통과했다.
- 정리: `docker compose -p coffee-multi-verify down -v --remove-orphans` 후 검증 container와 volume이 남지 않은 것을 확인했다.
- 배운 점: nginx가 서로 다른 인스턴스로 쓰기와 읽기를 보내도 공유 MySQL을 정본으로 사용하면 일관된 잔액·주문·집계 결과를 유지한다.

## Review fix Attempt 1 — 2026-07-12 ❌ FAIL
- 현상: nginx 프로세스는 정상 기동했지만 자체 health check가 `connection refused`로 실패했다.
- 원인: health target의 `localhost`가 IPv6 `::1`로 해석됐고, read-only nginx 설정에는 IPv6 listen이 없어 연결할 수 없었다.
- 다음: health target을 명시적인 IPv4 `127.0.0.1`로 변경한다.

## Review fix Attempt 2 — 2026-07-12 ✅ PASS
- 자동 smoke: `COMPOSE_PROJECT_NAME=coffee-multi-review GATEWAY_URL=http://localhost:18081 ./scripts/multi-instance-smoke.sh`가 메뉴 3개, 충전 잔액 10,000P, 주문 가격 4,500P·잔액 5,500P, 인기 메뉴 ID 1·주문 수 1, 공유 DB 잔액 5,500P·주문 1건·이력 2건을 모두 검증하고 PASS했다.
- 분산 판정: 응답의 개발 검증용 `X-Upstream-Addr`를 모아 `172.18.0.3:8080`, `172.18.0.4:8080` 두 upstream 사용을 자동 확인했다.
- 실패 동작: 접근 불가능한 gateway로 실행했을 때 exit code 1과 `SMOKE FAIL: GET /menus HTTP 요청 실패`를 반환했고 임시 디렉터리 항목은 0개로 정리됐다.
- 동적 DNS: nginx 1.27.5의 Docker resolver `127.0.0.11`, upstream zone과 `resolve`를 사용했다. app1 이전 IP `172.18.0.4`를 검증용 컨테이너가 잠시 점유한 상태에서 `--force-recreate`해 새 IP `172.18.0.6`을 만들었다.
- 재생성 증거: DNS TTL 후 gateway 요청 6건이 모두 200이었고 `X-Upstream-Addr`와 nginx log에서 새 app1 `172.18.0.6`과 app2 `172.18.0.3`이 번갈아 사용됐다.
- gateway health: IPv4 `127.0.0.1/menus` HTTP health check 적용 후 nginx가 healthy가 되어 `docker compose up -d --wait`가 정상 완료됐다.
- 호환·회귀: MySQL 단독 실행 서비스가 `mysql` 하나임을 다시 확인했고, `./gradlew clean test --console plain` 전체 29개 테스트, nginx config, Compose config, shell syntax, `git diff --check`가 통과했다.
- cleanup: `down -v --remove-orphans` 후 검증용 다중 인스턴스·MySQL 단독 프로젝트의 컨테이너, 네트워크, 볼륨이 남지 않았다.

## Review fix Attempt 3 — 2026-07-12 ✅ PASS
- 버전 고정: Compose nginx image를 동적 DNS와 health 검증에 실제 사용한 `nginx:1.27.5-alpine`로 고정하고 해당 이미지의 `nginx -t`를 통과했다.
- 최적화 안전성: smoke의 모든 Python `assert`를 명시적 조건문과 `SystemExit`로 교체했다. `PYTHONOPTIMIZE=1`에서도 전체 자동 smoke가 PASS해 검증 로직이 제거되지 않음을 확인했다.
- fresh 사전조건: smoke 시작 전 잔액 0P·주문 0건·이력 0건을 확인한다. 같은 DB에서 재실행했을 때 exit code 1과 실제 상태 `[5500, 1, 2]`, 고유 `COMPOSE_PROJECT_NAME` 또는 `down -v --remove-orphans` 안내를 반환했다.
- 격리 실행: `coffee-multi-final` 프로젝트의 fresh volume에서 메뉴·충전·주문·인기·upstream 2개·공유 DB 검증이 모두 PASS했다.
- 재생성: app1을 `172.20.0.3`에서 `172.20.0.6`으로 재생성한 뒤 gateway가 새 app1과 app2 `172.20.0.4`에 번갈아 200 응답을 전달했다.
- 문서: README 검증 명령을 시간 기반 고유 프로젝트 이름과 검증 전용 `down -v --remove-orphans`로 변경하고, 일반 MySQL 개발 종료는 볼륨을 보존하는 `down`으로 구분했다. ERD는 `USER.created_at DATETIME`, `ORDERS.created_at DATETIME(6)`으로 migration과 일치시켰다.
- 회귀·정리: MySQL 단독 실행, 전체 29개 테스트, Compose config, shell syntax, nginx config, diff 검사를 통과했고 모든 검증 컨테이너·네트워크·볼륨을 제거했다.

## Review fix Attempt 4 — 2026-07-12 ✅ PASS
- README 검증 블록에서 고유 `COMPOSE_PROJECT_NAME`, 비기본 `DB_PORT=13316`, `GATEWAY_PORT=18081`, 포트에서 파생한 `GATEWAY_URL`을 같은 셸에 export하도록 변경했다.
- 사용 중인 포트는 다른 빈 포트로 교체하고, 기동·smoke·로그·종료 명령 전체에서 같은 환경변수를 유지해야 함을 명시했다.
- 실제 컨테이너를 재기동하지 않고 해당 환경변수의 Compose config 확장, smoke shell 문법, README 내부 링크, diff를 검증했다.
