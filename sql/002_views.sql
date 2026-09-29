DROP VIEW IF EXISTS v_shipment_customer_monthly;
DROP VIEW IF EXISTS v_shipment_group_monthly;
DROP VIEW IF EXISTS v_shipment_plan_progress;
DROP VIEW IF EXISTS v_inbound_plan_progress;
-- Consumers need only these local SQL views; no Oracle/Splunk calls occur here.
DROP VIEW IF EXISTS v_monthly_progress;
DROP VIEW IF EXISTS v_plan_match;
DROP VIEW IF EXISTS v_inbound_daily;
DROP VIEW IF EXISTS v_shipment_daily;
DROP VIEW IF EXISTS v_inbound_product_monthly;
DROP VIEW IF EXISTS v_shipment_product_monthly;
DROP VIEW IF EXISTS v_inventory_balance;
DROP VIEW IF EXISTS v_inbound_detail;
DROP VIEW IF EXISTS v_shipment_detail;
DROP VIEW IF EXISTS v_inventory_detail;
DROP VIEW IF EXISTS v_fact_enriched;
DROP VIEW IF EXISTS v_fact_all;
DROP VIEW IF EXISTS v_source_health;
CREATE VIEW v_fact_all AS
SELECT 'inbound' AS domain,source_id,record_key,document_no,box_no,material,qty_i,amount_i,unit,plant,warehouse,location,customer_key,business_date,business_time,business_us,modified_us,generated_us,indexed_us,event_hash,scope_ok,deleted,payload_json FROM inbound_current
UNION ALL SELECT 'inventory' AS domain,source_id,record_key,document_no,box_no,material,qty_i,amount_i,unit,plant,warehouse,location,customer_key,business_date,business_time,business_us,modified_us,generated_us,indexed_us,event_hash,scope_ok,deleted,payload_json FROM inventory_current
UNION ALL SELECT 'shipment' AS domain,source_id,record_key,document_no,box_no,material,qty_i,amount_i,unit,plant,warehouse,location,customer_key,business_date,business_time,business_us,modified_us,generated_us,indexed_us,event_hash,scope_ok,deleted,payload_json FROM shipment_current;
CREATE VIEW v_fact_enriched AS
SELECT f.*, COALESCE(NULLIF(p.product_name,''), f.material) AS product_name,
 COALESCE(NULLIF(p.product_group,''),'UNMAPPED') AS product_group,
 COALESCE(NULLIF(c.customer_name,''),f.customer_key) AS customer_name,
 COALESCE(c.customer_group,'') AS customer_group,
 CASE WHEN f.unit='PC' THEN 'EA' ELSE f.unit END AS display_unit,
 CASE WHEN f.unit IN ('PC','EA') THEN f.qty_i END AS ea_i,
 CASE WHEN v.event_hash=f.event_hash AND v.reference_revision=CAST(m.value AS INTEGER) THEN v.eq_i END AS eq_i,
 CASE WHEN v.event_hash=f.event_hash AND v.reference_revision=CAST(m.value AS INTEGER) THEN v.eq_dram_i END AS eq_dram_i,
 CASE WHEN v.event_hash=f.event_hash AND v.reference_revision=CAST(m.value AS INTEGER) THEN v.eq_flash_i END AS eq_flash_i,
 CASE WHEN p.material IS NULL THEN 0 ELSE 1 END AS product_mapped
FROM v_fact_all f
LEFT JOIN dim_product p ON f.material=p.material
 AND EXISTS(SELECT 1 FROM reference_state s WHERE s.source_id=p.reference_source AND s.projection_ready=1)
LEFT JOIN dim_customer c ON f.customer_key=c.customer_key
 AND EXISTS(SELECT 1 FROM reference_state s WHERE s.source_id=c.reference_source AND s.projection_ready=1)
LEFT JOIN fact_valuation v ON f.source_id=v.source_id AND f.record_key=v.record_key
LEFT JOIN meta m ON m.key='reference_revision';
CREATE VIEW v_inbound_detail AS SELECT * FROM v_fact_enriched WHERE domain='inbound' AND scope_ok=1 AND deleted=0;
CREATE VIEW v_inventory_detail AS SELECT * FROM v_fact_enriched WHERE domain='inventory' AND scope_ok=1 AND deleted=0;
CREATE VIEW v_shipment_detail AS SELECT * FROM v_fact_enriched WHERE domain='shipment' AND scope_ok=1 AND deleted=0;
CREATE VIEW v_inbound_daily AS
SELECT source_id,business_date,display_unit,COUNT(*) AS latest_rows,
 COUNT(DISTINCT NULLIF(box_no,'')) AS box_count, SUM(qty_i) AS qty_i, SUM(qty_i)/1000000.0 AS quantity,
 SUM(CASE WHEN box_no='' THEN 1 ELSE 0 END) AS missing_box_rows,
 CASE WHEN COUNT(eq_i)=COUNT(*) THEN SUM(eq_i)/100000000000000.0 END AS eq_100m,
 COUNT(*)-COUNT(eq_i) AS eq_unmapped_rows
