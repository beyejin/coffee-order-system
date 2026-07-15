# API 명세서

> 구현 완료 후 실제 API 문서는 springdoc-openapi(Swagger UI, `/swagger-ui.html`)로 자동 생성됩니다. 이 문서는 설계 점검용 초안입니다.

## 공통 사항

### 응답 포맷
```json
{
  "success": true,
  "data": { },
  "error": null
}
```

실패 시:
```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "INSUFFICIENT_POINT",
    "message": "포인트가 부족합니다."
  }
}
```

### 에러 코드 (초안)

| code | HTTP status | 설명 |
|---|---|---|
| `MENU_NOT_FOUND` | 404 | 존재하지 않는 메뉴 ID |
| `USER_NOT_FOUND` | 404 | 존재하지 않는 사용자 ID |
| `INSUFFICIENT_POINT` | 409 | 주문 금액보다 잔액이 부족함 |
| `INVALID_CHARGE_AMOUNT` | 400 | 충전 금액이 0 이하 |
| `POINT_BALANCE_OVERFLOW` | 409 | 충전 후 잔액이 BIGINT 범위를 초과함 |
| `VALIDATION_ERROR` | 400 | 요청 파라미터 형식 오류 |

---

## 1. 커피 메뉴 목록 조회

`GET /menus`

**Response 200**
```json
{
  "success": true,
  "data": [
    { "menuId": 1, "name": "아메리카노", "price": 4500 },
    { "menuId": 2, "name": "카페라떼", "price": 5000 }
  ],
  "error": null
}
```

---

## 2. 포인트 충전

`POST /users/{userId}/points/charge`

**Request Body**
```json
{ "amount": 10000 }
```

**Response 200**
```json
{
  "success": true,
  "data": { "userId": 1, "balance": 10000 },
  "error": null
}
```

**실패 케이스**
- `amount <= 0` 또는 누락 → 400 `VALIDATION_ERROR`
- 존재하지 않는 `userId` → 404 `USER_NOT_FOUND`
- 충전 후 잔액이 BIGINT 범위를 초과 → 409 `POINT_BALANCE_OVERFLOW`
- 잘못된 JSON, 빈 요청 본문, 소수 충전 금액 → 400 `VALIDATION_ERROR`
- 숫자가 아닌 `userId` → 400 `VALIDATION_ERROR`

---

## 3. 주문 / 결제

`POST /orders`

**Request Body**
```json
{ "userId": 1, "menuId": 1 }
```

**Response 200**
```json
{
  "success": true,
  "data": {
    "orderId": 100,
    "userId": 1,
    "menuId": 1,
    "price": 4500,
    "remainingBalance": 5500
  },
  "error": null
}
```

**처리 흐름**
1. 메뉴 존재 여부 검증 (없으면 404 `MENU_NOT_FOUND`)
2. 잔액 검증 (부족하면 409 `INSUFFICIENT_POINT`, 이 경우 `orders` row 생성 안 됨)
3. 하나의 트랜잭션에서: `orders` INSERT + `User.balance` 차감 + `PointHistory`(USE) INSERT
4. 데이터 수집 플랫폼으로 주문 내역 전송
   - DB 커밋 후 `AFTER_COMMIT` 이벤트를 비동기로 처리
   - 사용자 ID, 메뉴 ID, 결제금액을 Mock client로 전송
   - 외부 실패는 주문 응답과 이미 커밋된 DB를 변경하지 않음
   - 현재는 재시도·영속 이벤트가 없어 전송 유실 가능성이 있음

**실패 케이스**
- 존재하지 않는 `menuId` → 404 `MENU_NOT_FOUND`
- 존재하지 않는 `userId` → 404 `USER_NOT_FOUND`
- 잔액 부족 → 409 `INSUFFICIENT_POINT`
- 잘못된 JSON, 빈 요청 본문, 누락된 ID → 400 `VALIDATION_ERROR`

---

## 4. 인기 메뉴 목록 조회

`GET /menus/popular`

최근 7일간 주문 횟수 기준 상위 3개 메뉴를 반환합니다.

- 조회 시각 `to`를 UTC 기준으로 한 번 고정하고 DB 정밀도와 같은 microsecond로 절삭합니다.
- 집계 구간은 `[to - 7일, to)`입니다. 시작 시각 주문은 포함하고 `to`와 같은 시각의 주문은 제외합니다.
- 주문 횟수 내림차순, 동률이면 메뉴 ID 오름차순으로 정렬합니다.
- 응답 이름은 주문 시점 이름이 아니라 현재 `menus.name`입니다.
- 주문 API도 같은 UTC `Clock`으로 주문 시각을 캡처해 `DATETIME(6)`에 저장합니다.

**Response 200**
```json
{
  "success": true,
  "data": [
    { "menuId": 1, "name": "아메리카노", "orderCount": 42 },
    { "menuId": 3, "name": "카페모카", "orderCount": 30 },
    { "menuId": 2, "name": "카페라떼", "orderCount": 18 }
  ],
  "error": null
}
```
