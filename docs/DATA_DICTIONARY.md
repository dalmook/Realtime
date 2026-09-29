# 데이터 사전 · schema_version 1

## 1. 원본과 운영 메타데이터

| 테이블 | 의미/키 |
|---|---|
| raw_splunk_event | source_id + event_hash별 원본 JSON, 수신 시각. 기본 30일 로그 보관 |
| source_state | 원천 id, 설정 지문, 체크포인트, 수집 시작 커버리지, 최근 성공/오류 |
| etl_run | 실행 id, 종류, 시작/완료/상태/읽음/반영/거절/오류 |
| schedule_run | (task, local_day) UNIQUE. 재시작해도 당일 09시 예약 중복 방지 |
| data_issue | 잘못된 키/수량/일시 등 데이터 검토 기록 |
| field_catalog | Splunk에서 발견한 필드/표본형식 목록 |
| reference_state | 원본 복제 시각·행 수·컬럼 구조·정규화 가능 여부 |
| reference_snapshot_log | Oracle 스냅샷 이력/원본 행 수/구조 해시 |
| meta | 버전·환산 revision·bootstrap 진행 상태 |

`raw_splunk_event`와 오류 기록에는 업무 데이터가 들어 있습니다. 토큰/비밀번호를 기록하지 않지만, 이 파일과 DB 자체를 외부에 보내지 마세요.

## 2. Oracle 원본 테이블 (첫 성공 수집 시 생성)

| Oracle | 로컬 테이블 |
|---|---|
| SCM_INFO.SCM_FABIN_CONV_FAM6_MST_M | raw_oracle_conversion |
| MST_PAX_ITEM | raw_oracle_product |
| GUI_SITEORGHRCY | raw_oracle_customer |
| TAR_D_PLAN_SELL_ESCM | raw_oracle_shipment_plan |
| MST_MOPLAN | raw_oracle_inbound_plan |

원본 컬럼 이름을 그대로 사용합니다. 값은 **TEXT**로 보관해 긴 자재번호, 0으로 시작하는 코드, Oracle NUMBER의 소수 정밀도를 손상시키지 않습니다. 원래 데이터 형식/정밀도는 `reference_state.columns_json`과 구조 JSON에 보관합니다. 숫자 계산에는 정규화 테이블을 사용하세요.

예약 컬럼 `__scm_row_no`는 스냅샷 안의 보관 순서일 뿐 업무 고유키가 아닙니다. `__scm_json`은 행 전체 원본입니다. BLOB는 hex: 접두사의 문자열로 저장합니다. 원본 SQL의 반환 컬럼이 바뀌면 원본 복제는 새 구조로 교체하고, 기존 매핑과 맞지 않는 정규화는 오류로 표시합니다.

## 3. 공통 실적 컬럼

`inbound_current`, `inventory_current`, `shipment_current`는 테이블을 분리하되 아래 표준 컬럼을 공통 사용합니다.

| 컬럼 | 의미 |
|---|---|
| source_id + record_key | 복합 PK. record_key는 원천 키 값 배열 JSON |
| document_no / box_no | 문서번호 / 박스번호 |
| material | 기준정보 자재 연결키 |
| qty_i | 원수량 × 1,000,000을 정수로 저장 |
| unit | 원본 단위 PC/EA/KG 등 |
| plant / warehouse / location | 플랜트/창고/저장위치 |
| customer_key | 확인된 거래선키만 저장. 미확정이면 빈 값 |
| business_date / business_time | 업무일 YYYYMMDD / HHMMSS |
| business_us | 업무일시의 UTC epoch microseconds |
| modified_us | 원천 최종 수정일시 |
| generated_us | 수집 생성 UTC 시각. 알려진 CURRENT_TIMESTAMP 형식 |
| indexed_us | Splunk 인덱싱 시각 |
| event_hash | 원본/수집 버전 비교 식별자 |
| scope_ok | 최신 행이 업무 조회 범위 안인지 0/1 |
| deleted | 명시적으로 등록한 취소/삭제 규칙 결과 0/1 |
| payload_json | 최신 원본 전체 |

우선순위는 `(modified_us, generated_us, indexed_us)`입니다. QTY/자재/플래그를 필드별 latest로 섞지 않고 같은 최신 이벤트의 전체 행을 반영합니다. 동일 우선순위인데 내용이 충돌하면 멋대로 고르지 않고 오류를 남깁니다.

현재 입고 business key는 `CHIT + CHARG`. `scope_ok=0`인 행도 저장해야 이전에 집계되던 행이 범위 밖으로 수정될 때 제거할 수 있습니다. 보고서는 반드시 `v_inbound_detail`처럼 유효범위 뷰를 사용하세요.

재고는 **현재 잔량**입니다. 수집 시점마다 잔량을 더하지 않습니다. UPSERT 원천이면 삭제/잔량0도 전달되어야 합니다. 완전한 스냅샷 방식은 별도의 complete 선언으로만 원자 교체하며, 자동 원천에서는 확인 없이 적용하지 않습니다.

