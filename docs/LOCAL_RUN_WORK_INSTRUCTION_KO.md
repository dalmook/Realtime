# 로컬 실행 작업지시서 · 1.2.4-realtime

목적: 회사 PC에서 새 ZIP을 안전하게 실행하고, 실제 데이터의 MATNR 환산을 검증한 뒤 대시보드를 시작한다.

## 0. 절대 하지 말 것

- 기존 운영 SQLite를 삭제하지 않는다.
- 오류가 난다고 `reset-source`를 먼저 실행하지 않는다.
- 실제 `.env`, DB, 로그를 GitHub에 올리지 않는다.
- 기존 코드 폴더 위에 새 ZIP을 덮어쓰지 않는다.

## 1. 기존 데이터 확인

탐색기 주소창에 아래를 입력한다.

```text
%LOCALAPPDATA%\SCMRealtimeDB
```

`live\scm_live.sqlite`가 있으면 운영 데이터는 코드 폴더와 별도로 살아 있는 것이다.
가능하면 이 파일을 다른 로컬 폴더에 한 번 복사해 보관한다.

## 2. ZIP 해제

새 ZIP을 기존 폴더와 다른 새 폴더에 푼다.

예:

```text
C:\SCMRealtimeDB_1.2.3
```

## 3. SETUP

`SETUP.cmd` 실행.

이 단계는 Python 선택, `.env` 생성, DB 스키마 준비만 한다.
기존 DB가 예전 `P_CODE` 자재키를 사용하고 있으면 원문 JSON의 `MATNR`로 자동 이관을 시도한다.

### P_CODE → MATNR 이관 조건

모든 기존 입고행 원문에 MATNR가 있어야 한다.
하나라도 없으면 안전을 위해 중단한다. 중단 메시지가 보이면 DB를 삭제하지 말고 그 화면을 보존한다.

## 4. .env 입력

프로젝트 폴더의 `.env`에 승인된 연결정보를 넣는다.

필수 확인:

```text
SPLUNK_HOST
SPLUNK_PORT
SPLUNK_USER
SPLUNK_PASSWORD
ORACLE_ENABLED=true
ORACLE_USER
ORACLE_PASSWORD
ORACLE_DSN
ORACLE_CLIENT_LIB_DIR=C:\instantclient
```

비밀번호/주소는 문서나 GitHub에 복사하지 않는다.

## 5. 연결 준비 검사

`CHECK.cmd` 실행.

확인할 것:

- Python 3.11+
- SQLite quick_check OK
- Oracle Thick initialized
- Instant Client 경로 정상

## 6. Oracle 환산마스터 재동기화 — 이번 버전 최초 1회 필수

`SYNC_ORACLE.cmd` 실행.

이번 버전은 옛 EQQTY 환산 결과를 사용하지 않는다.
Oracle에서 아래 기준으로 다시 읽는다.

```text
SCM_INFO.SCM_FABIN_CONV_FAM6_MST_M
ITEM        ← Splunk MATNR와 연결
CONV_CODE   ← 구성 분리
CONVEQQTY   ← 환산계수
환산수량    = QTY × CONVEQQTY
```

분류:

```text
K4* / PD* → DRAM
K9*       → FLASH
그 외     → OTHER
```

한 ITEM에 DRAM/FLASH가 같이 있으면 두 구성 모두 보존한다.
단, EA/QTY·BOX·USD 원본 fact를 구성행 수만큼 복제하지 않는다.

## 7. 실제 MATNR 환산 확인

`VERIFY_CONVERSION.cmd` 실행.

실제 복합제품 MATNR 하나를 입력한다.
다음이 업무 기준과 일치하는지 확인한다.

- Oracle ITEM
- 각 CONV_CODE
- DRAM / FLASH 분류
- 각 CONVEQQTY
- 최근 입고 QTY
- 최근 출하 QTY
- 계산된 DRAM EQ / FLASH EQ / 전체 EQ

예:

```text
QTY 100
DRAM CONVEQQTY 2
FLASH CONVEQQTY 3

DRAM EQ  200
FLASH EQ 300
TOTAL EQ 500
원본 QTY 100 그대로
BOX / USD 그대로
```

## 8. 실행

`START.cmd` 실행.

기본 주소:

```text
http://127.0.0.1:8765/
```

화면에서 EA → EQ_DRAM → EQ_FLASH를 바꾸어 같은 MATNR의 값이 기대치와 맞는지 확인한다.

## 9. 첫 검증 체크리스트

- [ ] 입고 MATNR가 Oracle ITEM과 맞는다.
- [ ] 복합제품의 DRAM/FLASH가 둘 다 잡힌다.
- [ ] CONVEQQTY 곱셈 결과가 맞다.
- [ ] 환산 전후 EA/QTY가 증가하지 않는다.
- [ ] 환산 때문에 BOX가 두 배가 되지 않는다.
- [ ] 환산 때문에 USD가 두 배가 되지 않는다.
- [ ] 입고와 출하가 같은 환산 기준을 사용한다.
- [ ] STATUS.cmd에서 conversion이 READY다.
- [ ] 실제 SAP/운영 기준 숫자와 샘플 몇 건을 수기 대조했다.

오류가 있으면 해당 MATNR, 원본 QTY, CONV_CODE, CONVEQQTY, 화면 결과만 정리한다. 비밀번호나 전체 원천 데이터는 공유하지 않는다.
