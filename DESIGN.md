# Codex Usage Widget Design System

## 0. Research Log

- Concrete reference: `kindsusu/claude-usage-widget`의 `widget.pyw`를 시각·동작 계약으로 사용한다.
- Extracted evidence: 원본의 `THEMES`, `BAR_WIDTH`, `BAR_HEIGHT`, `PET_SIZE`, `Widget._build_ui()`, 미니 배터리 팔레트와 진행률 색상 계산을 확인했다.
- Skipped Lazyweb and Imagen: 새로운 디자인 탐색이 아니라 기존 위젯의 Codex 포팅이므로 별도 방향 탐색과 이미지 시안은 범위 밖이다.

## 1. Atmosphere & Identity

작고 조용한 데스크톱 계기판이다. 업무 흐름을 가리지 않으면서 Codex 사용량을 즉시 읽을 수 있어야 한다. 시그니처는 따뜻한 아이보리·차분한 네이비 표면과 사용량에 따라 녹색에서 노랑, 빨강으로 변하는 얇은 진행률 바, 제목 옆에서 움직이는 픽셀 펫이다.

## 2. Color

| Role | Token | Light | Dark | Usage |
|---|---|---|---|---|
| Surface/primary | `surface_primary` | `#f4f3ee` | `#1e1e2e` | 위젯 배경 |
| Text/primary | `text_primary` | `#111827` | `#cdd6f4` | 제목·사용량 |
| Text/secondary | `text_secondary` | `#6b7280` | `#7f849c` | 초기화 상세 |
| Text/muted | `text_muted` | `#9ca3af` | `#585b70` | 푸터·비활성 |
| Accent/primary | `accent_primary` | `#2563eb` | `#89b4fa` | 포커스·보조 정보 |
| Bar/background | `bar_background` | `#e5e3dc` | `#313244` | 진행률 바 바탕 |
| Control/default | `control_default` | `#9ca3af` | `#7f849c` | 헤더 컨트롤 |
| Control/hover | `control_hover` | `#111827` | `#cdd6f4` | 헤더 컨트롤 hover |
| Status/error | `status_error` | `#dc2626` | `#f38ba8` | 연결·로그인 오류 |
| Meter/low | `meter_low` | `#a6e3a1` | `#a6e3a1` | 낮은 사용량·미니 첫 행 |
| Meter/mid | `meter_mid` | `#f9e2af` | `#f9e2af` | 중간 사용량 |
| Meter/high | `meter_high` | `#f38ba8` | `#f38ba8` | 높은 사용량 |
| Meter/on-fill text | `meter_text_on_fill` | `#111827` | `#111827` | 배터리 채움 위 퍼센트 |
| Mini/secondary | `mini_secondary` | `#89b4fa` | `#89b4fa` | 미니 두 번째 행 |

진행률 색상은 0% `#a6e3a1`, 50% `#f9e2af`, 100% `#f38ba8` 사이를 선형 보간한다. 새 색상은 이 표에 먼저 추가한다.

## 3. Typography

| Level | Family | Size | Weight | Usage |
|---|---|---:|---:|---|
| Title | Segoe UI | 9pt | Bold | `Codex Plus` 제목 |
| Body | Segoe UI | 9pt | Regular | 사용량 행 |
| Detail | Segoe UI | 8pt | Regular | 초기화 시각·남은 시간 |
| Footer | Segoe UI | 7pt | Regular | 갱신·크레딧 상태 |
| Control | Segoe UI | 9–10pt | Regular/Bold | 헤더 컨트롤 |

Windows 기본 글꼴만 사용한다. 한국어는 한 글자 단독 줄바꿈이나 기준선 잘림이 없어야 한다.

## 4. Spacing & Layout

기본 단위는 2px이며 원본의 소형 위젯 밀도를 따른다.

