# Realtime · SCM LIVE Control Dashboard

생산(입고) / 출하 / 재고 / 수기 목표 / 집중관리 아이템을 제공하는 로컬 대시보드입니다.
전달받은 SCMRealtimeDB 구조와 Splunk/Oracle 설정을 기반으로 실행 경로와 API를 정리했습니다.
**회사 실데이터 연결 및 SAP 숫자 대조가 완료된 운영 인증본은 아닙니다.**

## 가장 먼저 화면 확인

`site/index.html`을 브라우저에서 열면 서버 없이 합성 데이터 데모가 열립니다.
다섯 화면, 지표/단위 전환, 차트, CSV, 수기 목표, 집중관리를 조작할 수 있습니다.
정적 데모는 CSP `connect-src 'none'`으로 네트워크 통신을 차단합니다.
목표/집중관리는 브라우저 저장소가 허용된 경우 그 브라우저에만 저장되고 타인과 공유되지 않습니다.

실제 Python API와 SQLite까지 확인하려면 **DEMO.cmd**를 실행하세요.
Python 3.11 이상만 필요합니다. Splunk·Oracle·`.env`를 사용하지 않으며 별도 합성 DB를 만듭니다.

```text
DEMO.cmd
# 또는
python run.py demo
```

기본 주소는 `http://127.0.0.1:8765/`입니다. 포트 변경은 `python run.py demo --port 8877`입니다.
이미 같은 포트로 실행 중이면 기존 창을 종료하거나 다른 포트를 선택하세요.

## 회사에서 실행

1. ZIP을 **새 폴더**에 압축 해제합니다. 기존 코드/DB를 덮어쓰지 않는 방식이 안전합니다.
2. `SETUP.cmd`를 실행합니다. Python 선택, `.env` 준비, 로컬 DB 스키마 준비만 수행합니다.
3. 생성된 `.env`에 회사 승인 Splunk/Oracle 연결 정보를 입력합니다.
4. `CHECK.cmd`로 Python·SQLite·Oracle Thick 준비 상태를 확인합니다.
5. **이번 MATNR/환산 변경판을 처음 적용할 때는 `SYNC_ORACLE.cmd`를 1회 실행**하여 `ITEM / CONV_CODE / CONVEQQTY` 기준정보를 다시 적재합니다.
6. `VERIFY_CONVERSION.cmd`에서 실제 MATNR 하나를 넣어 DRAM/FLASH 환산계수를 확인합니다.
7. `START.cmd`를 실행합니다. API와 수집기가 함께 실행되고 브라우저가 열립니다.

상세 체크리스트는 [로컬 실행 작업지시서](docs/LOCAL_RUN_WORK_INSTRUCTION_KO.md)를 따르세요.

기존 Python을 지정하려면 실행 전 `PYTHON_EXE`에 전체 python.exe 경로를 설정하거나 `SELECT_PYTHON.cmd`를 사용합니다.
Oracle을 쓰려면 선택한 Python에 `oracledb` 또는 `cx_Oracle` 드라이버와 호환 Instant Client가 **미리 설치**되어 있어야 합니다.
`ORACLE_CLIENT_LIB_DIR=C:\instantclient`가 기본이며, Thin 모드로 임의 전환하지 않습니다.
자동 pip 설치, 외부 PyPI 다운로드, 사내 보안정책 변경은 수행하지 않습니다.
승인된 wheel이 필요하면 `offline_wheels`에 준비한 후 `INSTALL_ORACLE_OFFLINE.cmd`를 별도로 실행합니다.

### 주요 .env 항목

| 항목 | 용도 |
|---|---|
| `DATA_DIR` | 로컬 DB 보관 폴더. 비우면 사용자 로컬 앱 데이터의 SCMRealtimeDB/live |
| `DASH_PORT` | 기본 8765 |
| `SPLUNK_HOST` | 호스트 또는 `https://호스트:포트` 둘 다 허용 |
| `SPLUNK_USER`, `SPLUNK_PASSWORD` | Splunk sessionKey 로그인 정보 |
| `ORACLE_ENABLED` | Oracle 수집 활성화 여부 |
| `ORACLE_USER`, `ORACLE_PASSWORD`, `ORACLE_DSN` | 회사 Oracle 접속 정보 |
| `ORACLE_CLIENT_LIB_DIR` | Thick용 Instant Client 폴더 |
| `SHIPMENT_BOX_CONFIRMED` | CARTON이 합산 가능한 BOX 수량임을 회사에서 검증한 뒤 true |

`.env` 예제에는 실제 주소/사용자/비밀번호가 없습니다. `$`나 역슬래시를 치환하지 않고 그대로 읽습니다.
기존 회사 `.env`에 새로운 항목이 없으면 기본값을 사용합니다.
서버는 이 릴리스에서 루프백으로만 열립니다. 사내 여러 직원에게 공개하려면 별도의 승인된 인증·접근제어가 필요합니다.

