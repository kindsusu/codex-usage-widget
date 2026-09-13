# 개발 노트 — Codex Usage Widget

제작 과정의 문제와 해결, 되돌리지 말아야 할 폐기 접근을 기록한다. 같은 실수 반복 방지용.

이 위젯은 자매 프로젝트 [claude-usage-widget](https://github.com/kindsusu/claude-usage-widget)와 시각·상호작용 계약을 공유하되, Codex의 데이터 구조·프로세스 구조에 맞춰 별도 구현했다. 아키텍처는 순수 함수 + frozen dataclass + 테스트 중심(pytest/ruff/basedpyright).

---

## 1. 데이터 소스

- 로컬 Codex의 공식 `app-server` 프로세스에 `account/rateLimits/read`를 요청. `auth.json`을 직접 읽지 않음.
- OAuth 토큰·이메일·계정 ID를 저장/로그/표시하지 않음. config에는 화면 설정(테마·투명도·배율·위치·펫)만.
- `UsageSnapshot.windows`에서 5시간 창(duration 300분)과 주간 창(10080분)을 분류해 미니 배터리 S/W로 매핑.

---

## 2. Smart topmost — 전경 감지 (핵심 버그 이력)

### 폐기: "존재 여부"로 판정
- 초기 `apply()`가 `window_layer(read_codex_running())` 사용 → **Codex 프로세스가 어디든 돌고 있으면** 무조건 topmost. 백그라운드에라도 Codex가 있으면 전경과 무관하게 **항상 위**에 뜸.

### 확정: "전경 여부"로 판정
- `should_keep_topmost(widget_focused, foreground)` 사용 — **위젯이 포커스됐거나 Codex가 실제 전경일 때만** 위로.

### ChatGPT 앱 호스트 문제 (안 올라오던 원인)
- 라이브 프로세스 추적으로 확증: `codex.exe ← ChatGPT.exe ← explorer.exe`.
- 사용자가 **ChatGPT 데스크탑 앱**에서 Codex를 실행 → 전경 창은 `ChatGPT.exe`(창 있는 Electron 껍데기), `codex.exe`는 `app\resources\` 아래의 **창 없는 자식**.
- 실제 패키지명은 `OpenAI.Codex`지만 실행파일은 `ChatGPT.exe`.
- 해결: `_CODEX_HOST_NAMES = _TERMINAL_NAMES | {"chatgpt.exe"}` — 호스트(터미널 또는 ChatGPT앱)가 전경이고 **자식에 codex 실행파일이 있을 때만** Codex 활성으로 간주. 일반 ChatGPT 채팅(codex 자식 없음)에는 반응 안 함.

### 확정: 스마트 OFF = 항상 최상위
- 스마트 OFF일 때는 전경·포커스와 무관하게 **항상 최상위 고정**(자매 클로드 위젯과 동일 계약), 전경 감지 전환은 스마트 ON일 때만 동작한다. `should_keep_topmost`/`window_layer` 둘 다 이 계약을 따른다.

---

## 3. 우클릭 메뉴 z-order (두 번의 실수)

### 문제: 메뉴가 위젯 뒤로
- 원인: `menu.tk_popup()`(Win32 `TrackPopupMenu`)은 모달이지만 그 안에서도 Tk `after` 타이머가 계속 돎. 네이티브 메뉴는 Tk grab을 등록하지 않아 `grab_current()`가 `None` → 750ms 폴이 `apply()`를 호출해 위젯을 메뉴 위로 재상승.

### 첫 수정의 부작용: 위젯이 사라짐
- `suspend()`가 위젯을 **bottom으로 내려버림** → 메뉴만 남고 위젯이 다른 창 뒤로 숨음.

### 확정 (자매 위젯 방식 이식)
- `suspend()`는 **내리지 않고 폴만 정지**(플래그).
- z-order **전이 캐싱**: 요청 레이어가 캐시와 같으면 SetWindowPos no-op → 폴이 위젯을 재상승시키지 않음. 원래 버그도 해결되면서 위젯은 제자리 유지, 메뉴가 그 위에 뜸.
- `menus.py`는 `try/finally: menu_closed()`로 어떤 경로(선택/ESC/클릭아웃)로 닫혀도 resume 보장.

---

## 4. 작업표시줄 버튼 (트레이 전용화)

- 원인: 미니모드의 `-transparentcolor` 갱신이 매 렌더마다 **`WS_EX_TOOLWINDOW`를 벗겨냄** → 시작 시 한 번 숨겨도 첫 렌더에 버튼 재출현.
- 해결: `taskbar_hidden_exstyle()`(APPWINDOW 제거·TOOLWINDOW 추가, 다른 비트 보존, 멱등)을 **`_render` 끝(transparentcolor churn 이후)** + 맵 후 ~200ms + 트레이 복원 후에 재적용.

---

## 5. 메뉴 체크버튼이 상태 반영 안 됨

- 원인: 메뉴는 팝업마다 올바른 config 값으로 재생성됐지만, `tk.BooleanVar(...)`를 인라인 생성·미참조 → **CPython GC가 즉시 수거**, Tcl 변수가 해제돼 모든 체크버튼이 해제 상태로 렌더.
- 해결: 테마/미니/스마트 var를 **이름 있는 지역변수**로 잡아 모달 `tk_popup` 동안 살려둠. 미니모드/스마트 위/다크 전환이 실제 상태대로 체크.

---

## 6. 미니 모드 배터리

- 자매 위젯에서 검증 끝난 디자인 이식: 아이폰형 배터리, 잔량(100−사용량) 표기, 잔량 ≤20% 빨강, 하드엣지 PIL 라벨(프린지 없음), 투명 키 `#fdfdfb`.
- **Codex 색상**: S(5시간) 틸 `#7fd8bb` / 라벨 라이트 `#10a37f`·다크 `#7fd8bb`, W(주간) 시안 `#8ad3e6` / 라벨 라이트 `#0e7490`·다크 `#8ad3e6`.
- 자매 위젯의 교훈(tkinter 반투명 불가, Tk 사각형 exclusive 좌표 +1 보정, ImageGrab 실측)이 그대로 적용됨.

---

## 7. 기타 결정

- **키보드 단축키 완전 제거**: Ctrl+R/M/T·Esc 바인딩과 라벨 표기 모두 삭제. 메뉴는 마우스 전용, 순 한국어 라벨(새로고침 / 다크·라이트 전환 / 미니모드 / 스마트 포지션 스위칭 / 전체·미니 배율 / 펫 선택 / 트레이로 숨기기 / 종료).
- **claudecode 펫만 제거**: 펫 시스템·나머지 30개·다시뽑기 유지. 기존 config의 `"pet": "claudecode"`는 로드 시 풀에 없으므로 자동 리롤·저장.

---

## 8. 작업 방식 교훈

- **검증은 실화면으로**: canvas bbox 근사값이 아니라 `PrintWindow(PW_RENDERFULLCONTENT)`/ImageGrab 실제 캡처로 확인 (occlusion·프린지·여백은 정적 검사로 안 잡힘).
- **근본 원인 먼저 재현**: 메뉴 z-order, 작업표시줄, 체크버튼 GC 모두 "추측 수정"이 아니라 라이브 프로세스/exstyle/변수 상태를 실측해 원인을 특정한 뒤 고침.
- **프로세스 종료는 경로로 정확히**: pythonw가 여러 개(코덱스 venv, codex-runtime 워치독, 자매 클로드 위젯, 규정봇) → 커맨드라인 전체 경로로 매칭해 엉뚱한 프로세스를 죽이지 않기.
- **디자인은 사용자 확정 후에만 변경**. 확정된 시각/동작 계약은 명시 지시 없이 건드리지 않는다.

---

## 9. 작업표시줄 메뉴 재클릭 닫기 (2026-09-14)

### 증상과 입력 순서

작업표시줄 Codex 버튼으로 열린 메뉴를 같은 버튼으로 닫을 때, 클릭 down에서 메뉴가 닫힌 뒤 mouse up이 새 메뉴를 다시 여는 경로가 있었다. 일반 클릭뿐 아니라 150ms 길게 누른 클릭과 데스크톱이 숨겨진 상태에서도 재현·검증했다.

### 확정된 처리

- nested Tk polling은 메뉴를 열기 전에 예약한다. 메뉴 상태는 팝업마다 버리지 않는 지속 객체로 관리한다.
- 닫기는 `WM_CANCELMODE`와 `EndMenu`를 함께 요청한다.
- 닫기 클릭의 held release는 한 번 소비하고, 포인터가 버튼을 벗어나면 소비 상태를 초기화한다.
- Tcl 체크 상태의 `BooleanVar`는 메뉴가 표시되는 동안 참조를 유지한다. 인라인 생성하면 GC가 Tcl 변수를 해제한다.
- 메뉴 항목 선택을 보존하려면 메뉴 객체의 destroy만 `after_idle`로 지연한다. 명령 실행 전 정리하면 표시 설정 변경이 사라질 수 있다.

### 검증과 제한

`menu-dismiss-checks.json`과 상위 `outputs/검수결과.md`에 실제 Windows 입력 결과를 보관한다. 일반 클릭·150ms held 클릭·숨긴 데스크톱·바깥 클릭·메뉴 항목 선택을 통과했고, 전체 테스트 242개·Ruff·basedpyright 오류 0을 확인했다.

일반 클릭 후 Esc 닫기는 통과했지만, 150ms held 클릭 뒤 재개방한 메뉴의 자동 Esc 입력 검사는 통과하지 않았다. 버튼 재클릭과 바깥 클릭이 그 순서에서 정상이어도 이 키보드 경로를 해결 완료로 보고하지 않는다.

### 같은 작업에서 확인한 경계

- UIA를 자기 창 스레드에서 탐색하면 self-thread deadlock으로 클릭 처리가 멈출 수 있다. 관찰 스레드에서 경계를 찾고 창 스레드에는 결과만 전달한다.
- 승인 HTML과 다른 단색 작업표시줄 결과를 막기 위해 per-pixel alpha 렌더러의 치수·팔레트를 `docs/taskbar-design.md`로 고정했다.
- 구버전 singleton이 새 사본 실행을 조용히 막던 문제는 기존 인스턴스 복원 요청과 제한된 시작 오류 분류 로그로 보완했다.

## 10. 데스크톱 카드·표시 패널 리디자인 (2026-09-14)

현재 사용자 승인 디자인은 `docs/desktop-card-design.md`가 기준이며 과거 펫/배터리형 미니의 시각 계약보다 우선한다. 저장된 표시·배율·펫 설정은 보존한다.

- 왼쪽 Codex 버튼은 세 체크 항목의 비모달 패널, 우클릭은 기존 고급 메뉴다. 두 입력 경로의 상태와 검증 결과를 구분한다.
- FocusOut에서 패널을 즉시 지우면 대기 중인 native button-up이 패널을 다시 연다. 같은 트리거의 release toggle을 먼저 처리하고, 지연 정리는 원래 창 객체에만 적용한다.
- 화면 위쪽의 데스크톱 버튼에 패널을 단순 상단 정렬하면 패널이 버튼을 덮고 재클릭이 설정 변경으로 전달된다. 데스크톱 전체 사각형을 피해서 오른쪽/왼쪽/아래/위에 배치한다.
- body drag를 버튼 위에서 놓는 것은 버튼 클릭이 아니다. 같은 버튼에서 시작한 press/release만 명령을 실행하고 body release는 위치 저장으로 전파한다.
- Tk chroma key 위에 저알파 RGBA를 바로 올리면 흰 halo가 생긴다. 내부 선·hover는 표면에 선합성하고, 텍스트는 고해상도에서 그린 뒤 축소하며, 바깥 윤곽은 binary mask로 자른다.
- 실제 Tk는 HTML backdrop blur·그림자·요소별 반투명을 구현하지 않는다. 단색 카드에 저장된 전체 창 투명도를 적용하며 이를 픽셀 단위 동일 구현으로 보고하지 않는다.

전체 테스트 264개, Ruff, basedpyright 오류 0, 실제 Windows 동작 26개를 통과했다. 세부 조건과 실제 화면은 [리디자인 검수](docs/desktop-redesign-validation.md)에 기록한다.
