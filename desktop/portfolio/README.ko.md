# OpsPilot-X Windows 로컬 작업공간

Windows x64에서 ZIP을 쓰기 가능한 로컬 폴더에 풉니다. 압축에 Flutter, Python 런타임, 로컬 Qwen 생성·임베딩 서버가 포함됩니다. 운영 데이터는 운영자가 지정한 작업공간에 보관됩니다.

## 새 작업공간 시작

1. 명령 프롬프트에서 다음 명령을 실행합니다. 두 계정의 암호는 각각 입력하고, 사용자 이름·조직·팀은 사용할 값으로 바꿉니다.

~~~bat
OpsPilot-Workspace.cmd --profile "C:\OpsPilotData" init
OpsPilot-Workspace.cmd --profile "C:\OpsPilotData" user-add --username author --tenant ops --team archive --role engineer
OpsPilot-Workspace.cmd --profile "C:\OpsPilotData" user-add --username reviewer --tenant ops --team archive --role approver
OpsPilot-Workspace.cmd --profile "C:\OpsPilotData" import "C:\Import\approved-evidence.json"
OpsPilot-X.cmd --workspace "C:\OpsPilotData"
~~~

2. 작성자로 로그인하고 자산·검토 항목을 선택합니다. AI 인용과 규칙 판정을 확인하고 원문을 열 수 있습니다. 확인한 근거로 검토 요청을 보냅니다.
3. 검토자가 같은 작업공간에 로그인해 승인합니다. 승인 결과를 PDF로 생성하거나 응답 유실 후 실행 결과를 확인할 수 있습니다.

작업공간 초기화는 새 디렉터리에서만 실행됩니다. 샘플 경로를 실행할 때에는 시작 인자 없이 `OpsPilot-X.cmd`를 실행합니다. 운영 작업공간과 샘플 데이터는 별도의 디렉터리에 저장됩니다.

## 근거 반입

[JSON 양식과 예시](evidence-template.json)를 복사해 조직·팀·자산·검토 항목·승인된 조치·유효 시점을 기록합니다. `text`에 실제 근거 구절을 넣고, `locator`에 원문에서 다시 찾을 위치를 적습니다. 버전을 바꿀 때는 새 `evidence_id`를 발급하고 같은 규정의 `source_id`를 유지합니다. 대체되는 이전 근거는 `supersedes`에 기록합니다.

이 경로에는 현재 역할로 읽을 수 있게 승인된 자료만 반입합니다. SHA-256을 생략하면 반입 시 UTF-8 본문에서 계산합니다. 근거 ID는 120자, 원문 응답은 4 MiB까지 허용합니다. 손상된 해시, 날짜 경계 오류, 변경된 기존 근거 ID가 있으면 일괄 반입을 거부합니다. 같은 내용으로 다시 반입하면 기존 스냅샷을 유지합니다.

## 계정·백업

~~~bat
OpsPilot-Workspace.cmd --profile "C:\OpsPilotData" revoke-sessions --username reviewer
OpsPilot-Workspace.cmd --profile "C:\OpsPilotData" user-disable --username reviewer
OpsPilot-Workspace.cmd --profile "C:\OpsPilotData" backup "C:\Backups\opspilot-2026-11-23.sqlite3"
OpsPilot-Workspace.cmd --profile "C:\OpsPilotRecovered" restore "C:\Backups\opspilot-2026-11-23.sqlite3"
~~~

앱을 한 번 기동한 뒤 새 목적지 파일에 백업합니다. 복원은 새 디렉터리에서 시작하며 복원본의 이전 계정과 세션은 비활성화됩니다. 운영자가 현재 권한과 승인·실행 이력을 대조한 뒤 필요한 계정을 새로 발급합니다. 작업공간 디렉터리를 읽을 수 있는 OS 계정은 로컬 파일과 SQLite를 읽을 수 있으므로 운영자만 이 디렉터리에 접근하도록 파일 권한을 구성합니다. 원격 공동 사용에서는 서버 인증·파일 권한·백업 절차를 별도로 검증합니다.

Qwen 모델은 Apache-2.0, llama.cpp는 MIT입니다. 라이선스와 무결성 해시는 `licenses`와 `release-manifest.json`에 있습니다.
