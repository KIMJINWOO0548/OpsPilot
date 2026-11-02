# ADR-000: 단일 기술 문제에 집중하며 축소 G2 데모를 먼저 제공

- Status: accepted as **initial implementation scaffold**, not validated research.
- Context: 취업 포트폴리오는 명확한 문제 해결, 비교실험, 재현성, 엔지니어링 깊이를 모두 보여줘야 한다.
- Decision: 실제 AI 모델 성능이라고 포장하지 않는 결정적 시간/충돌 엔진을 먼저 구현하여 코드 계약과 승인 경로를 검증한다.
- Reason: EIE 접근이 유효하지 않더라도 G2 테스트·안전경계·평가 인프라를 재사용할 수 있다.
- Rejected: 딥러닝 모델 무리한 직접 학습, 멀티에이전트, 본격 React 설계 선행, 공개 서비스 배포, Aegis 중복 재구현.
- Risk: SQLite·클라이언트 역할 입력의 낮은 현실성이 있다. G5 이전 인증·실데이터/DB 분리·실제 fault test 필요.
- Exit: G0 선행연구 검증/strong baseline failure → 좁게 기술 방향 수정. 기술 이득이 없으면 단순 대조군 채택.