FROM v_inbound_detail GROUP BY source_id,business_date,display_unit;
CREATE VIEW v_shipment_daily AS
SELECT source_id,business_date,display_unit,COUNT(*) AS latest_rows,
 COUNT(DISTINCT NULLIF(box_no,'')) AS box_count, SUM(qty_i) AS qty_i, SUM(qty_i)/1000000.0 AS quantity,
 COUNT(*)-COUNT(eq_i) AS eq_unmapped_rows
FROM v_shipment_detail GROUP BY source_id,business_date,display_unit;
CREATE VIEW v_inbound_product_monthly AS
SELECT source_id,substr(business_date,1,6) AS period_ym,material,product_name,product_group,display_unit,
 COUNT(*) AS latest_rows,COUNT(DISTINCT NULLIF(box_no,'')) AS box_count,
 SUM(qty_i) AS qty_i,SUM(qty_i)/1000000.0 AS quantity,
 CASE WHEN COUNT(eq_i)=COUNT(*) THEN SUM(eq_i)/100000000000000.0 END AS eq_100m
FROM v_inbound_detail GROUP BY source_id,substr(business_date,1,6),material,product_name,product_group,display_unit;
CREATE VIEW v_shipment_product_monthly AS
SELECT source_id,substr(business_date,1,6) AS period_ym,material,product_name,product_group,display_unit,
 COUNT(*) AS latest_rows,COUNT(DISTINCT NULLIF(box_no,'')) AS box_count,
 SUM(qty_i) AS qty_i,SUM(qty_i)/1000000.0 AS quantity
FROM v_shipment_detail GROUP BY source_id,substr(business_date,1,6),material,product_name,product_group,display_unit;
-- Inventory is a current balance; it is NEVER summed across collection timestamps.
CREATE VIEW v_inventory_balance AS
SELECT source_id,material,product_name,product_group,warehouse,location,display_unit,
 COUNT(*) AS latest_rows,COUNT(DISTINCT NULLIF(box_no,'')) AS box_count,
 SUM(qty_i) AS qty_i,SUM(qty_i)/1000000.0 AS quantity,MAX(modified_us) AS latest_modified_us
FROM v_inventory_detail GROUP BY source_id,material,product_name,product_group,warehouse,location,display_unit;
CREATE VIEW v_plan_match AS
SELECT p.*, rs.loaded_at AS reference_loaded_at, COUNT(f.record_key) AS matched_rows,
 (SELECT COUNT(*) FROM v_fact_enriched x
  WHERE x.domain=p.direction AND x.scope_ok=1 AND x.deleted=0
   AND EXISTS(SELECT 1 FROM plan_actual_source ax WHERE ax.plan_source=p.reference_source AND ax.actual_source=x.source_id)
   AND x.business_date>=p.period_ym||'01' AND x.business_date<p.period_ym||'32'
   AND x.business_us<=CAST(strftime('%s','now') AS INTEGER)*1000000
   AND (p.material='*' OR p.material=x.material)
   AND (p.plant='*' OR p.plant=x.plant)
   AND (p.warehouse='*' OR p.warehouse=x.warehouse)
   AND ((p.product_group<>'*' AND x.product_mapped=0) OR (p.customer_key<>'*' AND x.customer_key=''))
 ) AS unmapped_dimension_rows,
 CASE p.metric
 WHEN 'BOX' THEN COUNT(DISTINCT NULLIF(f.box_no,''))*1000000
 WHEN 'EA' THEN COALESCE(SUM(f.ea_i),0)
 WHEN 'EQ' THEN COALESCE(SUM(f.eq_i),0)
 WHEN 'USD' THEN COALESCE(SUM(f.amount_i),0) END AS observed_actual_i,
 SUM(CASE WHEN f.record_key IS NOT NULL AND p.metric='EQ' AND f.eq_i IS NULL THEN 1 ELSE 0 END) AS missing_conversion_rows,
 SUM(CASE WHEN f.record_key IS NOT NULL AND p.metric='EA' AND f.ea_i IS NULL THEN 1 ELSE 0 END) AS wrong_unit_rows,
 SUM(CASE WHEN f.record_key IS NOT NULL AND p.metric='BOX' AND f.box_no='' THEN 1 ELSE 0 END) AS missing_box_rows,
 MAX(f.business_us) AS latest_business_us
FROM plan_monthly p
JOIN reference_state rs ON p.reference_source=rs.source_id AND rs.projection_ready=1
LEFT JOIN v_fact_enriched f ON f.domain=p.direction AND f.scope_ok=1 AND f.deleted=0
 AND EXISTS(SELECT 1 FROM plan_actual_source a WHERE a.plan_source=p.reference_source AND a.actual_source=f.source_id)
 AND f.business_date >= p.period_ym||'01' AND f.business_date < p.period_ym||'32'
 AND f.business_us<=CAST(strftime('%s','now') AS INTEGER)*1000000
 AND (p.material='*' OR p.material=f.material)
 AND (p.product_group='*' OR p.product_group=f.product_group)
 AND (p.customer_key='*' OR p.customer_key=f.customer_key)
 AND (p.plant='*' OR p.plant=f.plant)
 AND (p.warehouse='*' OR p.warehouse=f.warehouse)
