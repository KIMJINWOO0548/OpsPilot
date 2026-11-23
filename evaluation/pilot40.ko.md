# 합성 40건 비교 실험

열 개의 독립적인 IT 정책 문서군으로 전개한 개발 24건과 홀드아웃 16건이다. 유효 기간 시작·종료 경계, 관측된 소급 정정 이전·이후, 상충하는 동급 SOP, 다른 팀과 테넌트, 역할 제한과 정상 사례를 포함한다. 문서군과 원문 해시는 분할 사이에 중복되지 않는다. 사례 입력, 기대 판정과 기대 출처는 `pilot40.json`에 고정한다.

## 실행

격리된 시험 환경에서 공식 GGUF 파일을 사용한 llama.cpp CPU 서버 두 개를 루프백에 띄운다. 실행기에 전달할 런타임 폴더에 원본 ZIP과 GGUF 두 파일을 두면 결과에 해시가 남는다. 결과 폴더와 런타임 경로를 환경에 맞게 지정한다. [모델과 런타임 선택 기록](../docs/decisions/ADR-006-LOCAL-HYBRID-DRAFTS.md)

```powershell
$evalRoot = Join-Path $PWD '.local/pilot40'
$evalRuntime = Join-Path $evalRoot 'runtime'
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:OPSPILOT_DB = Join-Path $evalRoot 'bootstrap.sqlite3'
python -m scripts.eval_pilot40 --output $evalRoot --runtime $evalRuntime --embedding-port 17582 --chat-port 7417
python -m pytest -q tests/test_eval_pilot40.py
```

스크립트는 사례마다 새 임시 SQLite에 합성 문서를 적재하고 작성자 계정으로 로그인한다. 기존 정책 분석과 Hybrid RAG는 서버가 인증한 동일 사용자로 요청한다. 단순 RAG는 같은 합성 사례의 자료에서 단어 겹침만 사용하고 오프라인 비교 코드에서만 호출된다. 두 생성 호출은 동일한 로컬 모델과 프롬프트, 응답 제약 및 상위 4개 한도를 사용한다.

## 결과 읽기

- `pilot40-results.json`에는 40개 사례의 기대 판정과 실제 결과, 권한·시간 경계에 걸린 근거, 입력과 소스 파일 해시, 구간별 비교 지표를 저장한다.
- `pilot40-results.ko.md`에는 개발·홀드아웃·전체의 실측 분자와 분모를 표시한다. 실행 중 보호 경계를 위반하거나 모델 연결에 실패하면 파일에 해당 사례를 기록하고 종료 코드는 1이다.
- 지연은 로컬 모델이 이미 실행 중일 때 측정한다. 단순 RAG는 검색과 생성 호출이고, Hybrid RAG에는 인증된 분석 API의 권한 확인·DB 조회·검색·생성·검증이 포함된다. 지표에 모델 초기 기동 시간은 포함되지 않는다.
- 원문 ID와 인용을 확인할 수 있는 합성 정책 파일럿이다. 별도 도메인의 검색 순위 개선, 일반화 성능과 공식 평가 게이트는 이 실행에서 판정하지 않는다.
