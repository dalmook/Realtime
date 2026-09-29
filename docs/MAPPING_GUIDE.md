# 원천별 매핑 가이드

## 목적

입고/재고/출하의 원천 테이블 구조가 달라도 수집 코드를 복사해서 수정하지 않습니다. `config/pipeline.json`에서 **각 원천의 실제 필드**를 표준 컬럼으로 연결합니다. 미확인 컬럼명은 채워 놓지 않았습니다.

## 1. Oracle 5개 테이블 구조부터 가져오기

`DISCOVER_ORACLE.cmd`는 데이터 행 대신 실제 컬럼명/형식/정밀도를 저장합니다. 결과 위치는 실행창에 표시됩니다. `SYNC_ORACLE.cmd` 또는 09시 예약 수집이 성공하면 원본 테이블과 `exports\oracle_schema.json`도 생성됩니다.

기본 SQL은 다음과 같습니다. 사내 테이블을 변경하지 않고 읽기만 수행합니다.

```sql
SELECT * FROM SCM_INFO.SCM_FABIN_CONV_FAM6_MST_M
SELECT * FROM MST_PAX_ITEM
SELECT * FROM GUI_SITEORGHRCY
SELECT * FROM TAR_D_PLAN_SELL_ESCM
SELECT * FROM MST_MOPLAN
```

이것은 **각각 따로 실행하는 5개 쿼리**이며 위 내용을 하나의 SQL 파일에 연속으로 넣는 형식이 아닙니다. 너무 큰 목표 이력/LOB가 있으면 `query_file`에 승인된 SELECT 파일을 지정하여 필요한 월·버전·컬럼만 가져올 수 있습니다. 결과 전체를 읽고 한도 초과 시 자르지 않고 실패 처리합니다.

## 2. 제품정보: 이미 설정됨

```json
"fields": {
  "material": "ITEM",
  "product_name": "PRODUCT",
  "product_group": "PRODUCTGROUP"
}
```

`MST_PAX_ITEM`은 확인된 컬럼을 사용합니다. 정규화는 material만으로 제품 라벨을 조인하므로 PC→EA 화면 표시와 충돌하지 않습니다. 동일 ITEM의 서로 다른 제품명/그룹이 나오면 필터 또는 승인 우선순위를 정해야 합니다. SQL MAX로 임의 병합하지 않습니다.

## 3. 환산·거래선·목표 연결

수집기를 중지하고 `MANAGE.cmd` → `9 기준정보 매핑`에서 source id를 선택합니다.

```text
conversion
customer
inbound_plan
shipment_plan
```

실제 컬럼 목록에서 번호 또는 이름을 선택합니다. 고정값은 `=PC`, `=BASE`처럼 입력합니다. 필수 매핑이 없으면 저장하지 않습니다. 현재 값이 표시되는 항목에서 Enter는 기존 값 유지이며, 제거/복합식은 JSON에서 명시적으로 바꾸세요.

목표의 기준월이 연·월로 나누어졌다면 JSON의 필드 표현을 사용할 수 있습니다.

```json
"period_ym": {"year_field": "확인된_연도컬럼", "month_field": "확인된_월컬럼"}
```

이는 문법 예시이지 실제 회사 컬럼명 제안이 아닙니다.

### 환산 시 확인

- 원천키가 MATNR/ITEM과 동일한 자재인지, FAM6 등 상위 분류인지
- 계수가 EA당 EQ인지, 다른 배율인지
- 적용월이 존재하는지, 월 이력 중 어떤 값을 쓸지
- 동일 자재·월·단위에 다중행이 남지 않는지

정확한 변환이 필요하면 `query_file`의 승인 SELECT에서 자재 수준으로 변환하세요. `factor_multiplier`가 기본 1이라고 실제 계수의 의미를 확인했다는 뜻이 아닙니다.

### 거래선 시 확인

- GUI_SITEORGHRCY의 어느 컬럼이 실제 거래선 식별자인지
- Splunk 각 원천의 어느 필드와 연결되는지
- 조직 계층별 반복행이 있는지

현재 입고 ACCOUNT 값의 의미는 확인되지 않았으므로 자동 조인하지 않습니다. 거래선 목표를 연결하려면 실적 `fields.customer_key`도 확정해야 합니다.

### 목표 시 확인

