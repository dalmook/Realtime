-- SCM_INFO.SCM_FABIN_CONV_FAM6_MST_M conversion components
-- Splunk MATNR = Oracle ITEM
-- Each CONV_CODE remains independent; converted quantity = source QTY * CONVEQQTY.
-- Facts must never join these component rows directly for EA/QTY/BOX/USD aggregation.
SELECT
  ITEM,
  CONV_CODE,
  SUM(CONVEQQTY) AS CONVEQQTY,
  'Y' AS USE_FLAG
FROM SCM_INFO.SCM_FABIN_CONV_FAM6_MST_M
WHERE USE_FLAG='Y'
  AND ITEM IS NOT NULL
  AND CONV_CODE IS NOT NULL
  AND CONVEQQTY > 0
GROUP BY ITEM, CONV_CODE
