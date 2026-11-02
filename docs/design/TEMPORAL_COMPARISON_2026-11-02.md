# 관측 시점 비교 · 기능 수용 기록

같은 업무 유효 시점에서 당시 알던 자료와 나중에 알려진 자료가 다른 판단을 만드는지 한 화면에서 비교한다. A-104의9월20일 판단을9월20일 관측 근거로 보면 **수동 점검**,10월6일 관측 근거로 보면 **센서 진단 우선**이다. 양쪽 판정과 v1→소급 정정 인용 변화를 함께 확인할 수 있다.

기존 타임라인은 문서별 시간축만 보여주고 단일 분석은 다음 결과로 교체됐다. 두 시점의 결과를 재계산하고 차이를 반환하는 API·읽기 전용 비교 화면을 추가했다. 기존 실행 미리보기/감사 이력과의 중복 및 설비 영향 모델 부재를 검토한 선택이다. [ADR-005와 수용 조건](../decisions/ADR-005-TEMPORAL-COMPARISON.md)에 이유를 기록했다.

## 사용자 흐름

1. 로그인 후 **근거 타임라인 → A-104 사후 정정 예시**를 선택한다. 자산과 유효 시점, 기준/비교 관측 시점이 채워진다. [비교 전 빈 상태](temporal-comparison-2026-11-02/03-comparison-empty.png).
2. **두 시점 비교**를 누르면 같은 유효 시점의 두 판정·권장 조치·인용과 인용 변화가 표시된다. [핵심 비교 화면](temporal-comparison-2026-11-02/04-comparison-changed-panel.png). 비교 결과에는 초안/승인/실행 조작이 없다.
3. 두 관측 시점을 같게 하거나 근거가 바뀌지 않는 구간을 선택하면 변경 없음을 표시한다. [변경 없음](temporal-comparison-2026-11-02/05-comparison-unchanged.png). 시간 숫자가 다른 것 자체는 판정 변화로 세지 않는다.
4. 입력 변경·실패·로그아웃은 이전 결과를 지운다. 로딩 중 조건·중복 요청을 잠그며 역순 시점은 한국어 오류를 표시한다. 주입한503·통신 실패 뒤 재시도로 복구했다. [오류 상태](temporal-comparison-2026-11-02/07-comparison-error.png).
5. 390px에서는 결과를 세로로 배치하고 긴 인용 표는 패널 안에서 스크롤한다. 문서 clientWidth/scrollWidth는 모두390이다. [모바일](temporal-comparison-2026-11-02/08-comparison-changed-mobile.png).

조사 조건의 `알려진 시점`이 기준 관측 시점이다. 별도 비교 관측 시점만 바꿔 비교한다. 문서 검색어는 판정 비교에 사용하지 않는다고 화면에 안내한다. 현재 접근 권한을 양쪽에 적용하며, 과거 사용자의 실제 권한 이력을 재현하는 기능은 아니다. 인용 제외는 해당 판정에서 빠졌다는 뜻이며 문서 삭제나 ACL 변경 이력을 의미하지 않는다.

## API와 재현

기존 로그인 세션·CSRF를 사용해 `POST /api/v1/analysis/compare`를 호출한다. 본문 예시:

```json
{
  "asset_id": "A-104",
  "claim_key": "inspection_priority",
  "effective_at": "2026-09-20T10:00:00+09:00",
  "before_known_as_of": "2026-09-20T10:00:00+09:00",
  "after_known_as_of": "2026-10-06T10:00:00+09:00"
}
```

응답의 `before`/`after`는 기존 Analysis이고 `changes`는 상태·조치 변경 여부와 추가/제외된 허용 인용이다. 인용은 ID뿐 아니라 source/version/locator/checksum까지 비교한다. 두 SQL 조회는 하나의 `query_only` 읽기 트랜잭션에서 현재 tenant/team/role·각 관측 시점으로 선필터한다. 비교 중 ACL이 바뀌어도 같은 DB snapshot을 사용하며 다음 요청에서 회수를 반영한다. 본문 actor는 세션 권한을 바꾸지 못한다. 미인증401·CSRF/외부origin403·timezone 누락/역순422를 검사한다.

`python -m pytest tests/test_analysis_compare.py -q`로 새21개를 재현한다. 비교 전후 proposals/work_orders/audit의 모든 행이 동일하며, 기존 UNKNOWN_RECONCILE의 영수증도 같은 ID로 복구되고 mock 작업은1건을 유지한다. 숨겨진 근거와 없는 근거의 결과는 같고, 비인가 문서 ID·원문·조치를 반환하지 않는다.

## 검증 결과와 범위

개발·디자인·독립 QA·읽기 전용 코드 검토를 나눴다. Product Design `get-context` 브리프를 사용해 기존 타임라인과 운영자 목표를 고정하고 후보를 비교했다. 동봉 context preflight 스크립트는 클라우드 리소스에서 읽을 수 없어 저장된 디자인 컨텍스트를 사용했다고 주장하지 않았으며, 현재 코드와 새로 캡처한 실제 화면을 기준으로 진행했다.

Linux Python3.12.14 / Node24.19.0 / pnpm11.25.0에서 baseline169개 통과, 초기 새15개는 endpoint 부재404로 실패했다. 스냅샷 일관성과 인용 metadata/order 검사를 더한 최종 새21개·전체 **190개 통과**, 프런트5개·TypeScript/build·Ruff·mock E2E·합성8개·평가 계약 예제·필수파일24개·pip check·diff 검사를 통과했다. 합성/계약 검사는 모델 성능 수치가 아니다.

실제 FastAPI·임시 SQLite·Chromium의 독립12개 검사에서 정상/변경 없음/충돌/빈 근거/시간 오류/통신 실패/재시도/로그아웃/읽기 전용·영수증 보존/모바일을 확인했다. 페이지 예외는0이다. 디자인 오류 화면 검사에서는 의도적으로 주입한HTTP503 콘솔1건을 별도 기록했다. 화면 리더·색 대비 계측은 하지 않았다. 임시 서버8765/18213은 종료했다.

[명령·소스 hash](../../verification/temporal-comparison-local-2026-11-02.json), [pytest XML](../../verification/temporal-comparison-pytest-2026-11-02.xml), [독립 QA](../../verification/temporal-comparison-qa-2026-11-02.json), [디자인 화면 검사](../../verification/temporal-comparison-design-2026-11-02.json)를 보존했다.

이 기능은 합성 자료·결정적 규칙의 읽기 전용 비교다. 실제 설비 영향·LLM·외부 자료·실서비스 명령·새 ACL·과금은 추가하지 않았다. G0/G1 연구 수용·운영 전체 안전성·Windows WPF/설치기 실행은 미검증이다. 기존 GitHub403은 미해결이며 이번에는 원격 쓰기/다른 인증/재시도/배포를 시도하지 않았다. 로컬 `feat/temporal-decision-comparison`을 만들고 이전 `feat/proposal-review-readiness`의5bd503f는 보존했다.