## 데이터 분리와 업데이트

- 실제 DB 기본 위치: Windows `%LOCALAPPDATA%\SCMRealtimeDB\live\scm_live.sqlite`
- 합성 API 데모 DB: `%LOCALAPPDATA%\SCMRealtimeDB\demo-web\scm_live.sqlite`
- 실행 코드 폴더와 DB 폴더가 분리되어 ZIP 교체만으로 DB가 삭제되지 않습니다.
- `DATA_DIR`은 네트워크 공유 드라이브가 아닌 로컬 디스크로 지정합니다.
- 업데이트 전 수집기를 종료하고 `BACKUP.cmd`로 SQLite 일관성 백업을 수행합니다.
- 새 ZIP을 **새 폴더**에 해제하고 `.env`와 필요한 로컬 설정만 복사합니다.
- 이번 버전은 입고 자재 연결키를 `P_CODE → MATNR`로 바꿉니다. 기존 DB의 원문 JSON에 MATNR가 모두 있으면 최초 초기화 때 자동 이관하며, 이관 전 DB 백업을 만듭니다.
- 기존 행 중 MATNR가 하나라도 없으면 자동 이관을 중단합니다. **DB 삭제/reset-source로 우회하지 말고** 오류 내용을 보존한 뒤 backfill 방법을 결정하세요.
- 이전 `EQQTY/unit` 환산 결과는 신뢰하지 않고 무효화합니다. 새 코드 최초 적용 후 `SYNC_ORACLE.cmd`로 Oracle conversion을 다시 읽어야 합니다.
- 공급되는 새 `config/pipeline.json`과 회사에서 수정한 로컬 매핑은 비교 후 반영합니다. 다른 키·매핑 변경은 계속 지문 검사로 차단합니다.

## 프로젝트 구조

```text
SCMRealtimeDB/
├── run.py / launcher.py           통합 실행
├── *.cmd                         Windows 실행 / 검사 / 백업 / 테스트
├── .env.example                  연결 설정 예제 (비밀값 없음)
├── config/pipeline.json           전달받은 원천 매핑
├── config/queries/                Oracle 읽기 SQL
├── scm_db/                       기존 수집·정규화·원본 보존 엔진
├── dashboard/
│   ├── server.py                 HTTP 라우팅 / 정적 파일 / 로컬 쓰기
│   ├── runtime.py                공통 DB 경로 / 추가 스키마
│   ├── reporting.py              공통 수치 / 날짜 / 필터 / 목표 적용
│   ├── target_manager.py         수기 목표 CRUD
│   ├── focus_manager.py          집중관리 CRUD
│   └── static/                   기존 화면 디자인 + 데모/관리 UI
├── sql/                          DB 스키마와 호환 조회 뷰
├── tests/                        외부 연결 없는 144개 테스트
├── tools/build_site.py           합성 단일 HTML 생성
├── tools/build_package.py        허용 목록 기반 ZIP 생성
├── tools/publish_github.py       Realtime 저장소 / 다운로드 안내
├── site/index.html               서버 없는 완성 데모
└── docs/                         운영 안내 / 변경사항 / 실제 검증 결과
```

## 이번 복원에서 바꾼 실행 경로

기존 코드의 경로와 API 이름은 유지하되 실행을 막는 부분을 수정했습니다.
전달된 `server.py`, `target_manager.py`, `focus_manager.py`, KZWI3 개별 수집기는 비교할 수 있도록
`docs/restoration/*.txt`에 비실행 텍스트로 보관했습니다. 일부 문서·테스트·관리 UI·호환 뷰는 실행판에 맞춰 재작성했습니다.
**원본 81파일의 바이트 단위 동일 복제본이라는 뜻은 아닙니다.** 상세 내용은 `docs/RESTORATION.md`를 확인하세요.

주요 수정은 하드코딩된 H:/사용자 경로 제거, 단일 설정 공유, API/수집기 통합 실행,
없는 `c_id/i_type` 컬럼 대신 원본 JSON 조회, 연속 수집 KZWI3 우선 연결,
수기 목표 UI/API 필드 통일, 동일 범위에만 수기 목표 우선 적용,
조회 오류를 0으로 숨기지 않기, EQ의 일대다 JOIN으로 EA가 늘어나는 문제 차단입니다.

## 환산 규칙

현재 확정한 공통 환산 규칙은 다음과 같습니다.

