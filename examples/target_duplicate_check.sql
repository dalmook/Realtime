-- 정규화 키 제약은 중복을 막습니다. 목표 합산 전에 버전/그레인을 먼저 확인하세요.
SELECT reference_source, period_ym, plan_version, metric,
       material, product_group, customer_key, plant, warehouse, COUNT(*) AS n
FROM plan_monthly
GROUP BY reference_source, period_ym, plan_version, metric,
         material, product_group, customer_key, plant, warehouse
HAVING COUNT(*) > 1;
