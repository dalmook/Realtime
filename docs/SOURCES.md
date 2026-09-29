# 구현 참고 자료

확인일: 2026-09-23. 회사 테이블 정의는 사용자가 제공한 이름과 입고 샘플만 확정값으로 사용했습니다. 아래 공개 문서가 회사 커스텀 테이블의 컬럼/고유키/목표 의미를 보증하는 것은 아닙니다.

- Splunk: Creating searches using the REST API
  https://help.splunk.com/en/splunk-enterprise/leverage-rest-apis/rest-api-tutorials/9.4/rest-api-tutorials/creating-searches-using-the-rest-api
  검색 작업·명시적 결과 상한·범위 관리 참고.
- Splunk search endpoints
  https://help.splunk.com/en/splunk-enterprise/rest-api-reference/10.2/search-endpoints/search-endpoint-descriptions
  jobs 및 v2 results 페이지네이션 참고. 실제 서버는 사용자 환경의 10.0.7이며 실접속 검증 필요.
- python-oracledb 3.4.2: Initializing python-oracledb
  https://python-oracledb.readthedocs.io/en/v3.4.2/user_guide/initialization.html
  init_oracle_client와 Thick 모드 참고. 특정 버전 강제 설치를 의미하지 않음.
- SQLite Write-Ahead Logging
  https://www.sqlite.org/wal.html
  네트워크 파일시스템 제한, SQLite 2026 WAL-reset 수정 버전 확인. 알려진 수정 버전에서는 WAL, 그 이전 Python 내장 SQLite에서는 DELETE journal+FULL synchronous를 사용하도록 구현.
- pip configuration
  https://pip.pypa.io/en/stable/topics/configuration/
  선택적인 오프라인 설치에서 PIP_CONFIG_FILE=os.devnull 및 --no-index로 인덱스 접속 금지.

기본 프로그램에는 외부 패키지 소스/바이너리/폰트를 재배포하지 않습니다. Oracle 드라이버와 Instant Client는 사내 승인 설치본을 사용합니다.