- 실적 ITEM 연결키: **Splunk `MATNR` ↔ Oracle `SCM_INFO.SCM_FABIN_CONV_FAM6_MST_M.ITEM`**
- 구성 분리키: `CONV_CODE`
- 환산계수: `CONVEQQTY`
- 환산식: **원본 QTY × CONVEQQTY**
- `CONV_CODE K4*`, `PD*` → DRAM
- `CONV_CODE K9*` → FLASH
- 그 외 → OTHER

한 ITEM에 DRAM과 FLASH 구성행이 같이 있어도 환산 구성만 여러 행으로 보존합니다. EA/QTY·BOX·USD 원본 fact는 한 번만 집계합니다.
예를 들어 QTY=100, DRAM CONVEQQTY=2, FLASH CONVEQQTY=3이면 DRAM EQ=200, FLASH EQ=300이며 QTY=100/BOX/USD는 그대로입니다.
이 로직은 `fact_valuation`에서 독립적으로 수행하여 입고·출하·재고가 같은 환산마스터를 사용합니다.

로컬 확인은 `VERIFY_CONVERSION.cmd`를 실행해 실제 MATNR 하나를 입력하세요.

## 수치 계약

원수량·금액의 정수 저장 배율은 1,000,000이고 API는 원단위를 반환합니다.
표시의 K/M/억/B는 화면 배율입니다. DRAM EQ와 FLASH EQ는 분리합니다.
월 목표는 월 전체 목표로 비교하고 임의로 일할 배분하지 않습니다.
일자 지정 시 해당일 이후 실적을 월 누적에 넣지 않습니다.
집중관리의 날짜와 지표는 메인 화면을 따르며, 등록 범위 자체는 상단 추가 필터와 별도로 유지됩니다.
같은 범위의 겹치는 수기 목표는 우선순위 1건만 적용합니다. `additive` 값은 호환 보존되지만 임의 합산하지 않습니다.

출하 USD는 연속 수집 `shipment_amount_current`의 KZWI3가 우선이고, 해당 업무키가 없을 때만
전달받은 기존 `shipment_amount_kzwi3`의 KZWI3 스냅샷을 참조합니다. DO/자재 일치도 확인합니다.
**NETWR로 누락 금액을 메우지 않습니다.** 미매칭이 있으면 완전한 합계와 달성률을 보류합니다.
BOX의 ITEM/거래선 배분이 없으면 해당 조합을 미제공으로 표시합니다.

재고는 현재 스냅샷으로만 표시하며 목표가 없습니다. 가용재고, 과거 재고, 회전일수는 만들어내지 않습니다.
API 성공이 Splunk 수집 완료 또는 SAP 정합성 확인을 뜻하지 않습니다.

## GitHub에서 다운로드 / 업데이트

이 프로젝트의 저장소는 **[dalmook/Realtime](https://github.com/dalmook/Realtime)** 입니다.

- **[최신 실행 ZIP](https://github.com/dalmook/Realtime/releases/latest/download/SCMRealtimeDB_portable.zip)**: 테스트를 거쳐 Release에 첨부되는 휴대용 실행 패키지.
- **[소스 ZIP](https://github.com/dalmook/Realtime/archive/refs/heads/main.zip)**: 현재 main 브랜치 전체 소스.
- **[데모 HTML 원본](site/index.html)**: 다운로드 후 브라우저에서 직접 실행 가능.
- **[Actions](https://github.com/dalmook/Realtime/actions)**: 운영 DB나 회사 서비스에 연결하지 않는 테스트/패키징 이력.

`site/`는 합성 데이터만 담은 공개 정적 화면입니다. 회사 API를 GitHub Pages에서 호출하지 않습니다.
공개 저장소에 실제 `.env`, 업무 DB, 조회 결과, 로그를 커밋하지 마세요.
원천 테이블명과 마스킹된 코드/SQL도 공개되므로 회사의 소스 공개 정책은 별도로 준수해야 합니다.

회사에서는 Git이나 GitHub CLI 없이 ZIP을 받아 실행하면 됩니다. 코드 수정 후에는 이 저장소의 main 브랜치에서 관리하고,
회사 환경의 비밀값과 로컬 매핑은 외부에 올리지 않습니다. 업데이트 절차는 [회사 실행 가이드](docs/QUICK_START_KO.md)를 확인하세요.

`PUBLISH_GITHUB.cmd`는 더 이상 별도 저장소를 생성하지 않습니다. 저장소와 Release 안내를 표시하는 안전한 안내 명령입니다.

## 로컬 검증 / 패키지 다시 만들기

```text
SELFTEST.cmd
SYNC_ORACLE.cmd
VERIFY_CONVERSION.cmd
python -S -m unittest discover -s tests -v
python tools/build_site.py
python tools/build_package.py
python tools/publish_github.py
```

실제 실행 결과와 미검증 범위: `docs/TEST_REPORT.md`.