| Token | Value | Usage |
|---|---:|---|
| `space_1` | 2px | 아이콘·펫 간격 |
| `mini_gap` | 5px | 미니 아이콘·라벨·배터리 사이 간격 |
| `space_3` | 6px | 카드 세로 여백 |
| `space_5` | 10px | 카드 가로 여백 |
| `row_gap` | 6px | 사용량 행 사이 |
| `bar_width` | 220px | 전체 모드 진행률 |
| `bar_height` | 8px | 전체 모드 진행률 |
| `pet_size` | 20px | 100% 배율 펫 |
| `control_size` | 20px | 헤더 버튼 클릭 영역 |
| `control_icon_size` | 14px | 10pt 제목과 맞춘 실제 아이콘 크기 |
| `mini_icon_size` | 14px | 배터리 높이와 맞춘 테마별 Codex 컬러 아이콘 |
| `mini_label_width` | 14px | `W`·`5h` 축약 라벨 영역 |
| `mini_battery_width` | 76px | 배터리 몸체와 단자를 포함한 폭 |
| `mini_battery_height` | 14px | 퍼센트 텍스트가 들어가는 높이 |

전체 모드는 한 열 카드이며 높이는 표시되는 한도 개수에 따라 변한다. 미니 모드는 투명 배경의 114×28 영역에서 최대 두 개 한도를 배터리 스트립으로 표시한다. DPI 배율은 1.0, 1.3, 1.5, 2.0을 지원한다.

## 5. Components

### Header Controls
- Structure: 제목, 펫, 테마, 투명도, 미니 모드, 트레이 숨김 순서다.
- States: 사용자 제공 SVG의 line 버전을 기본으로, fill 버전을 hover·active에 사용한다. 키보드 접근은 우클릭 메뉴의 동일 명령으로 보완한다.
- Motion: 펫만 의미 있는 전체 몸체 애니메이션을 수행한다.

### Usage Row
- Structure: `라벨 · 사용률`, 220×8 진행률 바, 초기화 상세의 세 요소다.
- Variants: 5시간, 주간, 서버가 제공한 기타 기간·추가 한도.
- States: loading, ready, stale, error, empty.
- Accessibility: 사용률은 색상뿐 아니라 숫자 텍스트로 항상 표시한다.

### Footer Status
- Structure: 마지막 갱신 시각, 플랜·크레딧·초기화권 또는 오류 메시지.
- States: loading, ready, retrying, login-required, unavailable.

### Mini Battery Strip
- Structure: 배경 패널 없이 14px 라이트/다크 Codex 컬러 아이콘, 영어 축약 라벨, 14px 배터리를 5px 간격으로 배치한다.
- Data label: 사용량을 뺀 잔여 퍼센트와 잔여 채움을 배터리 몸체 안에 표기하며, 채움이 중앙을 지날 때 `meter_text_on_fill`을 사용한다.
- States: normal, low-remaining, stale.
- Interaction: 더블클릭으로 전체 모드를 복원한다.

### Transparency Popover
- Structure: 현재 백분율과 원형 손잡이 슬라이더.
- States: open, dragging, closed.

## 6. Motion & Interaction

- 펫 애니메이션은 bounce, sway, float, squish, breathe 중 결정적 한 가지를 사용한다.
- 헤더 클릭과 미니 모드 전환은 즉시 반응하며 레이아웃 애니메이션을 추가하지 않는다.
- 데이터 갱신은 백그라운드에서 수행하고 Tk 메인 스레드를 차단하지 않는다.
- 드래그 중에는 창 위치만 갱신하고 마우스를 놓을 때 설정을 저장한다.

## 7. Depth & Surface

전략은 tonal-shift다. 테두리와 그림자 없이 배경, 텍스트, 바 바탕의 명도 차이로 계층을 만든다. 투명도는 전체 창에 30–100% 범위로 적용한다.

## 8. Accessibility Constraints & Accepted Debt

### Constraints

- 사용률 정보는 숫자와 색상을 함께 제공한다.
- 100%, 150%, 200% DPI에서 텍스트·펫·바가 잘리지 않아야 한다.
- 한국어 라벨은 한 글자 단독 줄바꿈 없이 한 줄에 유지한다.
- 오류는 색상 외에 구체적인 조치 문구를 표시한다.
- 백그라운드 갱신 중 창 드래그, 메뉴, 트레이 동작이 멈추지 않아야 한다.

### Accepted Debt

| Item | Location | Why accepted | Owner / Exit |
|---|---|---|---|
| 헤더 컨트롤의 직접 키보드 포커스 부재 | Tkinter 무테 창 | 원본 동작을 유지하며 우클릭 메뉴로 동일 기능 제공 | 향후 네이티브 버튼 전환 시 해소 |
