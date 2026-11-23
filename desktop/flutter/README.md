# OpsPilot-X Windows

Flutter Windows 화면이 기존 Python 엔진을 별도 자식 프로세스로 시작합니다. 로컬 세션, CSRF, 승인 버전과 원문 검증은 서버가 처리합니다. 일반 등록과 복구는 AI가 없는 상태에서도 사용할 수 있습니다.

## 실행

패키지의 실행 스크립트가 격리 합성 프로필과 모델 주소를 준비합니다. 개발 실행에는 `--bundle <bundle>`, `--data-dir <profile>`, `--appearance-dir <profile settings>`를 지정합니다. 번들은 `backend/python/python.exe`와 `backend/web/dist`가 필요합니다. 프로필에는 별도로 생성한 합성 `opspilot.sqlite3`를 사용합니다.

AI를 활성화할 때는 런처가 구성한 두 루프백 포트 `OPSPILOT_CHAT_PORT`와 `OPSPILOT_EMBED_PORT`를 자식 프로세스에 전달합니다. 인증이 설정된 서버에는 런처가 `OPSPILOT_MODEL_KEY`도 전달합니다.

요청 등록 화면에서 자산을 선택하고 질문을 쓰면 AI가 고른 원문 문장과 정책 판정을 확인할 수 있습니다. 독립 승인 후에는 PDF를 생성하거나 합성 응답 유실을 시험할 수 있습니다. 영수증 확인 뒤 저장을 선택하면 격리 프로필의 `reports` 아래 새 폴더에 검증된 PDF를 씁니다.

## 빌드와 확인

Windows Flutter SDK와 Visual Studio C++ 환경에서 소스를 영문 경로에 복사한 뒤 실행합니다.

```powershell
flutter pub get --offline
flutter analyze --no-pub
flutter build windows --release --no-pub
```

`tool/check_portfolio.dart`에는 번들, 새 테스트 프로필, 런처가 생성한 해당 프로필의 계정 파일을 인자로 넘깁니다. 실제 모델 인용, 충돌 차단, 작성자 승인 거절, 승인 PDF, 프로세스 재시작 후 영수증 복구, 같은 PDF 해시와 기존 파일 보존을 확인합니다.

## Windows x64 포터블 번들 만들기

저장소 루트에서 기존 Python 데스크톱 번들 및 라이선스, Visual C++ x64 재배포 DLL, [검증한 로컬 모델과 런타임](../../docs/decisions/ADR-006-LOCAL-HYBRID-DRAFTS.md)이 들어 있는 폴더를 지정합니다. 준비된 Python 번들에는 `backend/python/python.exe`, `backend/web/dist/index.html`, `licenses/PYTHON-LICENSE.txt`, `licenses/PYTHON-PACKAGES.json`이 필요합니다. 새 스테이징 폴더와 ZIP 경로를 사용합니다.

```powershell
$flutterRelease = 'C:\OpsPilotBuild\flutter\build\windows\x64\runner\Release'
$pythonBundle = 'C:\OpsPilotBuild\python-bundle'
$redist = 'C:\OpsPilotBuild\x64-redist'
$models = 'C:\OpsPilotBuild\models'
python scripts\stage_flutter_portfolio.py `
  --release $flutterRelease --python-bundle $pythonBundle --crt $redist `
  --models $models --destination 'C:\OpsPilotBuild\package' `
  --archive 'C:\OpsPilotBuild\OpsPilot-X-Workspace-win-x64.zip'
```

스크립트가 현재 저장소의 Python 소스를 복사하고, 입력 모델·런타임의 해시와 ZIP 무결성을 확인합니다. ZIP을 새 경로에 풀고 `OpsPilot-X.cmd`를 실행합니다. [작업공간과 합성 데모 시작](../portfolio/README.ko.md)
