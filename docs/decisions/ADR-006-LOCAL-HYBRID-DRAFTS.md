# ADR-006 · 로컬 Hybrid RAG와 모델 초안

상태: 채택 (2026-11-23), 포트폴리오 검증 범위.

BM25와 로컬 의미 임베딩을 결합한다. SQL로 테넌트·팀·역할·자산·관측 시점을 선필터한 뒤 유효 기간, 주장 유형, 대체 관계를 확인한다. 권한과 시점이 맞는 전체 SOP 집합을 EIE로 검사해 순위 밖의 충돌까지 차단한다. 모델은 그 검사를 통과한 제한된 근거로만 인용 초안을 만든다. 서버에서 인용 원문·버전과 EIE 조치를 확인하며, 기존 승인 엔진이 승인과 실행을 결정한다.

llama.cpp의 Windows CPU 실행본을 작업 폴더에 풀어 짧은 합성 근거로 시험한다. Qwen2.5-0.5B-Instruct와 Qwen3-Embedding-0.6B의 공식 Apache-2.0 GGUF를 SHA-256으로 확인한다. 서버는 루프백에서만 연결하고 API 결제와 실제 문서 전송은 없다. SQLite와 Python을 재사용한다. 이번 합성 규모의 BM25와 벡터 계산에 별도 검색 서버나 DB 마이그레이션은 필요하지 않다. [llama.cpp 빌드 b12649](https://github.com/ggml-org/llama.cpp/releases/tag/b12649) · [생성 모델 리비전](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/tree/9217f5db79a29953eb74d5343926648285ec7e67) · [임베딩 모델 리비전](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF/tree/370f27d7550e0def9b39c1f16d3fbaa13aa67728)

인증된 `POST /api/v1/analysis/hybrid`에서만 모델을 사용한다. 호출 직전에 근거 검색 범위를 확인하고 반환 전에도 현재 세션과 후보를 비교한다. 모델 종료나 잘못된 인용에는 검증된 AI 초안을 표시하지 않는다. 기본 분석 API는 모델이 꺼진 상태에서도 기존 정책 판정을 돌려준다. 실제 모델을 연결할 때 `OPSPILOT_EMBED_PORT`와 `OPSPILOT_CHAT_PORT`를 함께 설정한다. `scripts/hybrid_smoke.py`로 별도 시험 DB에서 과거 A-103, 현재 A-103, 충돌, 권한 밖 입력을 재현한다.

비교 대안은 단순 RAG와 기존 결정적 EIE다. 40개 합성 예비 사례에 동일 생성 모델을 적용하고 권한 누설·시점 오류·근거 누락·충돌 차단을 분모와 함께 집계한다. 지연, 모델 해시, 프롬프트 및 데이터셋 버전을 남긴다. 이 규모의 결과와 기존 공식 평가 게이트는 별도로 기록한다.

순서는 Hybrid RAG와 실제 LLM, 40개 비교, 승인된 로컬 PDF 생성, Flutter Windows 패키징이다. 완료 증거는 자동 테스트와 90초 합성 시연 데이터다.
