# Portable 운용 안내

최신 시작·업데이트 절차는 루트 README.md를 기준으로 합니다.
기존 DBOnly 안내는 historical/OPERATIONS_20260923.md에 보존했습니다.

프로세스 시작은 START.cmd, 준비 검사는 CHECK.cmd, 연결 없는 데모는 DEMO.cmd입니다.
Oracle Thick 라이브러리가 없으면 CHECK가 준비 오류를 표시합니다. 확인만 하며 자동 설치하지 않습니다.
09:00 KST Oracle 예약과 실패 시 당일 자동 재시도 금지 정책은 기존 engine을 유지합니다.
수동 재조회는 SYNC_ORACLE.cmd이며 원천 로그인/조회 권한은 별도 필요합니다.

.env / 실제 SQLite / raw JSON / 로그 / client DLL은 저장소에 넣지 않습니다.
수집 중 DB 본체만 파일 복사하지 말고 BACKUP.cmd를 사용합니다.
버전 교체 전 프로세스를 종료하세요. 새 ZIP+기존.env, 동일 DATA_DIR이 기본 업데이트 방식입니다.

GitHub Pages는 합성 HTML 체험판이고 회사 실행은 로컬 API입니다. 둘의 데이터를 연결하지 않습니다.
내부 .env나 사내 주소를 브라우저 설정인 config.js에 넣지 마세요.
SQL 집계 계약 변경은 RESTORATION.md의 호환성 항목을 확인하세요.
