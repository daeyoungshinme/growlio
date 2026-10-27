# 80. 79 병합 직후 재감사 (2026-10-27d)

## Context

계획 79(PR #163)가 main에 병합된 직후 다시 감사했다. 79의 이관 목록과 새 코드를 함께 대조했다.

브랜치 `fix/tech-debt-2026-10-27d`, 배치별 커밋.

상태: **A·B 완료, C는 사용자 확인 대기, 나머지 이관**.

## 감사 결과

- 정적 검사 0건: ruff·mypy(263 files)·tsc·eslint `--max-warnings 0`.
- 의존성 취약점 0건: npm audit, pip-audit. CI 최근 3회 성공.
- 위생 지표 0건: UTC `date.today()`/`datetime.now()`, `except Exception: pass`, TODO/FIXME, `as any`.
- 문서 드리프트 없음: CLAUDE.md의 훅·유틸·서비스·라우터 목록이 실제 파일과 일치한다. `vercel.json`은 `/api/:path*` 하나로 모든 prefix를 덮는다.
- 미병합 로컬 브랜치 0개. 병합이 끝난 worktree 4개가 남아 있다(C).
- 실버그 3건이 나왔다. 아래 A, B에서 고쳤다.

## 배치 A — ISA·연금 계좌 해외 매수 (실버그)

**문제.** 79 E는 매수 계좌가 하나일 때만 해외 대표 종목을 국내 대체 종목으로 바꿨다. 그래서 다음 경로에서 깨졌다.

1. VOO를 ISA 한 곳에서 사면 국내 대체 종목(360750)으로 바뀐다. 초기 선택 키는 `buy_360750_isa`다.
2. 일반 계좌에 "이 계좌에 매수 종목 추가"로 VOO를 더한다. 계좌가 2개가 되면 대체가 꺼진다.
3. 결과:
   - ISA 행이 다시 VOO가 된다. 증권사가 거부할 해외 매수 주문이 만들어진다.
   - 그 행의 키 `buy_VOO_isa`가 선택돼 있지 않아 체크가 풀린다.
4. 추가 드롭다운은 계좌 세제유형을 보지 않았다. 처음부터 ISA에 해외 종목을 더할 수도 있었다.
5. 백엔드 수동 실행 경로에는 이 주문을 막는 장치가 없었다. 자동 실행은 `order_builder`가 걸렀다.

**수정.**
- **A1**: 대체 여부를 계좌 세제유형만으로 판단한다(`buyRowItem`). 계좌 수는 보지 않는다.
  - 배분 합계는 대체 행 수량을 원래 종목 주수로 환산해 더한다(`qtyInOriginalUnits`). 79가 대체를 끈 이유였던 단위 섞임을 이렇게 푼다.
  - 대체 행의 배분 표시에는 "(VOO 기준)"을 붙인다.
- **A2**: `canBuyInAccount`를 추가했다. "이 계좌에 매수 종목 추가" 후보(`getAddableBuyItems`)와 기본 매수 계좌 선택이 이 함수를 쓴다. 절세 계좌에서 대체 종목이 없는 해외 종목은 후보에서 빠지고, 기본 계좌는 살 수 있는 첫 계좌로 잡힌다.
- **A3**: `ADD_BUY_ACCOUNT`·`REMOVE_BUY_ACCOUNT`에 `rowTicker`(실제로 사는 종목)를 넣었다. 수량·선택 키가 이 종목 기준으로 맞춰진다.
- **A4**: 백엔드 수동 실행(`_execute_account_group`)에서 절세 계좌의 해외 매수를 증권사로 보내지 않는다. 대신 안내 문구와 함께 SKIPPED로 남긴다.
  - 계획 단계에서는 422로 막으려 했다. 하지만 SKIPPED로 바꿨다. 같은 계좌의 다른 주문(국내 대체 등)은 그대로 나가야 하기 때문이다.
- **A4 부수**: `tax_service`·`isa_service`에 중복 정의돼 있던 `_OVERSEAS_MARKETS`를 `app.constants.OVERSEAS_MARKETS`로 올렸다. 다른 모듈 2곳이 private import하던 것도 함께 정리했다.

**회귀 테스트.**
- 훅 테스트 4건: 계좌 추가, 계좌 제거, 추가 후보, 기본 계좌. 수정 전 코드에서 3건이 실패하는 것을 확인했다.
- 유틸 테스트 2건을 추가했다.
- 백엔드 테스트 3건: ISA 해외 SKIPPED·국내 실행, 일반 계좌 통과, 연금 매도는 막지 않음.

## 배치 B — 알림 병합값 오용 (실버그) + 테스트 공백

**문제.** `mergeAlertsByPortfolio`는 `mode`만 "AUTO가 하나라도 있으면 AUTO"로 합친다. 나머지 필드는 첫 행 값을 그대로 남긴다. 계좌별 알림이 여러 개이고 첫 행이 다른 계좌의 NOTIFY·FULL이면 두 곳이 틀렸다.

- **B1** `useDcaTacticalLink`: 적립식 자동매수(AUTO·BUY_ONLY)를 놓쳐 전술 탭 안내가 틀렸다.
  - 이제 행 단위로 판정한다.
  - 적립식 자동매수가 모두 TACTICAL일 때만 "연동됨"으로 본다.
- **B2** `useAutoExecutionNotice`: 안내 문구의 자동 실행 시각이 빠졌다. 이제 활성 AUTO 행에서 시각을 읽는다.

**테스트.**
- 수정 전 코드에서 실패하는 회귀 테스트를 각각 추가했다.
- 직접 테스트가 없던 `useDcaTacticalLink`·`useSyncAccounts`에 테스트를 추가했다.

**제외한 항목.**
- 백엔드 `goal_feasibility`·`market_signal_scoring`: 1차 grep에서는 테스트가 없어 보였다. 실제로는 API 테스트와 서비스 재노출을 통해 이미 테스트되고 있어 제외했다.
- `useRebalancingUrlState`: 이미 테스트된 `rebalancingUrl` 유틸을 얇게 감싼 훅이라 제외했다.
- 남은 `mergeAlertsByPortfolio` 사용처(`AutoInvestStatusBanner`의 `account_id` 등): 표시용 첫 행 값이라 영향이 작아 그대로 둔다.

## 배치 C — worktree 정리 (사용자 확인 대기)

병합된 worktree 4개가 남아 있다. 넷 다 미커밋 변경과 미병합 커밋이 없다.

| 경로 | 브랜치 |
|---|---|
| `growlio-goal` | `feat/nestlio-external-api` |
| `growlio-mobile-67` | `feat/mobile-usability-2026-10-23` |
| `growlio-mobile-ux` | `feat/mobile-ux-2026-10-14` |
| `growlio-wt` | `feat/external-nestlio-goal-api` |

다른 세션이 쓰고 있을 수 있어 사용자 확인 뒤 `git worktree remove`로 지운다.

## 이관 (외부 조건 대기)

| 항목 | 막힌 이유 | 풀리는 조건 |
|---|---|---|
| `untracked_holdings` 백엔드 필드 제거 | 구버전 APK가 필드 없으면 크래시. Android APK 빌드는 2026-05-25 실패가 마지막 | `build-android.yml` 수동 실행 성공 → 재배포 |
| 65 B4 대안·66 P3 예열 | 실측 로그 없음, Render 슬립 | 운영 `goal_recommendation_timing` 확인, 상시 기동 |
| 67 바텀시트·InfoTip, 79 F 실기기 확인 | 실기기 필요 | 사용자 확인 |
| 100줄 넘는 함수 15개(`tactical_backtest.simulate` 157줄 등), 600줄 넘는 파일 3개 | 동작 불변 리팩터라 위험 대비 이득이 작음 | 해당 함수를 기능 수정할 때 함께 |
| ORM `getattr` 기본값 잔여 | 대부분 덕타이핑·스키마 객체 대상 | 관련 함수를 수정할 때 |
| 메이저 업그레이드(react 19·recharts 3·tailwind 4·TS 7·plugin-react 6) | 범위가 큼 | 별도 계획 |

## 검증

- 백엔드: ruff·format·mypy 클린. `pytest --cov` 3050 passed, 91.79%.
- 프론트: tsc·eslint(`--max-warnings 0`)·prettier 클린. `vitest --coverage` 1849 passed.

## 배포 후 확인

- 실기기 또는 개발 서버에서 확인한다.
  1. 지수 그룹 포트폴리오의 실행 화면을 연다.
  2. ISA 계좌 매수 행이 국내 대체 종목인지 본다.
  3. 일반 계좌를 추가하거나 뺀다. 그때 행 티커·체크 상태·"배분 x / y주 (VOO 기준)" 표시가 맞는지 본다.
