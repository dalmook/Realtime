# Realtime 저장소 반영

대상: `dalmook/Realtime` (public). 기반: 이전 대화에서 생성된 `SCMRealtimeDB_portable_1.2.0.zip`.
변경: 저장소/ZIP 링크, 회사 실행 가이드, 버전 표기, 별도 저장소를 만들던 최초 게시 도구를 안내용으로 변경.
기존 수집/API/화면 코드는 유지합니다. 원본 비교 자료는 `docs/restoration/`에 있습니다.

2026-09-29 로컬 재검증: `python -S -m unittest discover -s tests -v` — 132개 통과.
실제 Windows 실행 및 회사 Splunk/Oracle/SAP 대조 성공을 의미하지 않습니다.
원격 Actions의 최종 결과는 저장소 Actions 화면에서 확인합니다.

업로드는 파일별 SHA-256 및 아카이브 SHA-256을 확인한 후 복원하도록 구성했습니다.
실제 `.env`/DB/로그/Oracle 바이너리는 포함하지 않습니다. 마스킹된 원본 코드와 업무 테이블 이름은 포함됩니다.
