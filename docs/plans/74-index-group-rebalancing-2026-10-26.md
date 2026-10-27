> 상태: **구현 완료(미커밋)·마이그레이션 `ig1_portfolio_item_groups` 공유 Supabase 적용 완료(2026-10-26, `alembic check` 일치)** (2026-10-26). 계획서의 파일:라인은 작성 시점 기준 — 실행 시 현재 코드 우선. 하단 "구현 결과" 참고.

# 지수 그룹 단위 리밸런싱 (plans/74)

## Context
리밸런싱 목표가 지금은 `(ticker, market, weight)` 행 단위라, 같은 지수를 여러 종목으로 들고 있으면 계산이 틀어진다. 예를 들어 목표가 `VOO 40%`인데 S&P500을 VOO, SPY, TIGER 미국S&P500으로 나눠 보유하면 이렇게 된다.
- VOO는 비중 미달로 잡혀 매수가 나간다.
- SPY와 TIGER는 목표에 없는 종목(`_build_untracked_items`)이라 **전량 매도** 대상이 된다.

원하는 결과는 "S&P500 40%"처럼 **지수 그룹 단위로 목표를 잡고**, 이탈 판단도 그룹 합계로 하고, 실제 주문만 구체적인 종목으로 바꾸는 것이다. 종목 단위 항목과 그룹 항목은 한 포트폴리오에 섞어 쓸 수 있다.

사용자가 정한 내용:
- **그룹 구성:** 분류기가 자동으로 제안하고, 사용자가 확정한 멤버를 DB에 저장한다. AUTO 실행 때는 분류하지 않는다(네트워크 불필요, 결과가 항상 같음).
- **매수:** 그룹의 대표 매수 종목으로 산다. 매수 계좌가 ISA·연금저축·IRP이고 대표 종목이 해외 상장이면, 국내 상장 대체 종목으로 자동 전환한다.
- **매도:** 대표가 아닌 멤버부터 판다(한 종목으로 정리되는 방향). 계좌 간 순서는 지금처럼 일반계좌 먼저, 절세계좌 나중이다(`_build_sell_orders`).

## 설계 핵심: 그룹 항목 = 대표 종목 행 + 그룹 메타
`PortfolioItem` 행 하나가 그룹 하나를 나타낸다. **`ticker`/`market`에는 대표 매수 종목을 넣는다.** 이렇게 하면 종목 단위로 동작하는 기존 소비처(배당·수익률·expected-metrics·factor·optimizer·overview_enrichment)가 대표 종목을 기준값(proxy)으로 써서 수정 없이 계속 돈다. 그룹 여부는 `group_key IS NOT NULL`로 판별한다.

### P0. 모델·스키마·CRUD
- `backend/app/models/portfolio.py`
  - `PortfolioItem`에 `group_key String(64) null`(예: `US_SP500`, `RAW:...`)과 `group_label String(50) null`을 추가한다.
  - 새 모델 `PortfolioItemMember`(테이블 `portfolio_item_members`)를 만든다. 컬럼은 `id`, `portfolio_item_id` FK(CASCADE), `ticker`, `market`, `name`, `role`(`MEMBER` | `DOMESTIC_ALT`)이다.
  - `(portfolio_item_id, ticker, market)`에 unique를 건다. 제약·인덱스는 `__table_args__`에도 선언한다.
  - `items` 관계에서 members를 selectinload로 함께 읽는다.
- alembic: 작업 시점의 `alembic heads`를 down_revision으로 쓰고, `alembic/env.py`에 새 모델 import를 추가한다.
- `backend/app/schemas/portfolio.py`: `PortfolioItem`에 `group: PortfolioItemGroup | None`을 추가한다(`key`, `label`, `members[]`, `domestic_alt | None`).
- 검증은 `schemas/_validators.py`의 `validate_portfolio_weights` 옆에 추가한다.
  - 같은 `(ticker, market)`가 여러 그룹에 들어가거나, 그룹 멤버이면서 단독 항목으로도 있으면 안 된다.
  - `domestic_alt`는 `DOMESTIC_MARKETS`(`app/constants.py`)에 속하는 종목이어야 한다.
  - 대표 종목은 멤버 목록에 자동으로 포함한다.
