# 인증 콘솔 실행·배포 준비

현재 패키지는 **서버 계정 인증 + React 콘솔 + SQLite + 합성 근거 + mock 작업 원장**을 한 origin에서 실행한다. 실제 공개 배포나 외부 모델 평가를 완료한 제품은 아니다. 기본 바인딩은 loopback이다. [ADR-003](decisions/ADR-003-SECURE-CONSOLE.md) 참조.

## Windows 로컬 실행

Python 3.12, Node.js 24, pnpm 11이 필요하다. 기존 .venv가 있으면 재사용한다.

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -c requirements-runtime.lock -e '.[dev]'
Push-Location web
pnpm install --frozen-lockfile
pnpm build
Pop-Location
.venv/Scripts/python.exe scripts/manage_users.py --username engineer --tenant demo --team team_a --role engineer
.venv/Scripts/python.exe scripts/manage_users.py --username reviewer --tenant demo --team team_a --role approver
.venv/Scripts/python.exe -m uvicorn opspilot_x.api:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

각 계정의 12자 이상 비밀번호를 프롬프트에 입력한다. 기본 계정·자동 비밀번호·공개 가입은 없다. 계정은 `OPSPILOT_DB`가 가리키는 DB에 생성되므로 CLI와 서버가 같은 경로를 사용해야 한다. 환경 변수가 없으면 루트의 `opspilot_demo.sqlite3`다. `.env` 파일을 서버가 자동 읽지는 않는다. 재설치/서버 재시작 시 DB를 지우지 않는다.

브라우저에서 <http://127.0.0.1:8000>으로 접속한다. engineer로 A-103을 현재 시점 분석해 초안을 만들고 로그아웃한다. reviewer로 로그인해 승인함에서 근거·해시를 검토하고 승인 후 mock 실행한다. `응답 유실 시뮬레이션`을 선택하면 상태 조회로 영수증을 복구한다. 과거 분석·충돌·불충분 근거는 현재 작업 초안을 허용하지 않는다. 로그인은 서버 DB identity를 사용하고 본문의 `actor`는 권한을 바꾸지 못한다.

`RUN_WINDOWS.ps1`은 설치·빌드·회귀 검사 후 loopback 서버를 시작한다. Mac/Linux는 `RUN_MAC_LINUX.sh`를 사용한다. 개발 시 Vite는 `web`에서 `pnpm dev`, API는 별도 8000 서버를 사용한다. Vite 개발 프록시만 사용하며 production은 FastAPI 정적 빌드다.

## 컨테이너

```bash
docker compose up --build -d --wait
docker compose exec opspilot python scripts/manage_users.py --username engineer --tenant demo --team team_a --role engineer
docker compose exec opspilot python scripts/manage_users.py --username reviewer --tenant demo --team team_a --role approver
```

컨테이너는 UID10001, 읽기 전용 root, drop capabilities, `/data` 영속 volume으로 구성했다. Docker 시작 장애 복구 후 **실제 이미지 build·Compose Healthy·HTTP 자산/인증 경계·설치 이미지 mock E2E**를 확인했다. [검증 기록](../verification/runtime-final-2026-10-22.json). CI에도 Linux build/healthcheck 작업이 있지만 GitHub에서 실행한 증거는 아직 없다. Node/Python base image는 tag로 지정했고 이번에 해석된 digest는 빌드 로그에 보존했다. Dockerfile digest·wheel hash까지 고정한 공급망 재현성은 미완료다. 오래된 `demo_data` 볼륨을 자동 이관하지 않는다. 기존 Compose DB가 필요하면 종료 후 백업·이관 범위를 먼저 확인한다.

