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
  ]
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
  "data": { "userId": 1, "balance": 10000 }
}
```

**실패 케이스**
- `amount <= 0` → 400 `INVALID_CHARGE_AMOUNT`
- 존재하지 않는 `userId` → 404 `USER_NOT_FOUND`

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
  }
}
```

**처리 흐름**
1. 메뉴 존재 여부 검증 (없으면 404 `MENU_NOT_FOUND`)
2. 잔액 검증 (부족하면 409 `INSUFFICIENT_POINT`, 이 경우 `orders` row 생성 안 됨)
3. 하나의 트랜잭션에서: `orders` INSERT + `User.balance` 차감 + `PointHistory`(USE) INSERT
4. 데이터 수집 플랫폼으로 주문 내역 전송
   - 학습 단계: 트랜잭션 내 동기 Mock 호출로 장애 영향을 재현
   - 최종 단계: 실패 테스트 후 `strategy.md` 5.2의 결정 게이트에 따라 확정

**실패 케이스**
- 존재하지 않는 `menuId` → 404 `MENU_NOT_FOUND`
- 존재하지 않는 `userId` → 404 `USER_NOT_FOUND`
- 잔액 부족 → 409 `INSUFFICIENT_POINT`

---

## 4. 인기 메뉴 목록 조회

`GET /menus/popular`

최근 7일간 주문 횟수 기준 상위 3개 메뉴를 반환합니다.

**Response 200**
```json
{
  "success": true,
  "data": [
    { "menuId": 1, "name": "아메리카노", "orderCount": 42 },
    { "menuId": 3, "name": "카페모카", "orderCount": 30 },
    { "menuId": 2, "name": "카페라떼", "orderCount": 18 }
  ]
}
```

집계 방식은 `strategy.md` 5.3 및 `policy.md`의 "보류 항목" 참고 (초기 구현은 실시간 `GROUP BY`).