- `backend/app/api/v1/portfolios.py`의 POST(`:114`)와 PUT(`:184`)에서 member 행을 만들고 응답에 직렬화한다.
- **가드:** 전술 배분이 켜진 포트폴리오(`tactical_allocation_service.is_tactical_managed`)에 그룹 항목이 있으면 422를 낸다. `apply_regime_to_portfolio`가 항목을 통째로 지우기 때문이다.

### P1. 분석: 그룹 합산 (`backend/app/services/rebalancing/service.py`)
- `_build_target_items`(`:117`)에서 항목이 그룹이면, 대표 종목과 모든 멤버 키의 `current_map` 값·수량을 합쳐 그룹 행 하나(`RebalancingItem`)를 만든다. 멤버 키는 전부 `target_keys`에 넣어 `_build_untracked_items`가 전량 매도로 잡지 않게 한다.
- `RebalancingItem`(`schemas/rebalancing/analysis.py:19`)에 필드를 추가한다.
  - `group_key`, `group_label`
  - `members: list[RebalancingItem]`: 종목별 현재 가치·수량, 그리고 아래 P2 전개 결과인 매매 수량
- 그룹 행의 `shares_to_trade`/`target_qty`는 `None`이다. 수량은 `members`에만 둔다. `filter_drifting_items`(`:485`)는 그룹 행의 `weight_diff_pct`로 판정하므로 이탈 규칙은 하나로 유지된다.
- 배당은 멤버별 `_div_info`를 더해서 계산한다. CAGR은 대표 종목 값을 쓴다(proxy).

### P2. 주문 전개 (새 모듈 `backend/app/services/rebalancing/group_expansion.py`, 순수 함수)
- `expand_group_items(items, buy_account_tax_type) -> list[RebalancingItem]`는 그룹 행을 종목 단위 매매 행으로 펼치고, 그룹이 아닌 행은 그대로 둔다.
  - **매수(diff > 0):** 대표 종목 행의 `target_value_krw`를 현재 가치 + diff로 잡는다. 단, `buy_account_tax_type`이 ISA/PENSION_SAVINGS/IRP이고 대표 종목이 해외이며 `domestic_alt`가 있으면 대체 종목으로 산다. 대체 종목이 없으면 기존 order_builder의 해외 스킵(`order_builder.py:357`)에 맡긴다.
  - **매도(diff < 0):** 대표가 아닌 멤버를 현재 가치가 작은 것부터 전량 정리하고, 남은 금액은 대표 종목에서 판다. 멤버마다 `target_value_krw = 현재 - 매도액`으로 둔다.
  - 이렇게 하면 `refresh_live_prices`(`order_builder.py:88`)가 `floor(target_value/price) - qty`로 다시 계산해도 같은 결과가 나온다.
- 호출 위치:
  - `plan_generation.build_pending_plan_for_alert`(`:343` 이후)에서 `filter_drifting_items` 다음, `refresh_live_prices` 전에 호출한다. 매수 계좌 tax_type은 `alert.account_id` 계좌에서 가져온다. quick-execute도 이 함수를 거치므로 자동으로 적용된다.
  - `analyze_rebalancing`에서는 UI 표시용 `members` 수량을 채우는 데 쓴다. 이때 기준은 대표 종목으로 산다고 가정한 값이다.
- `jobs/dca_cash_shortfall.py:77`의 해외 여부 판정은 실제 매수될 종목(대체 종목 반영)의 market으로 판단하도록 바꾼다.

### P3. 그룹 제안 API
- `GET /portfolios/index-group-suggestions?account_ids=`
  - 보유 종목 쪽은 `index_exposure_service.get_index_exposure()`(`:121`)를 재사용한다. INDEX 종류의 그룹과 멤버 목록이 그대로 그룹 후보가 된다. 레버리지·커버드콜은 별도 키라 자연스럽게 분리된다.
  - 대표·대체 종목 후보는 `recommendation_universe.RECOMMENDATION_UNIVERSE`에서 같은 `tracking_index`를 가진 해외 종목과 국내 종목을 찾는다. 제안 순서는 보유 금액이 가장 큰 종목 → 유니버스 순이다.
- 응답 스키마는 `schemas/portfolio.py`에 추가한다. 이 엔드포인트는 제안만 하고 저장하지 않는다.

### P4. 프론트엔드
- `frontend/src/api/portfolios.ts`: `PortfolioItem.group` 타입과 `fetchIndexGroupSuggestions`를 추가한다.
- 편집기(`components/portfolio-analysis/UnifiedPortfolioEditor.tsx`, `hooks/usePortfolioItemsEditor.ts`, `PortfolioItemRow.tsx`)
  - "지수로 묶기" 버튼으로 제안 시트를 연다. 그룹을 고르면 그 지수의 개별 종목 행들이 그룹 행 하나로 합쳐지고, 비중도 합산된다.
  - 그룹 행은 라벨, 대표 종목, 국내 대체 종목, 멤버 칩(추가·제거)으로 구성된다.
  - "그룹 해제"를 누르면 대표 종목 행 하나로 되돌린다.
- 분석 화면(`RebalancingWeightTable.tsx`, `RebalancingTable`)에서는 그룹 행을 펼쳐 멤버별 현재 가치와 매매 수량을 보여준다.
- 주문(`RebalancingOrderTable`, `RebalancingExecutionModal`, `utils/rebalancingTradeMath.ts`)은 그룹 행 대신 `members`로 평탄화해 주문을 만든다(`isTradableItem`, `calcTradeSummary`).
- 추천 적용과 이탈 비교(`RecommendationCard.tsx` applyMutation, `utils/recommendationDrift.ts`, 백엔드 `compute_recommendation_drift`)
  - 추천 종목이 기존 그룹의 멤버면 그 그룹 비중으로 합산하고, 그룹은 보존한다. 지금처럼 전체를 덮어쓰면 그룹이 사라지기 때문이다.
  - 프론트와 백엔드 로직은 같이 맞춘다(backend/CLAUDE.md 규약).

### P5. 문서
- `docs/plans/74-index-group-rebalancing-2026-10-26.md`를 작성하고 `docs/plans/README.md` 인덱스에 추가한다.
- `backend/CLAUDE.md`(services 목록에 `group_expansion.py`, portfolios 라우터 설명)와 `frontend/CLAUDE.md`(새 API·유틸)를 갱신한다.

## 재사용
- `etf_index_classifier.classify_holding`, `INDEX_LABELS`, `index_label`
- `index_exposure_service.get_index_exposure`
- `recommendation_universe.RECOMMENDATION_UNIVERSE` / `resolve_tracking_index`
- `order_builder._build_sell_orders`(계좌 간 매도 순서), `refresh_live_prices`, `filter_drifting_items`
- `app/constants.DOMESTIC_MARKETS`

## 범위 밖
- 그룹 안에서 멤버별 목표 비중(그룹 안 비율 고정)은 다루지 않는다.
- 개별 주식을 지수에 편입하는 것(look-through)은 다루지 않는다.
- 전술 배분 포트폴리오에는 그룹을 쓸 수 없다(P0 가드). → **plans/76에서 대체**: 전술 QQQ·SPY·DIA가 지수 그룹 비중이 되어 그룹 포트폴리오도 전술로 관리한다.

## 검증
- **백엔드 단위 테스트**(`backend/tests/`)
  - `test_group_expansion.py`: 매수가 대표 종목으로 가는지, ISA에서 대체 종목으로 바뀌는지, 대체 종목이 없을 때 스킵되는지, 매도가 비대표 멤버의 작은 것부터 나가는지, 매도액이 대표 종목까지 넘치는 경우를 확인한다.
  - `analyze_rebalancing` 그룹 테스트: VOO·SPY·TIGER를 보유하고 목표가 S&P500 40%일 때 untracked 전량 매도가 없고 그룹 합계로 이탈을 판정하는지 확인한다.
  - plan_generation 통합 테스트: leg가 종목 단위로 만들어지는지 확인한다.
  - 스키마 검증(중복 멤버, 해외 대체 종목) 422를 확인한다.
- `make lint`, `make typecheck`, `make test-backend-cov`(80%)
- `make test-frontend`: 편집기에서 그룹으로 묶고 해제하는 동작, 주문 평탄화 테스트
- 수동: `make dev` → 리밸런싱 > 포트폴리오에서 지수로 묶기 → 저장 → 분석 화면에서 그룹 행 펼치기 → "지금 계획 생성"으로 대기 플랜 leg 종목을 확인한다. 실주문은 하지 않는다.
- `make migrate` 후 `make migrate-down`으로 왕복을 확인한다.


## 구현 결과 (2026-10-26)