- 월 컬럼/계획 버전
- EA/BOX/EQ 수량 컬럼과 배율
- 월+제품인지, 월+제품군+거래선인지 등 행 단위
- P1M1·CO/GO 실적과 같은 범위의 목표인지
- 예산·수정계획·기초계획 중 어느 버전을 비교할지

목표가 여러 수량 컬럼을 가지고 있으면 `mapping.metrics`에 지표별로 추가합니다. 같은 그레인의 중복은 기본 거절합니다. 실제 다른 계획 상세행을 합해야 한다면 **행 고유키를 확인한 후** `row_key_fields`와 `aggregation="sum"`을 지정합니다. 정확히 같은 원본행의 반복까지 두 번 더하지 않도록 키 중복 검사가 들어 있습니다.

매핑 저장 후 `APPLY_MAPPINGS.cmd`로 **로컬 원본만** 재정규화합니다. 이때 Oracle은 재조회하지 않습니다. `STATUS.cmd`의 `MAPPING_REQUIRED`/`MAPPING_ERROR`가 `READY`로 바뀌는지 확인합니다.

## 4. 재고·출하 등록

`MANAGE.cmd` → `8 Splunk 테이블 목록`으로 사용 가능한 TREAD_DYN 테이블 이름을 확인한 뒤 `10 재고/출하 매핑`을 실행합니다.

도우미는 선택한 테이블의 최근 표본에서 필드 목록을 읽습니다. 입고의 필드명을 재고나 출하에 복사하지 않습니다. 고유키·업무일시·수정일시·수량/단위·BOX/자재·저장위치를 지정합니다.

삭제/취소 플래그는 의미가 확인된 경우만 지정합니다. 원천이 행을 물리 삭제하면서 삭제 이벤트를 보내지 않으면 UPSERT만으로 잔존 행을 알아낼 수 없습니다. 이때는 원천의 삭제 이벤트 또는 완전한 전체 스냅샷 계약이 필요합니다.

현재 자동 수집은 TREAD_DYN형 **JSON 최신행 UPSERT** 계약입니다. 전체 스냅샷 엔진은 있지만, 미확인 원천의 표본을 전체 재고로 간주해서 자동 교체하지 않습니다.

확인된 전체 재고 스냅샷을 수동 반영할 경우:

```bat
python run.py import-snapshot --source inventory_dep --file approved_complete_snapshot.jsonl --as-of "2026-09-23T09:00:00+09:00" --token "APPROVED_BATCH_001" --complete --confirm
```

실행 전 자동 백업합니다. JSONL 각 행은 Splunk 결과 envelope(`_raw`, `event_epoch`, `indexed_epoch`)입니다. 빈 스냅샷은 기본 거절합니다. `complete`는 데이터 누락 여부를 프로그램이 외부에서 보장했다는 뜻이 아니며 원천 계약/건수 대조가 선행되어야 합니다.

## 5. 여러 Splunk 서버/원천

기존 항목을 새 id로 복사하고 `connection`을 다르게 지정합니다. 다른 서버 프로필은 `.env`에 `SPLUNK_<PROFILE>_HOST/PORT/USER/PASSWORD/VERIFY_SSL/CA_BUNDLE/PROXY/TIMEOUT`을 넣습니다. 빠진 항목은 기본 `SPLUNK_*` 값을 사용합니다. `record_key`가 같아도 source_id가 다르면 별도 최신행으로 보존합니다.

단, 같은 업무 데이터를 두 개 원천에서 동시에 수집하면 원수량은 중복될 수 있습니다. 월 목표 `actual_sources`에는 겹치지 않는 원천만 연결하세요. BOX의 고유성 범위가 시스템마다 다르면 CHARG 숫자만으로 타 시스템 BOX를 합치지 않도록 별도 규칙을 확정해야 합니다.

## 6. 이미 적재한 원천 매핑 변경

키/필드/범위/테이블 변경은 기존 캐시와 의미가 달라지므로 지문 검사가 차단합니다. 수집을 중지하고 **새 source id로 등록**하거나, 필요한 이력을 백업한 후 명시적으로 해당 원천만 리셋합니다.

```bat
python run.py reset-source inbound_dep --confirm
```

전체 DB를 지우지 않습니다. 해당 원천 원본/최신행/커서만 초기화하고 자동 백업합니다. 다시 켜면 초기 구간부터 재수집합니다. 조회 주기/중첩/건수 상한의 변경은 리셋 없이 가능합니다.
