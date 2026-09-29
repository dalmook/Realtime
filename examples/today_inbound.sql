-- 로컬 SQLite용. Oracle/Splunk에 실행하는 SQL이 아닙니다.
SELECT business_date, display_unit, latest_rows, box_count, quantity, eq_100m, eq_unmapped_rows
FROM v_inbound_daily
WHERE business_date = strftime('%Y%m%d', 'now', '+9 hours')
ORDER BY business_date, display_unit;
