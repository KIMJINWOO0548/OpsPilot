# 포트폴리오 95점 도전 평가표 (현재 평가 = 보류)

*이 표는 공식 SK 채용 평가가 아니라, 사전에 약속한 내부 가중 루브릭입니다.*

| 평가 항목 | 만점 | 점수 입력 | 인정 가능한 증빙 |
|---|---:|---|---|
| 채용 직무 적합성 | 12 | 보류 | 실제 API/SQL/RAG/Agent/운영 스크린샷·코드 |
| 기술 난이도·문제 설정 | 14 | 보류 | 명세된 실패 경계·시간 모델·재현 케이스 |
| 독자 설계 유효성 | 16 | 보류 | 최신 기술 B3 대비 paired 결과+ablation |
| 실험의 신뢰성 | 18 | 보류 | 외부/독립 라벨, group split, CI, manifest |
| SW 설계·운영 | 14 | 보류 | auth/RLS/outbox/복구/fault harness/CI |
| 데이터·업무 현실성 | 10 | 보류 | 공개 실원본(적법), source-version provenance/검토 |
| 외부 인정·검증 | 10 | 보류 | 독립 재실행·공식 점수·OSS 기여·발표 등 실제 증빙 |
| 전달력 | 6 | 보류 | 실행 가능한 README·데모·논문형 보고 |
| **합계** | **100** | **판정 보류** | **95+는 외부 검증 등 실측 후에만 가능** |

**상한 규칙:** 외부 데이터 평가·독립 검토 부재는 최대 79점, B4가 강한 대조군보다 좋아지지 않으면 최대 82점, 권한/미승인 write 위반 시 최대 69점, 외부 재현 미달 시 외부 검증 배점 4/10 이하. 현재는 이 점수를 계산할 수 있는 외부/실측 산출물이 없음.

## 2026-10-20 추가 증빙과 인정 한계

- [공식 원천 8종 비교표](research/prior_art_matrix.csv)와 [collision matrix](research/NOVELTY_COLLISION_MATRIX.md): 연구 질문·라이선스 범위를 설명하는 근거다. 신규성이나 성능 우위의 증거는 아니다.
- [원문·시간·권한·분할 평가 코드](../src/opspilot_x/evaluation_data.py), [지표/paired cluster CI 코드](../src/opspilot_x/evaluation_metrics.py), [실행 명세](evaluation/EXPERIMENT_RUNBOOK.md): 평가 인프라의 코드 근거다. 실제 대조군·외부 데이터 실행 결과는 없다.
- 30개 합성 예시는 작성자 정답/원문 대조를 위한 후보이고 독립 검토는 0건이다. AI 코드 리뷰를 독립 사람 평가나 외부 인정으로 계산하지 않는다.

점수·95점 달성·채용 합격 가능성은 계속 **판정 보류**다. 제출 경쟁력을 주장하려면 이후 실제 비교 실험, 독립 정답 검토, 인증·운영 경계와 외부 재실행 증빙이 필요하다.

## 2026-10-22 제품 구현 증빙

- [인증 API](../src/opspilot_x/api.py), [계정/session](../src/opspilot_x/auth.py), [DB 근거 선필터](../src/opspilot_x/evidence_store.py), [React 콘솔](../web/src/main.tsx): 실제 구현 파일이다. 실제 모델 성능 실험의 증거는 아니다.
- [브라우저 QA·화면](design/CONSOLE_QA.md), [실행·배포 안내](DEPLOYMENT.md), [검증 기록](../verification/console-final-2026-10-22.json): 로컬에서 로그인→분석→독립 승인→mock 유실→복구 경로와 114 테스트의 근거다. 외부 검토나 서비스 운영 실적으로 계산하지 않는다.
- [위협 모델](safety/THREAT_MODEL.md): 저장 action 변조·scope 존재 추측·관계 ID 누출을 발견하고 수정한 실패 사례다. DB 전체 관리자 변조·분산 장애·기업 보안 인증까지 해결한 것은 아니다.

현재 제출 시에는 “인증된 근거·시점 검증 콘솔과 mock 승인/복구를 구현”이라고 설명할 수 있다. “기업 운영 배포 완료”, “B4 우위”, “95점 달성”은 아직 근거가 없다.

같은 날 계정 회수 직후 [Windows 검사](../verification/recovery-final-2026-10-22.json)는127 pass/1 failure/5 errors였다. 이후 Docker 엔진을 복구해 [현재 Linux 전체133개·스모크·설치 이미지 실제 HTTP E2E](../verification/runtime-final-2026-10-22.json)를 통과했다. 로컬 Compose는 Healthy·non-root/read-only/loopback이다. 새 Windows baseline은126 pass/7 errors로 별도 미해결이다. GitHub CI 실실행·HTTPS/외부 배포·연구 성능·독립 평가는 미확보이며 점수는 계속 보류다.

10월23일에는 같은 이미지의 실제 Chrome 승인/복구·충돌/과거 차단을 [새 화면](design/CONSOLE_QA.md)으로 확인했다. 서비스는 Healthy이나 Windows 재검사는120 pass/2 failures/11 errors(10014)이며 재시작 범위·OS 원인은 미확정이다. [최신 검증](../verification/reboot-final-2026-10-23.json)은 이전 Linux 통과와 구분한다. 실원본·독립 라벨·B0~B4 실험·외부 수용 증거는 여전히 없으므로 점수를 갱신하지 않는다.
