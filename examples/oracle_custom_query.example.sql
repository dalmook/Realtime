-- 이 파일은 실제 Oracle SQL을 사용하는 query_file 지정 예시입니다.
-- 제품 정보는 확인된 컬럼만 사용합니다. 제품 GROUP/name 충돌은 로더에서 검증합니다.
SELECT ITEM, PRODUCT, PRODUCTGROUP
FROM MST_PAX_ITEM
WHERE ITEM IS NOT NULL