2026-10-22 최초 호스트 점검에서 `wsl --status`는 exit50(미설치), Docker의 `wslEngineEnabled=true`와 Desktop `starting`을 확인했다. [Docker 공식 요구 조건](https://docs.docker.com/desktop/features/wsl/), [Microsoft 설치 안내](https://learn.microsoft.com/en-us/windows/wsl/install), [옵션 명세](https://learn.microsoft.com/en-us/windows/wsl/basic-commands)를 대조한 뒤 **사용자의 WSL2 설치 승인**을 받아 관리자 권한으로 `wsl --install --no-distribution`을 실행했다(exit0). 이후 WSL **3.0.3.0**, 기본 버전 **2**, Docker가 생성한 `docker-desktop`의 Running/VERSION 2와 커널 `6.18.54.1-microsoft-standard-WSL2` 실행을 확인했다. Ubuntu 등 별도 사용자 배포판은 설치하지 않았다.

WSL 설치 직후 `docker desktop restart --timeout 60`은 init 응답 대기로 시간 초과(exit1), 엔진 version 조회는 API500(exit1)을 반환했다. 당시에는 WSL 커널만 확인했고 build/run은 미검증이었다. 확인한 CBS/Windows Update 재부팅 대기 key는 없었으며 자동 재부팅을 요청하지 않았다. [설치 당시 증거](../verification/wsl-install-2026-10-22.json)와 아래 후속 복구를 구분한다. Windows Python의10014와 WSL 미설치의 인과관계도 입증하지 않았다.

위 실패 뒤의 복구: `wsl --terminate docker-desktop`(배포판 등록/디스크 삭제 아님) → `docker desktop restart --timeout 60`으로 엔진29.8.2 응답을 확인했다. `docker compose build --progress plain`, `docker compose up --no-build -d --wait --wait-timeout 90` 모두exit0이며 서비스가 Healthy다. 실제 inspect로 UID10001·read-only root·ALL cap drop·no-new-privileges·host127.0.0.1을 확인했다. 이 복구는 Windows를 재부팅하지 않고 수행했으며, Windows 소켓 오류 해결과는 구별한다.

Linux Python3.12.15에서 동일 소스/133개 테스트를 **133 passed / 0 skipped / dependency warning1개**로 검증했고 두 스모크도exit0이었다. 검증 컨테이너는 소스를 읽기 전용으로 마운트하고 `OPSPILOT_DB=/tmp/import-default.sqlite3`를 사용했다. pytest9.1.1/httpx0.28.1은 pyproject의 dev 범위로 임시 `/tmp`에 설치했으며 서비스 이미지를 수정하지 않았다. 최초 검증은 `/data` volume 없이 read-only root로 실행해 DB 경로 오류였고, 테스트 설정에 임시 경로를 지정해 해결했다. 서비스 자체는 처음부터 volume을 사용해 Healthy였다. [Linux 전체 로그](../verification/linux-container-2026-10-22.log), [XML](../verification/linux-pytest-2026-10-22.xml).

별도 네트워크 없는 컨테이너에서 설치된 패키지를 실행하고 임시 DB의 가상 계정2개로 실제 HTTP 로그인→분석→초안→작성자 승인403→독립 승인→유실→복구→동일 receipt 재시도→감사→logout/replay401을 검증했다. 서비스 volume/기존 계정은 변경하지 않았다. Compose의 기본 계정은 없으므로 로그인하려면 위 CLI로 운영자가 직접 계정을 생성해야 한다. HTTP HTML/JS/CSS200·미인증401도 확인했다. 이후 다시 사용 가능해진 브라우저 도구로 접근을 시도했으나 `net::ERR_CONNECTION_REFUSED`/`net::ERR_CONNECTION_FAILED`로 화면 상호작용을 완료하지 못했다. 터미널 브라우저로 우회하지 않았다. [설치 이미지 E2E](../verification/container-image-e2e-2026-10-22.json), [검증 당시 HTTP/설정 검사](../verification/container-http-2026-10-22.json).

추가 운영 관측: 최종 정적검사 시 Docker pipe가 다시 사라졌고 Desktop 프로세스가 실행되지 않았다. 일반 hidden 앱 실행 뒤 보존된 동일 컨테이너가 restart 정책으로 Healthy에 돌아왔다. 종료 원인은 확인되지 않았고 Application crash event도 조회 범위에서 발견되지 않았다. 재실행 성공을 장기 지속성 보장으로 설명하지 않는다. [최종 서비스 확인 시각/브라우저 실패](../verification/runtime-final-2026-10-22.json)를 별도로 본다. Desktop/Windows 재시작과 장기 부하·중단 복구는 여전히 운영 수용 항목이다.

**10월 23일 후속:** 표준 Desktop hidden 실행 뒤 보존된 동일 서비스가 Healthy로 복구됐다. 실제 Chrome에서 서비스8000의 로그인 화면을 확인하고, 같은 이미지의 별도 loopback18010·read-only·non-root·tmpfs DB에서 임시 계정2개로 정상 분석/타임라인/독립 승인/유실 복구와 충돌·과거 초안 차단을 확인했다. 서비스 volume과 기존 계정은 변경하지 않았다. 임시 컨테이너는 ID를 대조한 뒤 종료·자동 제거했고8000 로그인 화면을 남겼다. [브라우저 QA](design/CONSOLE_QA.md), [최신 상태·정리 증거](../verification/reboot-final-2026-10-23.json). 이 Chrome 경로의 연결 오류는 해소됐지만 장기 실행 안정성은 미검증이다.

이번 검증의 입력 코드도 [Windows 호스트용 Linux 검사 runner](../verification/verify_linux_container.py), [격리 이미지 HTTP assert 스크립트](../verification/image_http_smoke.py)에 보존했다. 전자는 루트에서 `.venv/Scripts/python.exe verification/verify_linux_container.py`로 실행한다(Docker CLI 설치 경로 사용). 후자는 이미지에 읽기 전용으로 마운트하고 `docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true --tmpfs /tmp:mode=1777,size=32m --mount "type=bind,source=절대경로/verification/image_http_smoke.py,target=/smoke.py,readonly" 이미지이름 python /smoke.py`로 실행한다. 둘 다 기존 서비스 DB를 사용하지 않으며 실험 성능 평가 도구가 아니다.

## HTTPS 환경으로 옮기기 전

- ingress에서 TLS를 종료하고 `OPSPILOT_SECURE_COOKIE=true`를 지정한다. 현재 `false`는 loopback HTTP 개발용이다.
- 앱은 `Origin == request.base_url`을 검사한다. 프록시가 external host/scheme을 정확히 전달해야 한다. 기본 `--no-proxy-headers`는 위조 forwarding header를 신뢰하지 않는다. 사설 네트워크의 지정 proxy IP만 신뢰하는 별도 uvicorn 설정을 검토하고 공격/정상 요청을 검증한다.
- ingress의 허용 host, 요청 크기(예: 16 KiB), rate limit, 접근 로그의 비밀번호·cookie·CSRF 마스킹을 적용한다. 외부 포트를 바로 노출하지 않는다.
- 단일 인스턴스 SQLite의 쓰기/로그인 제한을 실부하로 측정한다. 다중 노드·외부 실행은 Postgres/outbox/별도 mock 프로세스 ADR과 장애 검증 이후다.
- 계정 회수·세션 폐기·검증된 새 DB 복원 CLI를 제공한다. 아래 절차를 임시 DB에서 검증했다. 계정 재활성화/비밀번호 변경·OIDC/SSO·외부 침투 테스트·브라우저 자동회귀·부하/P95 측정은 미완료다.

비밀번호는 PBKDF2-HMAC-SHA256 600,000회+개별 salt, 세션은 random opaque token의 hash를 DB에 저장한다. cookie는 HttpOnly/SameSite Strict이며 CSRF token은 로그인/me 응답으로 받아 메모리에만 둔다. 세션 만료는 8시간, 로그인 시도 제한은 사용자/IP별 SQLite 15분 창이다. 정상 로그인도 시도 수에 포함된다. 이 제한은 분산 공격 방어·기업 보안 인증을 의미하지 않는다.

## 보존·복구와 확인

DB에는 계정 hash·세션·근거·초안·감사·mock 영수증이 함께 있으므로 민감 자료로 취급한다. 원본 근거는 같은 evidence ID에 덮어쓸 수 없고 새 버전 ID로 넣는다. 현재 관리 수집 API는 없다. 실행 중 DB 파일 하나만 복사하지 않는다. 다음 CLI가 SQLite backup API의 일관된 snapshot을 새 파일에 만든다.

```powershell
# 디렉터리는 운영자가 미리 준비한다. 기존 목적지는 거부한다.
.venv/Scripts/python.exe scripts/backup_db.py backup --source ./opspilot_demo.sqlite3 --destination ./backups/snapshot.sqlite3
# 서버를 정지하고, 새 경로로 복원한 뒤 OPSPILOT_DB를 변경해 시작한다.
.venv/Scripts/python.exe scripts/backup_db.py restore --source ./backups/snapshot.sqlite3 --destination ./recovered.sqlite3
```

원본은 읽기 전용으로 열고 임시 파일에서 integrity_check·필수 table을 검증한 뒤 overwrite 없이 게시한다. 실패 시 해당 임시 파일만 지운다. hard link를 지원하는 같은 파일 시스템이 필요하며 지원하지 않으면 실패로 종료한다. 복원본의 모든 세션을 폐기하므로 다시 로그인해야 한다. 계정 disabled/password·감사·초안은 snapshot 시점으로 돌아간다. 백업 이후 비활성화한 계정·변경한 암호가 복원으로 되돌아갈 수 있으므로 외부 포트 연결 전에 회수 목록과 계정 상태를 대조해야 한다. 기존 운영 DB 파일의 교체/삭제·실계정 변경은 자동 수행하지 않는다. 암호화·offsite 보관·보존 정책·실운영 재해 복구 시간은 미검증이다.

## 계정 회수와 세션 폐기

아래 명령은 운영자가 특정 계정에 대한 변경을 결정했을 때 실행한다. 개발 검증에서는 임시 DB 계정만 사용했다. 기존 CLI의 create 명령은 유지한다.

```powershell
# 현재 세션만 폐기: 올바른 비밀번호로 새 로그인 가능
.venv/Scripts/python.exe scripts/manage_users.py --db ./opspilot_demo.sqlite3 --username engineer --action revoke-sessions
# 계정 비활성화 + 모든 세션 폐기: 새 로그인도 거부
.venv/Scripts/python.exe scripts/manage_users.py --db ./opspilot_demo.sqlite3 --username engineer --action disable
```

회수 명령은 비밀번호를 읽거나 요구하지 않는다. unknown 계정/DB는 오류로 끝난다. users의 `disabled`·`session_version`은 기존 계정/해시를 보존하는 호환 migration으로 추가되며 서버 재시작 시 적용된다. password 해시 계산 중 회수·폐기가 발생하면 세대 번호를 다시 검사해 새 세션 발행을 거부한다. 계정 비활성 상태는 매 새 요청에서 확인하지만 이미 허용되어 진행 중인 작업의 OS 수준 취소는 보장하지 않는다. 재활성화·비밀번호 재설정 기능은 아직 없다.

```bash
python -m pytest -q
python scripts/smoke_demo.py
python scripts/eval_smoke.py
python -m ruff check src tests scripts
python -m pip check
cd web
pnpm test
pnpm build
```

헬스체크의 `production_ready:false`, `benchmark_verified:false`는 의도된 정직한 상태다. 합성 smoke의 8개 일치를 외부 정확도로 홍보하지 않는다.

## 이번 Windows 환경의 실행 오류

2026-10-21~22에 Python `socket.socketpair()`/`asyncio` 생성 단계에서 간헐적인 WinError 10014가 발생했다. 앱을 import하지 않은 최소 재현에서도 관측했으며 Python 3.12.14와 설치된 3.12.10에서 모두 확인했다. 한 실행은 111 passed / 2 setup errors, 마지막 PTY 실행은 동일 테스트를 제거하거나 우회하지 않고 114 passed / 1 dependency warning이었다. 특정 터미널 방식이 근본 해결이라고 결론 내리지 않는다. 표준 라이브러리 수정·예외 무시·테스트 skip·전역 Winsock 설정 변경을 하지 않았다.

10월 21일 브라우저 서버는 별도 진단 프로세스에서 socketpair를 한 번 생성/종료한 뒤 uvicorn을 시작해 실행됐다. 22일에는 기본 uvicorn 명령이 PTY에서 사전 초기화 없이 시작됐다. 두 방식 모두 보장된 복구 절차라고 결론 내리지 않으며 기본 스크립트에 workaround를 넣지 않았다. 다른 호스트/Linux 컨테이너에서 재실행하고 OS 네트워크 계층 원인을 확인하는 일이 배포 전 남아 있다. 개발용 `.local/access.json`과 `.local/console.sqlite3`는 브라우저 검증 전용이며 배포 이미지/소스에 포함하지 않는다.

계정 회수·backup 직후 Windows 전체는127 passed/1 failed/5 errors였고, 새 Windows baseline은 **126 passed / 7 errors**였다. 실패는10014가 포함된 루프 생성 오류이며 in-process smoke도exit1이다. 앱 없는 IPv4 socketpair와 정확한 인자형의 native Winsock listen에서도10014가 재현돼 앱 코드에만 한정되지 않는다. IPv6 비교는25/25 통과했으나 OS 원인 자체는 미확정이다. Winsock 공급자·로드 모듈에 제삼자 코드 증거는 없었고 자식의 호환성 환경변수를 제거해도 실패했다. 작은 backlog·예외 무시·stdlib patch·테스트 skip·Winsock reset·보안 제외를 해결책으로 넣지 않았다. 사용자가 직접 재부팅 후 같은 probe→전체 pytest→smoke로 확인해야 한다. 위 Linux133개 통과는 이 Windows 실패를 삭제하거나 해결한 결과가 아니다. [현재 검증](../verification/runtime-final-2026-10-22.json), [Windows 로그](../verification/runtime-baseline-pytest-2026-10-22.log).

10월 23일 사용자의 재부팅 완료 보고 후 실제 재검사는 **120 passed / 2 failures / 11 errors / 0 skipped**, smoke exit1, 합성 eval8/8 exit0이었다. 실패·오류13건 모두 TestClient/AnyIO의 루프 생성 중10014를 포함한다. 앱 없는 IPv4 socketpair는33/60 성공·27건10014, IPv6는60/60 성공이었다. 읽기 전용 모듈/레지스트리 검사에서는 Python에 verifier가 적용됐다는 증거를 찾지 못했다. FTH 시스템 활성 설정만으로 Python 적용이나 원인이라고 단정하지 않는다. 커널 LastBoot는10월21일로 표시돼 사용자가 수행한 재시작 범위를 확인 중이다. 종료/빠른 시작과 실제 재시작의 차이는 [Microsoft 설명](https://learn.microsoft.com/en-us/troubleshoot/windows-client/setup-upgrade-and-drivers/fast-startup-causes-system-hibernation-shutdown-fail)을 참고하되, 이 환경의 원인으로 확정하지 않는다. 자동 재부팅·Winsock reset·보안 설정 변경 없이 [실패와 현재 상태](../verification/reboot-final-2026-10-23.json)를 보존했다.