GROUP BY p.plan_id;
CREATE VIEW v_monthly_progress AS
WITH status_calc AS (
 SELECT m.*,
 CASE
 WHEN m.scope_confirmed=0 THEN 'SCOPE_UNCONFIRMED'
 WHEN NOT EXISTS(SELECT 1 FROM plan_actual_source a WHERE a.plan_source=m.reference_source) THEN 'ACTUAL_SOURCE_UNMAPPED'
 WHEN EXISTS(SELECT 1 FROM plan_actual_source a LEFT JOIN source_state s ON a.actual_source=s.source_id
   WHERE a.plan_source=m.reference_source AND (s.source_id IS NULL OR s.enabled=0)) THEN 'ACTUAL_SOURCE_NOT_CONFIGURED'
 WHEN EXISTS(SELECT 1 FROM plan_actual_source a JOIN source_state s ON a.actual_source=s.source_id
   WHERE a.plan_source=m.reference_source AND s.last_error IS NOT NULL) THEN 'SOURCE_ERROR'
 WHEN EXISTS(SELECT 1 FROM plan_actual_source a JOIN source_state s ON a.actual_source=s.source_id
   WHERE a.plan_source=m.reference_source AND (s.last_success IS NULL OR s.coverage_from IS NULL OR
     s.coverage_from>CAST(strftime('%s',substr(m.period_ym,1,4)||'-'||substr(m.period_ym,5,2)||'-01 00:00:00','-9 hours') AS INTEGER))) THEN 'PARTIAL_HISTORY'
 WHEN EXISTS(SELECT 1 FROM plan_actual_source a JOIN source_state s ON a.actual_source=s.source_id
   WHERE a.plan_source=m.reference_source AND s.watermark < MIN(
     CAST(strftime('%s',substr(m.period_ym,1,4)||'-'||substr(m.period_ym,5,2)||'-01 00:00:00','+1 month','-9 hours') AS INTEGER),
     CAST(strftime('%s','now') AS INTEGER)-300)) THEN 'SOURCE_LAG_OR_BACKFILL'
 WHEN m.unmapped_dimension_rows>0 THEN 'DIMENSION_MAPPING_MISSING'
 WHEN m.wrong_unit_rows>0 THEN 'UNIT_MISMATCH'
 WHEN m.missing_conversion_rows>0 THEN 'CONVERSION_MISSING'
 WHEN m.missing_box_rows>0 THEN 'BOX_NUMBER_MISSING'
 WHEN m.target_i=0 THEN 'ZERO_TARGET'
 ELSE 'READY' END AS progress_status
 FROM v_plan_match m
)
SELECT *, target_i/1000000.0 AS monthly_target,
 CASE WHEN progress_status IN ('READY','ZERO_TARGET') THEN observed_actual_i/1000000.0 END AS actual_to_date,
 CASE WHEN progress_status='READY' THEN ROUND(100.0*observed_actual_i/target_i,4) END AS progress_pct,
 CASE WHEN progress_status IN ('READY','ZERO_TARGET') THEN (target_i-observed_actual_i)/1000000.0 END AS remaining_to_month_target,
 'FULL_MONTH_TARGET_NO_DAILY_ALLOCATION' AS target_basis
FROM status_calc;
CREATE VIEW v_source_health AS
SELECT 'splunk' AS source_type,source_id,domain AS kind,enabled,watermark,coverage_from,last_success,last_error,
 last_read AS rows_read,last_written AS rows_written FROM source_state
UNION ALL
SELECT 'oracle',source_id,kind,1,NULL,NULL,loaded_at,
 CASE WHEN projection_ready=0 THEN projection_note END,row_count,NULL FROM reference_state;

-- Compatibility aggregate views: local diagnostics. Dashboard USD uses reporting.py / KZWI3.
CREATE VIEW v_shipment_customer_monthly AS
SELECT source_id,substr(business_date,1,6) period_ym,customer_key,customer_name,customer_group,
 COUNT(*) latest_rows,COUNT(DISTINCT NULLIF(box_no,'')) box_count,
 SUM(qty_i) qty_i,SUM(qty_i)/1000000.0 quantity
FROM v_shipment_detail GROUP BY source_id,substr(business_date,1,6),customer_key,customer_name,customer_group;
CREATE VIEW v_shipment_group_monthly AS
SELECT source_id,substr(business_date,1,6) period_ym,product_group,display_unit,
 COUNT(*) latest_rows,COUNT(DISTINCT NULLIF(box_no,'')) box_count,
 SUM(qty_i) qty_i,SUM(qty_i)/1000000.0 quantity
FROM v_shipment_detail GROUP BY source_id,substr(business_date,1,6),product_group,display_unit;
-- Preserve individual plan versions/scopes. No hidden daily proration or version sum.
CREATE VIEW v_shipment_plan_progress AS SELECT * FROM v_monthly_progress WHERE direction='shipment';
CREATE VIEW v_inbound_plan_progress AS SELECT * FROM v_monthly_progress WHERE direction='inbound';
