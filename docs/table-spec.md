# 테이블 명세

> 테이블명은 `ORDER`가 MySQL 예약어이므로 `orders`로 명명한다.

## user

| 컬럼 | 타입 | 제약 |
|---|---|---|
| id | BIGINT | PK, AUTO_INCREMENT |
| balance | BIGINT | NOT NULL, DEFAULT 0 |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP |

## point_history

| 컬럼 | 타입 | 제약 |
|---|---|---|
| id | BIGINT | PK, AUTO_INCREMENT |
| user_id | BIGINT | NOT NULL, FK → user.id |
| amount | BIGINT | NOT NULL |
| type | VARCHAR(10) | NOT NULL (`CHARGE` \| `USE`) |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP |

## menu

| 컬럼 | 타입 | 제약 |
|---|---|---|
| id | BIGINT | PK, AUTO_INCREMENT |
| name | VARCHAR(50) | NOT NULL |
| price | BIGINT | NOT NULL |

## orders

| 컬럼 | 타입 | 제약 |
|---|---|---|
| id | BIGINT | PK, AUTO_INCREMENT |
| user_id | BIGINT | NOT NULL, FK → user.id |
| menu_id | BIGINT | NOT NULL, FK → menu.id |
| price | BIGINT | NOT NULL |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP |
