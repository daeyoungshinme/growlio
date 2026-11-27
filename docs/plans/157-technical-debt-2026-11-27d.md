# 157. 기술부채 감사 — 156 A~F + Dependabot 머지분 (2026-11-27)

상태: A1~A3·B1 구현, C(133 운영 보정) 적용, 마이그레이션 없음. 브랜치 `fix/157-tech-debt`, PR #340.

## Context
- 155 이후 main에 들어온 변경: 계획156 A~E(#330~#333)·F 해외 매매 거래일 환율(#339), Dependabot sentry-sdk 3.0(#338, 48ab914e에서 `data_collection`으로 이관)·프론트 deps 그룹·gradle 2건·uv 0.13.10.
- `git diff bf78ccce..HEAD`의 백엔드·프론트 소스를 직접 읽었다. 의심 경로는 설치된 `sentry_sdk` 3.0 소스까지 따라가 확인했다. 아래 4건은 모두 재현 경로를 코드로 확인했다.
- 156의 오탐(`_retry_provider_sync` docstring, 삭제 rate limit, TransactionModal 은행 계좌, websockets, formatManwon)은 다시 올리지 않았다.

## A. 백엔드

**A1 Sentry 3.0이 KIS 요청 URL의 계좌번호를 수집한다** — `app/main.py`
- 3.0의 `data_collection.url_query_params` 기본값은 `denylist`다. 거르는 단어(auth·token·key·secret…)에 `CANO`·`ACNT_PRDT_CD`가 없다. httpx 통합은 이 필터를 거친 `url.full`·`http.query`를 **모든 이벤트에 붙는 breadcrumb**과 span(traces 0.1)에 넣는다. 156 A4로 로그에서는 지웠지만 Sentry로는 그대로 나갔다. 기본 설정으로 `CANO=12345678&...`이 그대로 통과하는 것을 직접 확인했다.
- 수정: 설정을 `app/core/sentry_options.py` `SENTRY_DATA_COLLECTION`으로 옮기고 `"url_query_params": {"mode": "off"}`를 추가했다. 헤더(appkey·appsecret·authorization)는 기본 denylist에 걸려 그대로 둔다.
- 테스트 `tests/test_sentry_options.py`: SDK가 키를 그대로 받는지(메이저에서 키 이름이 바뀌면 조용히 기본값=수집으로 돌아간다), KIS 쿼리가 버려지는지, 기본값이 여전히 새는지(전제 확인).

**A2 동기화 중 삭제된 계좌가 있으면 "전체 갱신" 진행률이 멈춘다** — `services/accounts/sync_all_service.py`
- 156 A1의 비활성 계좌 `return`이 `try` 안에 있어 아래 `on_progress` 갱신을 건너뛰었다. 진행 상태가 `N-1/N`에 머물다가 끝에서야 `done`이 됐다.
- 수정: `return` 대신 `else` 분기로 흐름을 바꿨다. 기존 `test_rereads_account_and_skips_deleted_one`에 진행률 단언(`(2, 2, 0)`)을 추가했다.

**A3 최근 날짜 환율을 미확정 값으로 7일 캐시한다** — `services/market_data/fx_history.py`
- `USDKRW=X` 일봉 날짜는 KST와 어긋난다. KST 새벽에 "어제"를 조회하면 그 일봉은 아직 장중이고, Yahoo가 하루 늦으면 전날 종가가 그날 값으로 온다. 어느 쪽이든 7일 동안 굳는다.
- 수정: KST 오늘 기준 4일 이상 지난 날짜만 `TTL_USD_KRW_ON_DATE`(7일)로 캐시하고, 그보다 최근이면 `TTL_USD_KRW_ON_DATE_RECENT`(1시간)로 캐시한다. 처음 계획한 "`rate_day < day`면 짧게"는 넣지 않았다. 오래된 날짜에서는 주말이면 늘 참이라 의미가 없고, 최근 날짜는 기간 규칙이 이미 덮는다.
- 테스트: 1·3·4일 전의 TTL을 parametrize로 확인한다.

## B. 프론트

**B1 거래일 환율 조회 실패가 세션 내내 고정된다** — `hooks/useTradeDateUsdRate.ts`
- 백엔드는 실패를 캐시하지 않는다(`usd_krw=null`). 그런데 훅이 `staleTime: Infinity`라 null 응답이 그 날짜의 결과로 남았다. 그래서 모달을 다시 열어도 재조회하지 않고 현재 환율로 저장됐다. persist 대상이 아니라서 새로고침하면 풀린다.
- 수정: `staleTime: (q) => (q.state.data?.usd_krw ? Infinity : 0)`. 테스트 `__tests__/hooks.useTradeDateUsdRate.test.tsx`는 같은 QueryClient에서 두 번 마운트한다. null이면 2회, 값이 있으면 1회 조회해야 한다.
- 기기 날짜와 KST: `isPast`는 기기 날짜를 쓰고 백엔드는 KST 오늘 이후를 400으로 거절한다. 그래서 KST보다 늦은 시간대에서는 "어제"가 폴백(현재 환율 + 안내)으로 끝난다. 저장값이 안전해 주석만 남겼다.

## C. 계획 133 스냅샷 운영 보정 (사용자 요청, 2026-11-27)
- 운영 DB에 `scripts/fix_manual_usd_double_count_133.py` dry-run을 돌렸다. 후보는 수기 해외 계좌 1개의 14행(11/2~11/15)이고, 스크립트 판정은 OK 8행·`ALREADY_OK?` 6행이었다.
- 행마다 스냅샷 포지션 합계로 검증해 보니 스크립트의 전제가 틀렸다. 이 계좌는 입출금 기록이 없고 현금으로 매수하므로, 정상일에는 **현금(금액−포지션) + 투자원금**이 1.62억~1.65억 원으로 거의 일정하다. 이 기준으로 과다인 날은 6일(11/2·3·4·11·12·14)이고, 과다분은 530만~2,023만 원으로 날마다 달랐다. 스크립트 보정액은 456만 원으로 고정돼 있다. 스크립트가 OK로 고른 11/5·13은 정상이었다(보정하면 오히려 틀린다).
- 적용: 6행의 `amount_krw`를 앞뒤 정상일(10/31·11/5·11/10·11/13·11/15) 합계를 날짜로 선형 보간한 기준선에 맞춰 낮췄다. 한 트랜잭션에서 처리했고, 각 행은 값이 미리보기 때와 같을 때만 바뀌게 했다. 보정 뒤 현금은 매수에 따라 단조 감소한다(8,929만→8,402만→…→6,772만).
- 일회성 스크립트와 `test_real_db_upserts.py`의 해당 테스트는 삭제했다(135 계획대로). 서버 캐시는 프로세스 로컬이라 대시보드·추이는 TTL이 지나거나 계좌를 동기화하면 반영된다.

## 범위에서 뺀 것
- `get_or_fetch_token`의 `force_refresh`(401 재발급) 경로는 single-flight 밖이다. 캐시 키가 계좌별이라 같은 키에서 동시에 401이 나는 경우가 드물다. remaining-tasks "의도적으로 남긴 것"에 적었다.
- 월간 리포트 `_confirm_claim`이 2회 실패했을 때의 재발송 여지는 156 A6에서 받아들인 선택이라 유지한다.
- Dependabot 프론트 그룹(마이너·패치)과 gradle·uv는 CI가 통과했고, 코드 영향을 받는 API 변경은 없다.

## 검증
- 백엔드: ruff check·format, mypy 통과. `pytest --cov=app` 4338 passed, 커버리지 93.99%(게이트 91%).
- 프론트: typecheck·eslint·prettier 통과. vitest 221 files / 2321 tests passed.
