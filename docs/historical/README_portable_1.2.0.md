# SCM Realtime LIVE Control Dashboard — Portable 1.2.0

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

1. ZIP을 새 폴더에 압축 해제합니다. 기존 코드/DB를 덮어쓰지 않는 방식이 안전합니다.
2. `SETUP.cmd`를 실행합니다. 이미 있는 `.env`는 보존하며, 없을 때만 예제를 복사합니다.
3. 생성된 `.env`에 회사 승인 연결 정보를 입력하고 `CHECK.cmd`로 준비 상태를 확인합니다.
4. `START.cmd`를 실행합니다. API와 수집기가 함께 실행되고 브라우저가 열립니다.

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
- 새 ZIP을 **새 폴더**에 해제하고 `.env`와 필요한 로컬 설정만 복사합니다. 새 폴더에서 `START.cmd`를 실행합니다.
- 공급되는 새 config/pipeline.json과 회사에서 수정한 로컬 매핑은 비교 후 반영합니다. 키·매핑이 달라지면 지문 검사가 중단합니다. DB 전체 리셋으로 우회하지 마세요.
- 기존 테이블/행을 지우는 자동 마이그레이션은 없습니다. 추가 컬럼 마이그레이션과 실행 전 백업을 사용합니다.

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
├── tests/                        외부 연결 없는 132개 테스트
├── tools/build_site.py           합성 단일 HTML 생성
├── tools/build_package.py        허용 목록 기반 ZIP 생성
├── tools/publish_github.py       사용자 PC의 gh로 최초 게시
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

## GitHub 최초 게시

현재 배포물에는 **원격 저장소 생성/Pages 게시 성공 결과가 포함되어 있지 않습니다.**
이번 작업의 GitHub 연결에서는 저장소 읽기/파일 작업은 가능했지만 신규 저장소 생성 액션이 제공되지 않았고,
연결된 원격 실행기는 계정 연결 오류로 실행되지 않았습니다.

사용자 PC에 Git과 GitHub CLI가 설치되고 `gh auth login`으로 `dalmook` 계정 인증이 완료되어 있을 때:

```text
PUBLISH_GITHUB.cmd
```

이 스크립트는 처음 게시할 때 아래 두 저장소를 **새로** 만듭니다.

- `dalmook/SCMRealtimeDB`: 회사 코드/매핑 보호를 위한 **비공개** 소스 저장소.
- `dalmook/SCMRealtimeDB-demo`: 합성 HTML만 포함하는 **공개** 데모 저장소. GitHub Pages workflow를 설정합니다.

동명 저장소가 이미 있으면 덮어쓰지 않고 중단합니다. `.env`나 DB 파일을 업로드하지 않습니다.
기본 공개 데모에는 회사 원천 테이블명·Oracle SQL·원본 테스트 문서가 포함되지 않습니다.
권한/연결 문제는 사용자 계정과 조직 정책에 따라 별도로 확인해야 합니다. 이 게시 스크립트는 dry-run만 검사했고 실제 GitHub 실행은 하지 못했습니다.

게시된 소스 저장소는 push마다 GitHub Actions로 테스트와 ZIP을 만들도록 준비했습니다.
Actions 실행 여부와 Windows CI 성공은 **실제 게시 후** 확인해야 합니다.
태그 `v...`로 push하면 해당 버전 ZIP을 Release에 첨부합니다.

## 로컬 검증 / 패키지 다시 만들기

```text
SELFTEST.cmd
python -S -m unittest discover -s tests -v
python tools/build_site.py
python tools/build_package.py
python tools/publish_github.py --dry-run
```

실제 실행 결과와 미검증 범위: `docs/TEST_REPORT.md`.