- **백엔드**
  - 모델·마이그레이션: `PortfolioItem.group_key/group_label` + `PortfolioItemMember`(`members`는 `lazy="selectin"`이라 `selectinload(Portfolio.items)`만 하는 기존 조회 13곳이 수정 없이 멤버까지 읽음). 응답은 ORM `PortfolioItem.group` property로 직렬화.
  - 검증 `_validate_group_members`: 그룹이 하나라도 있을 때만 동작. 단독 항목끼리의 중복은 예전처럼 막지 않는다.
  - 분석: `service._build_group_item`. 전개는 `group_expansion.py`가 맡고, `build_rebalancing_orders` 첫 단계(알림 미리보기·테스트 발송 포함)와 `plan_generation`(라이브 시세 갱신 전, 매수 계좌 세제유형 반영)이 호출한다.
  - `refresh_live_prices`는 그룹 행을 건너뛴다. 세금영향 미리보기는 `iter_trade_items`로 평탄화한다. 그렇지 않으면 수량이 없는 그룹 행이 "보유수량 전체 매도" 폴백에 걸린다.
  - 그 밖의 그룹 대응:
    - 미보유 국내 대체 종목의 현재가를 보완한다(`overview_enrichment._target_names`).
    - 적립식 예수금 부족 판정이 실제로 매수될 종목의 시장을 쓴다(`dca_cash_shortfall._buy_market`).
    - 추천 변화 알림이 그룹 멤버를 그룹 비중으로 합산한다(`fold_into_portfolio_groups`).
  - 제안 API: `GET /portfolios/index-group-suggestions`.
- **프론트**
  - 편집기: "지수로 묶기"(`IndexGroupPicker`, 펼칠 때만 조회)와 `PortfolioGroupItemRow`(대표·국내 대체 선택, 멤버 칩, 묶음 해제). 편집 로직은 `utils/portfolioGroups.ts`.
  - 분석표: 그룹 행 아래에 멤버 행을 보여준다. 모바일은 탭하면 펼친다.
  - 주문과 요약: `flattenTradeItems`로 평탄화한다.
  - 추천 적용: `toPortfolioItemsPreservingGroups`로 그룹을 유지한다.
- **계획과 다르게 처리한 것**
  - 전술 배분 가드: 422 대신 `is_tactical_managed`가 그룹 항목을 "비호환"으로 판정한다. 기존 비호환 경고와 분할 적용 차단 경로를 그대로 탄다.
- **남은 한계**
  - ~~수동 실행 모달은 국내 대체 종목으로 자동 전환하지 않는다~~ → plans/79 E에서 해소. 매수 계좌가 ISA·연금저축·IRP 한 곳이면 해외 대표 종목 매수 행을 국내 대체 종목 행으로 바꾼다(`rebalancingTradeMath.buyItemForAccount`, 백엔드 `_buy_target`과 같은 규칙). 같은 종목을 여러 계좌로 나눠 사는 중이면 배분 수량 단위가 섞여 바꾸지 않는다.
  - 팩터 전략(`strategy_service._build_trade_recommendations`)·expected-metrics·백테스트는 그룹 항목을 대표 종목 하나로 근사한다(proxy).
  - plan_generation 통합 테스트는 추가하지 않았다. 주문 생성은 `build_rebalancing_orders` 단위 테스트로 검증했다.
- **검증**
  - 백엔드: 전체 2920 passed, ruff·mypy clean, 신규 `tests/test_index_group_rebalancing.py` 14건. 마이그레이션은 `--sql` 오프라인 생성만 확인했다.
  - 프론트: 1804 passed, tsc·eslint·prettier clean, 신규 `__tests__/utils.portfolioGroups.test.ts` 10건.
  - 실기기·브라우저 확인은 하지 않았다.


## 후속: 레버리지 ETF 노출 합산 (2026-10-26)

- **요청**: QLD 같은 레버리지 ETF도 나스닥 100 그룹에 묶고 싶다. 합산은 사용자가 고른 **노출 기준(배수 반영)**으로 한다.
- **분류기**(`etf_index_classifier._leverage_info`)
  - 정방향 레버리지면 `index_key`(기초 지수)와 `leverage`를 채운다. 해외는 ticker 맵(QLD·TQQQ·SSO·UPRO·SPXL·DDM·UDOW·SOXL)으로, 국내는 종목명 "레버리지/2X/3X"로 판정한다. 기초 지수 이름이 없는 KODEX·TIGER 레버리지는 KOSPI200으로 본다.
  - 인버스는 키를 비운다.
  - `kind`는 LEVERAGED 그대로라 자산탭 지수별 비중 카드는 바뀌지 않는다.
- **제안**: INDEX 그룹에 기초 지수가 같은 레버리지 멤버를 합친다. 레버리지만 보유해도 큐레이션 1배 ETF를 대표로 제안한다. 레버리지 종목은 대표·국내 대체 후보에서 뺀다. 응답에 `exposure_krw`를 추가했다.
- **저장**: `PortfolioItemMember.leverage`(마이그레이션 `ig2_portfolio_item_member_leverage`, 2026-10-26 공유 Supabase 적용·`alembic check` 일치), `PortfolioGroupMember.leverage`(1~3). 국내 대체 종목이 레버리지면 422를 낸다.
- **분석·전개**: 그룹 행은 Σ(평가액 × 배수)로 이탈을 판정한다. 매도 시 줄일 노출 ÷ 배수만큼 레버리지 멤버를 판다. 매수는 1배 대표 종목으로만 한다.
- **프론트**: 칩·제안 목록에 "QLD ×2", 분석표에 "2배"와 "노출 기준"을 표시한다. 그룹 행에 노출 계산 안내를 넣었다.
- **검증**
  - 백엔드: 2947 passed. 신규 테스트로 분류 7건(파라미터화), 제안 2건, 분석·전개 3건, 검증 1건을 추가했다.
  - 프론트: 1805 passed, tsc·eslint·prettier clean.
- **범위 밖**: 인버스의 음(-) 노출, 레버리지 종목 매수, 일일 리셋(변동성 끌림).


## 후속 2: 제안 범위 — 다른 계좌의 QLD가 빠지던 문제 (2026-10-26)

- **원인**: QLD는 '해외' 계좌에만 있는데, 포트폴리오의 분석 대상 계좌는 ISA·연금이다. 편집기가 제안을 분석 대상 계좌로 조회하므로 QLD가 빠졌다. 분류와 레버리지 합산 로직은 정상이었다.
- **수정**: `get_index_group_suggestions`가 항상 전체 계좌 기준으로 제안을 만든다. 분석 대상 밖에만 있는 종목은 멤버의 `in_scope=False`와 `account_names`로 표시하고, 범위 안 종목을 먼저 정렬한다.
  - 편집기는 그 종목을 amber 칩으로 "QLD ×2(해외)"처럼 보여주고, "분석 대상 계좌에 추가해야 합산돼요"라고 안내한다.
  - 멤버로는 그대로 넣는다. 분석은 원래 분석 대상 계좌만 보므로, 계좌를 추가하기 전까지는 0원으로 잡힌다.
- **검증**
  - 백엔드: 신규 테스트 3건을 추가했다. 실데이터를 읽기 전용으로 조회해, ISA 범위에서도 US_NASDAQ100 제안에 QLD(×2, in_scope=False, 해외)가 나오는 것을 확인했다.
  - 프론트: 1807 passed.

## 후속 3: "지수로 묶기" 목록에 QLD가 안 보이던 문제 (2026-10-26)

- **확인**: 실행 중인 백엔드는 최신 코드였다. 실제 사용자로 API를 직접 호출하면 나스닥 100 제안에 QLD(×2)가 들어 있었다. 백엔드는 정상이다.
- **원인(프론트)**
  - `IndexGroupPicker`가 멤버를 한 줄 텍스트로 이어 붙이고 말줄임(`truncate`)을 걸어, 두 번째 이후 멤버가 잘려 보이지 않았다.
  - 제안 쿼리는 60초 stale이라, 편집기를 연 채로 이전 응답이 남을 수 있었다.
- **수정**
  - 멤버를 줄바꿈되는 칩으로 바꿨다. 칩에는 "ProShares Ultra QQQ ×2(해외)"와 대표 표시를 붙이고, 범위 밖 멤버는 amber 색으로 보여준다. 레버리지 안내 줄도 넣었다.
  - 제안 쿼리를 `staleTime: 0`으로 바꾸고, "지수로 묶기"를 펼칠 때마다 다시 조회한다.
  - 신규 테스트 `components.indexGroupPicker.test.tsx`. 프론트 1808 passed.
