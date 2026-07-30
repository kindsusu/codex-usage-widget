# Codex Usage Widget

Codex의 현재 사용량 제한을 Windows 바탕화면에서 확인하는 작은 위젯입니다. 사용량 창은 이름이나 순서를 추측하지 않고 Codex가 실제로 반환한 기간만 표시합니다. 따라서 계정에 주간 한도만 있으면 주간 행만, 5시간 한도도 있으면 두 행이 함께 나타납니다.

## 요구사항

- Windows 10/11
- Python 3.11 이상
- Codex 데스크톱 앱 또는 Codex CLI 설치
- Codex에서 ChatGPT 계정으로 로그인된 상태

## 설치 및 실행

PowerShell에서 프로젝트 폴더를 연 뒤 다음을 실행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

이후 `실행.bat`을 더블클릭하거나 다음 명령으로 실행합니다.

```powershell
.\.venv\Scripts\pythonw.exe widget.pyw
```

## 사용법

- 헤더 아이콘: 테마, 투명도, 미니 모드, 숨기기
- 우클릭 메뉴: 새로고침, 다크/라이트 전환, 미니모드, 스마트 포지션 스위칭, 배율, 미니 배율, 펫 선택, 트레이 숨기기, 종료
- 미니 모드: 투명 배경 위에 14px 테마별 Codex 아이콘, 영어 축약 라벨(`W`, `5h`), 배터리를 5px 간격으로 표시합니다. 배터리 채움과 내부 퍼센트는 사용량을 제외한 잔여율이며, 더블클릭하면 전체 모드로 돌아갑니다.
- 위젯 이동: 빈 영역을 드래그하면 위치가 저장됩니다.

진행률 색상은 낮음(초록), 중간(노랑), 높음(분홍)으로 변하며 색상과 관계없이 정확한 백분율을 함께 표시합니다. 크레딧 또는 한도 초기화 크레딧이 반환되면 하단 상태 영역에 표시합니다.

## 문제 해결

- **Codex를 찾을 수 없음**: Codex 데스크톱 앱 또는 CLI를 설치한 뒤 다시 실행합니다. 필요하면 `CODEX_EXE` 환경변수에 `codex.exe` 전체 경로를 지정합니다.
- **로그인이 필요함**: Codex 데스크톱 앱이나 CLI에서 ChatGPT 로그인을 완료한 뒤 위젯을 새로고침합니다.
- **트레이 아이콘이 없음**: 일부 환경에서는 시스템 트레이를 사용할 수 없습니다. 위젯 자체와 우클릭 종료 메뉴는 계속 동작합니다.
- **사용량 행이 예상보다 적음**: 위젯은 서버가 반환하지 않은 5시간/주간 창을 임의로 만들지 않습니다.

## 개인정보 보호 방식

위젯은 로컬 Codex의 공식 `app-server` 프로세스에 `account/rateLimits/read`를 요청합니다. `auth.json`을 직접 읽거나 수정하지 않으며 OAuth 토큰, 이메일, 사용자 ID, 계정 ID를 저장·로그·표시하지 않습니다. 설정 파일에는 테마, 투명도, 배율, 위치, 펫 같은 화면 설정만 저장됩니다.

## 라이선스와 에셋

펫 에셋은 같은 제작자의 MIT 프로젝트 [kindsusu/claude-usage-widget](https://github.com/kindsusu/claude-usage-widget)와 공유합니다.

테마·투명도·미니 모드에는 `assets/icon`의 사용자 제공 SVG를 사용합니다. 각 SVG의 line 버전은 기본 상태, fill 버전은 hover·active 상태에 대응하며, Tk에서 그대로 표시할 수 있도록 같은 폴더의 투명 PNG로 변환합니다. 헤더 버튼 아이콘은 `Codex Plus` 10pt 제목 높이에 맞춘 14px로 표시하고 클릭 영역은 20px로 유지합니다. 트레이에는 `codex.svg`, 미니 모드에는 밝은 테마용 `codex-color.svg`와 파생된 어두운 테마용 `codex-color-dark.svg`를 사용합니다. SVG 원본은 편집 가능한 형태로 보존됩니다. 숨기기 아이콘의 fallback은 [Tabler Icons](https://github.com/tabler/tabler-icons)를 사용하며, 관련 MIT 고지는 `THIRD_PARTY_NOTICES.md`에 포함했습니다.
