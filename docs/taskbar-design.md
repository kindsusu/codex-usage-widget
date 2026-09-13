# 작업표시줄 표시 시안 계약

승인 원본은 [taskbar-widget-design.html](taskbar-widget-design.html)이다. 네이티브 렌더러는 이 문서의 기본 2행 막대형을 기준으로 하며, 바탕화면 카드·미니 스트립 계약은 [desktop-card-design.md](desktop-card-design.md)에 둔다. 구현 및 Windows 검증 결과는 [리디자인 검수](desktop-redesign-validation.md)에 기록했다.

## 크기와 배치

- 사용량 버튼: `154 × 46` logical px, 안쪽 여백은 가로 8px·세로 4px이다.
- 두 행: `31px` 라벨, `6px` 간격, 기본 `59px` 막대, `6px` 간격, `36px` 값으로 배치한다.
- 각 행의 grid 높이는 19px(`y=4..23`, `y=23..42`)이다. 라벨은 11px 보통 굵기, 백분율은 14px semibold와 tabular 숫자를 사용한다.
- 진행 막대는 높이 4px, 완전한 둥근 모서리다.
- 사용량 버튼 오른쪽에는 5px 간격과 세로 중앙 정렬한 `38 × 44` logical px Codex 버튼(`y=1`)이 있다. 따라서 기본 선호 폭은 `197 × 46` logical px이다.
- Codex 아이콘은 19px 단색이며, 오른쪽 아래에 5px 초록 상태 점을 둔다.

## 색과 투명도

Segoe UI Variable Text를 우선 사용하고 없으면 Segoe UI를 사용한다. 일반 상태는 작업표시줄 재질이 보이는 per-pixel alpha 표면이며, 별도의 불투명 사각형 배경을 그리지 않는다. 호버 때만 부드러운 반투명 배경을 표시한다.

| 토큰 | Light | Dark |
|---|---|---|
| text | `#172033` | `#f3f6fb` |
| muted | `#5e6b7d` | `#aeb8c7` |
| taskbar material | `rgba(243,247,251,.96)` | `rgba(22,29,41,.97)` |
| track | `#dfe6ef` | `#3a4558` |
| green | `#18864b` | `#47c77d` |
| amber | `#c27612` | `#e6a842` |
| hover | `rgba(27,43,68,.08)` | `rgba(255,255,255,.09)` |
| line | `rgba(36,49,70,.14)` | `rgba(231,237,247,.15)` |

## 상호작용

- 사용량 막대를 클릭하면 비모달 상세를 열거나 닫는다. 상세에는 실제 반환된 한도만, 남은 비율과 초기화 정보를 표시한다.
- 오른쪽 Codex 아이콘의 왼쪽 클릭은 [표시 설정 패널](desktop-card-design.md)을 열고, 오른쪽 클릭은 고급 네이티브 컨텍스트 메뉴를 연다.
- 정상·호버 모두 바탕화면/작업표시줄 상태 설정을 바꾸지 않는다. 작업표시줄 연결 실패 시 기존 데스크톱 fallback 정책을 따른다.
