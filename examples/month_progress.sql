-- 오늘이 속한 월. 계획 버전은 따로 표시하며 합산하지 않습니다.
SELECT direction, period_ym, plan_version, metric,
       material, product_group, customer_key, plant, warehouse,
       monthly_target, actual_to_date, progress_pct, remaining_to_month_target,
       progress_status, reference_loaded_at
FROM v_monthly_progress
WHERE period_ym = strftime('%Y%m', 'now', '+9 hours')
ORDER BY direction, plan_version, metric, material;