## 4. 정규화 기준정보

| 테이블 | PK / 내용 |
|---|---|
| dim_product | material / product_name, product_group |
| dim_customer | customer_key / customer_name, customer_group |
| dim_conversion | period_ym + material + unit / eq_per_unit |
| fact_valuation | source_id + record_key / reference_revision, event_hash, eq_i |

제품명·그룹은 동일 자재키당 한 행만 허용합니다. 값이 동일한 중복은 합칩니다. 충돌하는 중복은 원본을 보존하면서 정규화를 중단합니다. `MAX(PRODUCT), MAX(PRODUCTGROUP)`로 서로 다른 원본 행을 섞지 않습니다.

환산 적용월 `period_ym=''`는 **명시적으로 확인한 상시계수**입니다. `YYYYMM` 행이 있으면 해당 월의 계수가 우선합니다. 원본이 FAM6나 다른 계층의 키를 사용하면, 자재코드와의 관계를 먼저 확인하여 승인 SQL에서 한 자재·월·단위당 한 계수로 만들어야 합니다.

환산은 원수량 × EQ-per-unit. EQ_100M 표시 = EQ ÷ 100,000,000. BOX에는 환산계수를 쓰지 않습니다. 환산 revision이 바뀌면 한 번 재계산하며 화면 조회마다 Oracle을 재실행하지 않습니다.

## 5. 월 목표

`plan_monthly`의 고유 식별은 원천 + 방향 + 월 + 계획버전 + 지표 + 집계차원입니다.

- `direction`: inbound / shipment
- `period_ym`: YYYYMM
- `plan_version`: 승인된 버전. 자동 MAX/버전 합산 없음
- `metric`: EA / BOX / EQ
- `target_i`: 정규화 단위 목표 × 1,000,000
- `material, product_group, customer_key, plant, warehouse`: 특정 값 또는 `*` (목표의 ALL 수준)
- `scope_confirmed`: 목표와 실적의 업무 범위가 같다는 명시적 확인
- `reference_source, snapshot_id`: 출처/적용 스냅샷

`plan_actual_source`에서 목표 원천과 실적 원천을 연결합니다. 집계차원이 없는 목표를 임의로 제품/일자에 복제하지 않습니다. 계획 버전을 합산하지 않습니다. 집계차원이 겹치는 소계/합계 행도 함께 합산하지 마세요.

지표가 동일해도 EA와 천EA, EQ와 억EQ는 다릅니다. 매핑의 multiplier로 정규화합니다. 예: 억EQ 목표라면 metric=EQ, multiplier=100000000. `monthly_target`과 `actual_to_date`는 **canonical metric 단위**입니다. display_unit은 라벨 메타데이터이며 자동 배율 환산을 의미하지 않습니다.

## 6. 소비용 SQL VIEW

| VIEW | 사용 목적 |
|---|---|
| v_inbound_detail / v_shipment_detail | 최신 유효 행 + 제품/거래선 정보 |
| v_inventory_detail | 현재 재고 원장 |
| v_inbound_daily / v_shipment_daily | 일별 실제 수량/고유 BOX. 일 목표 없음 |
| v_inbound_product_monthly / v_shipment_product_monthly | 월·제품별 실적 |
| v_inventory_balance | 제품·창고·저장위치별 현재 잔량 |
| v_monthly_progress | 월 목표·관측 실적·진척률·비교 가능 상태 |
| v_source_health | 최근 수집/정규화 상태 |

`*_i` 정수는 원단위 × 1,000,000입니다. 데이터 규모가 SQLite 정수 합계 한계를 넘으면 오류로 중단하고 더 큰 DB/숫자형으로 이관해야 합니다. 상세 원수량은 소수 6자리까지 허용하며 초과는 조용히 절삭하지 않습니다. EQ 환산 결과만 명시적으로 소수 6자리 half-even 반올림합니다.

## 7. 월 진척 상태

`READY`일 때만 비율을 읽습니다. `ZERO_TARGET`은 실제값을 제공하지만 0 나누기를 하지 않습니다.

`SCOPE_UNCONFIRMED`, `ACTUAL_SOURCE_UNMAPPED`, `ACTUAL_SOURCE_NOT_CONFIGURED`, `SOURCE_ERROR`, `PARTIAL_HISTORY`, `SOURCE_LAG_OR_BACKFILL`, `DIMENSION_MAPPING_MISSING`, `UNIT_MISMATCH`, `CONVERSION_MISSING`, `BOX_NUMBER_MISSING`는 **비율 보류**입니다.

`observed_actual_i`는 현재 관측분을 진단하기 위한 값이며 완전한 실적으로 확정한 값이 아닙니다. 전체 복구·범위·단위 검증 후의 `actual_to_date`를 최종 보고에 사용하세요. `reference_loaded_at`을 같이 표시하여 오래된 목표를 최신 목표로 오인하지 않게 합니다.
