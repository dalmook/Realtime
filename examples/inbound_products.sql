-- 오늘 제품별 BOX/EA. BOX를 부분합하여 전체 고유 BOX로 사용하지 마세요.
SELECT material, product_name, product_group,
       COUNT(DISTINCT NULLIF(box_no, '')) AS box_count,
       SUM(CASE WHEN unit IN ('PC', 'EA') THEN qty_i ELSE 0 END)/1000000.0 AS ea_qty,
       SUM(CASE WHEN unit NOT IN ('PC', 'EA') THEN 1 ELSE 0 END) AS other_unit_rows
FROM v_inbound_detail
WHERE business_date = strftime('%Y%m%d', 'now', '+9 hours')
GROUP BY material, product_name, product_group
ORDER BY box_count DESC, material;
