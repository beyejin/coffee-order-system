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
| created_at | DATETIME(6) | NOT NULL, DEFAULT CURRENT_TIMESTAMP(6), UTC |

인기 메뉴 기간 조회를 위해 `orders(created_at, menu_id)` 복합 인덱스를 사용한다.

V5의 `DATETIME(6)` 변경은 배포 전이며 영속 주문 데이터가 없는 현재 환경을 전제로 한 스키마 정밀도 정렬이다. 기존 V3 주문 데이터가 있다면 저장 당시 DB session timezone을 확인한 뒤 별도 데이터 마이그레이션을 설계해야 하며, 검증된 `CONVERT_TZ` 없이 V5를 적용하거나 기존 데이터를 임의 변환·삭제하지 않는다.
