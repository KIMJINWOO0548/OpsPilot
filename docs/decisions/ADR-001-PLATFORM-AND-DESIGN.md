# ADR-001: 현재 Python API를 보강하고 React/TypeScript는 G6에서 도입

- 날짜: 2026-10-19 (Asia/Seoul)
- 상태: 현재 개발 범위 결정. 후속 프레임워크 설치·성능 검증 승인 아님.
- 배경: 사용자는 현재 플랫폼 개발에 맞는 언어와 superpowers, ponytail, codex-auto-model-router, 디자인 플러그인 활용을 요청했다. 저장소 계약은 첫 작업을 G0/G1 보강으로 정하고 사전 검증 없는 라이브러리 추가·UI 재구축을 금지한다.

## 결정과 근거

1. **백엔드·평가 도구는 Python/FastAPI를 유지한다.** 기존 Pydantic 타입, 정책 코드, SQLite 트랜잭션과 테스트를 재사용한다. 이번 Windows 검증 런타임은 Python 3.12.14이며 프로젝트 최소 버전 `>=3.11`은 변경하지 않는다. FastAPI는 표준 Python 타입을 요청 검증에 활용한다([공식 설명](https://fastapi.tiangolo.com/features/), 조회 2026-10-19).
2. **제품 UI는 기존 계획대로 G6의 React/TypeScript 대상으로 둔다.** TypeScript는 실행 전 타입 검사 도구이며, React는 공식 TypeScript 사용 지침을 제공한다([TypeScript](https://www.typescriptlang.org/docs/handbook/typescript-from-scratch), [React](https://react.dev/learn/typescript), 조회 2026-10-19). 이 조합의 적합성은 기존 계획과 API 타입 경계를 근거로 한 프로젝트 판단이며, 유행 순위나 비교 성능의 결론이 아니다. A03 인증·E03 정책 의존성을 해결하기 전 UI를 재구축하지 않는다.
3. **이번 실행은 G1 분할 검사와 발견된 Windows DB 연결 누수를 수정한다.** 새 직접 의존성, LLM 호출, PostgreSQL, LangGraph, 외부 데이터, 실제 쓰기 도구를 추가하지 않는다. 기존 `pyproject.toml`의 개발 의존성만 로컬 `.venv`에 설치했다.

## 대안

| 대안 | 판단 |
|---|---|
| API를 TypeScript로 전면 이전 | 기존 정책·평가 코드와의 경계가 늘어난다. 현재 요구에서 이득을 측정할 근거가 없어 채택하지 않는다. |
| React/TypeScript UI를 즉시 구축 | 현재 G0/G1 누락과 인증 부재를 해결하지 못하고 UI01 의존성을 앞지른다. G6에서 실행한다. |
| 현재 Python 코드와 HTML을 보강 | 기존 계약과 실패 사례에 집중할 수 있어 이번 작업에 채택한다. |

## 플러그인 적용 기록

| 도구/스킬 | 이번 실제 사용과 경계 |
|---|---|
| superpowers | 맥락·범위 검토, 원인 조사, 실패 테스트→최소 수정, 독립 리뷰, 최종 검증. 사용자의 파일별 승인 없는 자율 개발 지시가 스킬의 일반 승인 절차보다 우선한다. |
| ponytail full | 표준 라이브러리와 기존 함수 재사용. 변경은 분할 검사기와 DB 연결 생명주기에 제한한다. |
| codex-auto-model-router | 권고에 따라 구현·출처 검토는 GPT-6 Luna/high 하위 에이전트, 독립 리뷰는 GPT-6.1 Sol/medium 하위 에이전트로 실행. 메인 대화 모델 전환은 하지 않았다. |
| Product Design | 로컬 in-app browser에서 기존 흐름 6단계를 캡처·검토. [디자인 점검 기록](../design/LOCAL_DEMO_AUDIT.md)에 근거와 UI01 후속 항목을 남긴다. |
| Figma | 연결·권한을 읽기 전용으로 확인했다. 현재 응답은 View seat, Code Layers 비활성이다. 대상 Figma 파일이 제공되지 않았으며 디자인 파일 작성·업로드는 실행하지 않았다. |
| Canva | 기존 OpsPilot 디자인 검색을 시도했으나 재인증 필요 응답으로 자료 확인 불가. 디자인 생성·업로드는 실행하지 않았다. |
| ImageGen·Sites 등 | 이번 범위에는 새 이미지나 웹사이트 게시가 필요하지 않아 생성·게시하지 않았다. UI 제작 시 시각 자료와 해당 기능의 필요성을 정한 뒤 적용한다. |

## 검증 기준과 남은 위험

- 기존 전체 테스트·CLI 스모크, 새 잘못된 manifest 거부·정상 분할 테스트, API 권한 거부 후 연결 종료 테스트가 통과해야 한다.
- 승인 전 mock write 차단, 승인 초안 변조 거부, 중복 영수증 방지와 응답 유실 복구 회귀를 유지한다.
- 현재 입력 actor는 위조 가능한 demo persona다. 바인딩은 `127.0.0.1`만 사용하며 공개 배포하지 않는다.
- 의존성 범위가 넓어 이번 설치 조합에서 Starlette/HTTPX 테스트 클라이언트 deprecation warning이 발생했다. 실행은 검증하되 의존성 잠금·지원 조합 정리는 별도 작업이다.
- `.git` 없는 압축 해제 디렉터리이므로 code commit은 미확보다. G0/G1 공식 통과, 성능, 비용, coverage는 미측정이다.
