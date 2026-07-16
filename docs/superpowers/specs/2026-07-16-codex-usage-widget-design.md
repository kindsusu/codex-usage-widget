# Codex Usage Widget 설계 명세

## 목표

`kindsusu/claude-usage-widget`의 Windows 사용 경험을 유지하면서 현재 로그인된 Codex 계정의 실제 사용량을 표시한다.

## 데이터 계약

- 설치된 Codex 실행 파일을 찾아 `app-server --stdio`로 실행한다.
- JSONL RPC 순서는 `initialize` → `account/rateLimits/read`다.
- `rateLimitsByLimitId`가 있으면 이를 우선 사용하고, 없으면 `rateLimits`를 사용한다.
- 각 `primary`·`secondary`는 `usedPercent`, `windowDurationMins`, `resetsAt`으로 정규화한다.
- 300분은 `5시간 한도`, 10,080분은 `주간 한도`, 그 외는 분·시간·일 단위 동적 라벨을 사용한다.
- 존재하지 않는 window는 0% 행으로 만들지 않는다.
- 인증 토큰, 이메일, account ID를 읽거나 출력하거나 로그에 저장하지 않는다.

## 기능 계약

- 라이트·다크 테마, 30–100% 투명도, 미니 모드, 트레이 숨김·복원, 드래그 위치 저장, 단일 인스턴스, DPI 배율, 픽셀 펫을 제공한다.
- Codex 또는 위젯이 전경일 때만 항상 위로 올라오는 smart top-most를 기본값으로 사용한다.
- 180초마다 갱신하며 수동 새로고침을 제공한다.
- 갱신은 UI 스레드 밖에서 수행한다.
- 실패 후에는 마지막 성공값을 유지하되 푸터에 `업데이트 지연` 상태와 오류 조치를 표시한다.
- 종료 시 트레이와 app-server subprocess가 남지 않아야 한다.

## 범위 제외

- 크레딧 구매, 초기화권 사용, 로그인 자동화 같은 계정 변경 작업
- API 키 기반 OpenAI Platform 비용·사용량
- macOS·Linux 네이티브 지원
- 설치 파일·배포·자동 시작 등록

## 완료 기준

- 실제 Codex 계정 사용량이 화면에 표시된다.
- 현재 주간-only 응답과 과거 5시간+주간 응답을 모두 파싱한다.
- 자동 테스트, 타입 검사, 린트가 통과한다.
- 전체·미니·다크·라이트·투명도·트레이·smart top-most가 Windows에서 직접 검증된다.
- fresh 화면 캡처를 독립 검수 에이전트가 차단 이슈 없이 승인한다.

