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

- **키보드 단축키 완전 제거**: Ctrl+R/M/T·Esc 바인딩과 라벨 표기 모두 삭제. 메뉴는 마우스 전용, 순 한국어 라벨(새로고침 / 다크·라이트 전환 / 미니모드 / 스마트 위 / 전체·미니 배율 / 펫 선택 / 트레이로 숨기기 / 종료).
- **claudecode 펫만 제거**: 펫 시스템·나머지 30개·다시뽑기 유지. 기존 config의 `"pet": "claudecode"`는 로드 시 풀에 없으므로 자동 리롤·저장.

---

## 8. 작업 방식 교훈

- **검증은 실화면으로**: canvas bbox 근사값이 아니라 `PrintWindow(PW_RENDERFULLCONTENT)`/ImageGrab 실제 캡처로 확인 (occlusion·프린지·여백은 정적 검사로 안 잡힘).
- **근본 원인 먼저 재현**: 메뉴 z-order, 작업표시줄, 체크버튼 GC 모두 "추측 수정"이 아니라 라이브 프로세스/exstyle/변수 상태를 실측해 원인을 특정한 뒤 고침.
- **프로세스 종료는 경로로 정확히**: pythonw가 여러 개(코덱스 venv, codex-runtime 워치독, 자매 클로드 위젯, 규정봇) → 커맨드라인 전체 경로로 매칭해 엉뚱한 프로세스를 죽이지 않기.
- **디자인은 사용자 확정 후에만 변경**. 확정된 시각/동작 계약은 명시 지시 없이 건드리지 않는다.
