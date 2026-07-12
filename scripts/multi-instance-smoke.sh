#!/bin/sh
set -eu

gateway_url="${GATEWAY_URL:-http://localhost:18080}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-coffee-order-system}"

fail() {
  echo "SMOKE FAIL: $*" >&2
  exit 1
}

for command_name in curl python3 docker; do
  command -v "$command_name" >/dev/null 2>&1 || fail "필수 명령이 없습니다: ${command_name}"
done
docker compose version >/dev/null 2>&1 || fail "Docker Compose를 사용할 수 없습니다."

temp_dir="$(mktemp -d)"
trap 'rm -rf "$temp_dir"' EXIT INT TERM
upstreams_file="${temp_dir}/upstreams.txt"

docker compose exec -T mysql sh -c \
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -N -s -uroot coffee -e "SELECT u.balance, (SELECT COUNT(*) FROM orders), (SELECT COUNT(*) FROM point_history) FROM user u WHERE u.id = 1"' \
  > "${temp_dir}/initial-db-state.tsv" || fail "초기 공유 MySQL 상태 조회 실패"

python3 - "$temp_dir/initial-db-state.tsv" <<'PY' || fail "fresh DB가 아닙니다. 고유 COMPOSE_PROJECT_NAME을 사용하거나 docker compose down -v --remove-orphans 후 다시 실행하세요."
import sys
values = open(sys.argv[1], encoding="utf-8").read().strip().split()
if values != ["0", "0", "0"]:
    raise SystemExit(f"expected initial DB [0, 0, 0], got {values}")
PY

request() {
  method="$1"
  path="$2"
  body="${3:-}"
  response_body="${temp_dir}/body.json"
  response_headers="${temp_dir}/headers.txt"

  if [ -n "$body" ]; then
    curl --fail --silent --show-error \
      -X "$method" \
      -H 'Content-Type: application/json' \
      -d "$body" \
      -D "$response_headers" \
      -o "$response_body" \
      "${gateway_url}${path}" || fail "${method} ${path} HTTP 요청 실패"
  else
    curl --fail --silent --show-error \
      -X "$method" \
      -D "$response_headers" \
      -o "$response_body" \
      "${gateway_url}${path}" || fail "${method} ${path} HTTP 요청 실패"
  fi

  upstream="$(awk 'tolower($1) == "x-upstream-addr:" { gsub("\r", "", $2); print $2 }' "$response_headers")"
  [ -n "$upstream" ] || fail "${method} ${path} 응답에 X-Upstream-Addr가 없습니다."
  echo "$upstream" >> "$upstreams_file"
}

for request_number in 1 2 3 4; do
  request GET /menus
  python3 - "$temp_dir/body.json" <<'PY' || fail "GET /menus 응답 값이 예상과 다릅니다."
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
if data.get("success") is not True or data.get("error") is not None:
    raise SystemExit(f"unexpected response wrapper: {data}")
if len(data.get("data", [])) != 3:
    raise SystemExit(f"expected 3 menus, got {data.get('data')}")
menu_ids = [menu.get("menuId") for menu in data["data"]]
if menu_ids != [1, 2, 3]:
    raise SystemExit(f"expected menu IDs [1, 2, 3], got {menu_ids}")
PY
done

request POST /users/1/points/charge '{"amount":10000}'
python3 - "$temp_dir/body.json" <<'PY' || fail "포인트 충전 잔액이 10000P가 아닙니다."
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
if data.get("success") is not True:
    raise SystemExit(f"charge failed: {data}")
if data.get("data") != {"userId": 1, "balance": 10000}:
    raise SystemExit(f"unexpected charge data: {data.get('data')}")
PY

request POST /orders '{"userId":1,"menuId":1}'
python3 - "$temp_dir/body.json" <<'PY' || fail "주문 결제 값이 예상과 다릅니다."
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
if data.get("success") is not True:
    raise SystemExit(f"order failed: {data}")
order = data.get("data", {})
expected = {"userId": 1, "menuId": 1, "price": 4500, "remainingBalance": 5500}
actual = {key: order.get(key) for key in expected}
if actual != expected:
    raise SystemExit(f"expected order {expected}, got {actual}")
PY

request GET /menus/popular
python3 - "$temp_dir/body.json" <<'PY' || fail "인기 메뉴 집계 값이 예상과 다릅니다."
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
expected = [{"menuId": 1, "name": "아메리카노", "orderCount": 1}]
if data.get("success") is not True:
    raise SystemExit(f"popular menu request failed: {data}")
if data.get("data") != expected:
    raise SystemExit(f"expected popular menu {expected}, got {data.get('data')}")
PY

upstream_count="$(sort -u "$upstreams_file" | wc -l | tr -d ' ')"
[ "$upstream_count" -ge 2 ] || fail "요청이 두 upstream으로 분산되지 않았습니다."

docker compose exec -T mysql sh -c \
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -N -s -uroot coffee -e "SELECT u.balance, (SELECT COUNT(*) FROM orders), (SELECT COUNT(*) FROM point_history) FROM user u WHERE u.id = 1"' \
  > "${temp_dir}/db-state.tsv" || fail "공유 MySQL 상태 조회 실패"

python3 - "$temp_dir/db-state.tsv" <<'PY' || fail "공유 DB 상태가 balance=5500, orders=1, history=2가 아닙니다."
import sys
values = open(sys.argv[1], encoding="utf-8").read().strip().split()
if values != ["5500", "1", "2"]:
    raise SystemExit(f"expected final DB [5500, 1, 2], got {values}")
PY

echo "SMOKE PASS: menus=3 chargeBalance=10000 orderPrice=4500 remainingBalance=5500 popularMenuId=1 popularCount=1"
echo "SMOKE PASS: upstreams=$(sort -u "$upstreams_file" | paste -sd, -)"
echo "SMOKE PASS: sharedDb balance=5500 orders=1 history=2"
