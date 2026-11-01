# 107. 기술부채 — 104~106 머지 직후 재점검 (2026-11-01)

## 배경

104~106이 main에 머지된 직후(PR #206) 백엔드·프론트·인프라를 3갈래로 다시 훑었다. 105 이관분 중 남은 건 "판단 필요/그대로 둠"뿐이었다.

- **실버그 1건 (인프라)**: Dependabot #205가 `docker-compose.yml` db를 `postgres:16-alpine` → `18-alpine`으로 올렸다. 18 이미지는 볼륨을 `/var/lib/postgresql`에 두길 기대하는데 마운트는 그대로 `/var/lib/postgresql/data`였고, 기존 볼륨도 16 데이터라 `make up`이 깨진다. CI 서비스 이미지는 16에 머물러 로컬과도 갈라졌다(Dependabot은 워크플로 서비스 이미지를 추적하지 않음).
- 나머지는 모두 정리 작업이다.
  - 105 분리 작업의 잔여물: 외부에서 쓰지 않는 재노출, 테스트에서만 쓰는 래퍼, stale 주석
  - 라우터에 남은 로직
  - 102·106에서 만든 공용 패턴(탭 상수·ModalBody·SegmentedControl·ToggleRow)이 일부 화면에만 적용됨

사용자는 두 가지를 결정했다. Postgres는 **16으로 되돌리고**, 범위는 **A+B+C 전부**로 한다.

## 결과

| 항목 | 커밋 | 내용 |
|---|---|---|
| A | `661823cd` | compose를 postgres 16으로 되돌리고, Dependabot docker-compose에 postgres major 무시 규칙과 잘못된 주석 정정을 넣었다. Dependabot `gradle`(`/frontend/android`, major 무시)을 신설하고 `ci.yml` 서비스 이미지에 주석을 달았다 |
| B1~B4 | `004dc971` | 전술 재노출 6개를 제거하고 private은 `__all__`에서 뺐다. `tactical_backtest`는 `tactical_regime`에서 직접 import한다. 테스트 전용 `_calc_stock_unrealized`를 삭제했고(테스트는 `_stock_unrealized_from_rows`를 직접 호출), stale 주석 4곳을 고쳤다 |
| B5·B6 | `164ee7ce` | `advance_strategy`가 국면·틸트·웅덩이 갱신 3벌(조회·설정 저장·job)을 대신한다. `get_owned_portfolio`는 이제 `NotFoundError`를 던진다(라우터 `_portfolio_or_404` 삭제). `group_suggestions_for`와 `crud.delete_portfolio`를 서비스로 옮겼다 |
| C1 | `7f5a25b6` | `utils/tabUrl.ts` 빌더 4종을 만들어 하드코딩 딥링크 19곳을 치환했다. `MARKET_ALERT_SECTION`을 `constants/tabs.ts`로 옮겼고, 탭 fallback 6곳을 `X_TABS[0]`으로 바꿨다 |
| C2 | `b0f715f8` | SegmentedControl 4곳(시장가/지정가·매수/매도·KRW/USD×2), ModalBody 13곳(`padding` prop 신설로 기존 여백 유지), ToggleRow 2곳 |
| C3·C4 | `be837bdd` | `dashboardQuery`를 만들어 프리페치에 staleTime이 빠져 있던 문제를 고쳤다. `taxSummaryQuery`로 정의 2벌을 통합했고, 106 C1의 죽은 테스트 목과 주석을 지웠다 |
| C5 | `e724b3df` | minor·patch 업데이트 5종 |

### 계획과 달라진 것

- **B7(backend/CLAUDE.md email_templates 목록 누락)**: 스캐너 오탐이었다. 이미 목록에 있었다.
- **B6 포트폴리오 삭제**: 캐시 무효화는 create·update와 맞춰 라우터에 남겼다.
- **B5**: `get_owned_or_404`로 통일하는 대신 서비스 `get_owned_portfolio`가 `NotFoundError`를 던지게 했다. 테스트 patch 대상(`tactical.get_owned_portfolio`)을 유지하기 위해서다.
- **C1**: 빌더는 값을 인코딩하지 않는다. 백엔드·이메일 링크와 같은 모양을 유지하기 위해서다. 원래 `encodeURIComponent`를 쓰던 곳은 푸시 딥링크뿐이었다.
- **C2에서 손대지 않은 것**
  - 실행 주기는 보기가 6개라 택일 토글이 아니다.
  - 내역 유형·기간 단위는 필터 칩 패턴이다.
- **C4**: 환율 알림 설정은 `useAlertCrud` 제네릭 훅이 키와 fn을 직접 받는 구조라 그대로 뒀다.
- **C5**: `@capacitor/*` 8.6은 `cap sync`와 Android 빌드 확인이 필요해 제외했다.

## 검증

- 백엔드
  - 3226 tests 통과, 커버리지 92.82%. ruff·mypy clean.
  - `/openapi.json`이 전후 바이트 단위로 같다.
  - `group_suggestions_for`·`get_owned_portfolio` 서비스 테스트 3건을 추가했다.
- 프론트
  - 1966 tests 통과. typecheck(앱+테스트)·`eslint --max-warnings 0` clean, `npm run build` 성공.
  - `utils.tabUrl.test.ts`로 기존 링크 문자열을 고정했다.
- 인프라: Docker가 없는 환경이라 `docker compose config`와 `make up`은 **미실행**. YAML 문법은 pre-commit yaml 검사로 확인했다.

## 이관

- **사용자 확인 필요**: 운영 Supabase의 Postgres 버전(`SELECT version()`)을 확인한 뒤, 그 major에 docker-compose와 CI를 맞춘다.
- `npm audit` dev 의존성 moderate 23건: vite-plugin-pwa → workbox-build → `@trickfilm400/rollup-plugin-off-main-thread` → ejs/jake 체인이다. 갱신 전후 개수가 같고, CI 게이트(high)는 통과한다. vite-plugin-pwa 상위 버전이 나올 때 함께 처리한다.
- `@capacitor/*` 8.6: cap sync와 Android 빌드 확인을 함께 해야 한다.
- 그대로 두는 것: 총자산 엔진 2벌, OTHER 시장 세무 기준, 메이저 업그레이드(react 19·recharts 3·tailwind 4·TS 7), 106 실기기 확인
- 로컬 브랜치 16개는 전부 main에 머지돼 있다. 삭제는 사용자가 한다.
