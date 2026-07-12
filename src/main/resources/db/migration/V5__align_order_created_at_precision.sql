-- 적용 전제: 아직 배포 전이며 영속 orders 데이터가 없는 현재 프로젝트 환경이다.
-- 이 마이그레이션은 컬럼 정밀도와 기본값만 정렬하며 기존 시각 데이터는 변환하지 않는다.
-- 기존 V3 스키마에 주문 데이터가 있는 환경은 당시 DB session timezone을 먼저 확인하고,
-- 검증된 별도 CONVERT_TZ 데이터 마이그레이션 없이 이 DDL을 적용하면 안 된다.
ALTER TABLE orders
    MODIFY created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6);
