# 추가 의존성 확인 범위 (2026-10-22)

백엔드는 기존 FastAPI/SQLite/표준 라이브러리를 재사용했고 인증용 새 패키지는 추가하지 않았다. React/TypeScript UI 요구에 따라 10월 20일 로컬 설치한 프런트 의존성을 `web/pnpm-lock.yaml`에 고정했다. 이후 승인 없는 추가 설치를 금지한 사용자 규칙을 반영하여 새 패키지·MCP·플러그인을 설치하지 않았다.

| 직접 의존성/도구 | 고정 버전 | 설치물에서 확인한 표기 |
|---|---|---|
| React / React DOM | 19.3.1 | React 배포 LICENSE의 MIT |
| Vite | 8.3.4 | 배포 LICENSE.md의 MIT; 같은 파일에 번들된 타 코드 고지 포함 |
| TypeScript | 7.0.2 | 배포 package.json의 Apache-2.0, LICENSE/NOTICE 포함 |
| FastAPI | 0.148.0 | 설치 metadata: MIT |
| Uvicorn | 0.54.0 | 설치 metadata: BSD-3-Clause |
| Pydantic | 2.14.1 | 설치 metadata: MIT |
| Starlette | 1.9.0 | 설치 metadata: BSD-3-Clause |

이 표는 확인한 파일/metadata 범위의 기록이다. 모든 전이 의존성·컨테이너 OS 패키지의 고지·SBOM·취약점 검사를 마친 법적 배포 승인이 아니다. 코드의 라이선스가 외부 데이터/모델 가중치의 이용 권리를 주지도 않는다. 이미지 base tag는 digest 고정 전이며 Python lock은 wheel hash까지 잠그지 않았다. 배포 이미지가 만들어진 다음 SBOM/라이선스 고지·취약점 검사를 수행해야 한다. 외부 dataset·유료 모델·브랜드 이미지·서드파티 폰트는 새로 받지 않았다.
