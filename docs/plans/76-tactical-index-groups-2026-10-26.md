> 상태: **구현 완료(미커밋)** (2026-10-26). plans/74(지수 그룹 리밸런싱, 미커밋)와 ig2(그룹 멤버 레버리지) 위에 얹은 작업이다. 마이그레이션은 없다. 파일:라인은 작성 시점 기준이며, 실행할 때는 현재 코드를 우선한다.

# 전술 배분을 지수 그룹(나스닥100 / S&P500) 단위로 (plans/76)

## Context
리밸런싱 > 목표 조정 > 전술은 QQQ·SPY·DIA·QLD·SSO·현금을 **종목 단위**로 다뤘다. 포트폴리오는 plans/74부터 지수 그룹(예: S&P500 = VOO+SPY+TIGER 미국S&P500)으로 관리할 수 있다. 그래서 두 기능이 충돌했다.
- `apply_regime_to_portfolio`가 항목을 전부 지우고 QQQ·SPY 단독 항목으로 다시 만들었다. 그 결과 그룹 구성이 사라졌고, VOO·TIGER 같은 멤버가 "목표에 없는 종목"이 되어 전량 매도 대상이 됐다.
- plans/74는 이를 피하려고 그룹이 있는 포트폴리오를 `is_tactical_managed`에서 "비호환"으로 막았다. 그래서 분할 적용이 막히고 비호환 경고가 떴다.
- `_current_weights`가 ticker를 키로 썼다. 그래서 대표 종목이 VOO인 S&P500 그룹이 "SPY 0% + 기타 종목"으로 보였다. 홈 "지금 할 일"(plans/75)도 계속 "미적용"으로 판정했다.

## 사용자가 정한 내용
1. **전술이 포트폴리오 전체를 관리한다.** 전술 자산이 아닌 항목은 전과 같이 "기타 종목 → 0%"로 경고하고, 적용할 때 삭제한다.
2. **레버리지(QLD·SSO)**
   - 비중표에서 0%보다 크면 별도 단독 항목(원금 비중)으로 둔다.
   - 0%면 짝 그룹(나스닥100·S&P500)의 레버리지 멤버(노출 = 평가액 × 배수)로 남긴다. 그러면 그룹이 비중을 넘을 때 먼저 팔리고, 전량 매도되지 않는다.
3. **그룹이 없으면 자동으로 만든다.** 보유 종목 기준 지수 묶기 제안(`get_index_group_suggestions`)에서 멤버와 국내 대체 종목을 가져온다. 대표 종목은 전술 자산(QQQ·SPY·DIA)이다.

## 구현
비중표 내부 키(`QQQ/SPY/DIA/QLD/SSO/CASH`), 저장된 `regime_weights`, 틸트, 웅덩이, 백테스트는 바꾸지 않았다. 백테스트와 국면 판정은 QQQ·SPY 가격으로 지수를 재현하는 proxy다.

- **`backend/app/services/tactical_allocation_service.py`**
  - 매핑
    - `ASSET_GROUP_KEYS`는 `QQQ→US_NASDAQ100`, `SPY→US_SP500`, `DIA→US_DJIA`이다. `_LEVERAGED_PAIR`는 `QLD→(QQQ, 2)`, `SSO→(SPY, 2)`이다.
    - `tactical_asset_of(item)`이 항목을 전술 자산에 매핑한다. 그룹은 group_key로, 단독 항목은 ticker로 판별한다.
  - 판정
    - `_current_weights`는 자산 키 기준으로 합산한다. 그래서 `build_status`, `pending_action`(plans/75), `interpolate_weights`(분할 적용), 프론트 비교표가 함께 바로잡힌다.
    - `is_tactical_managed`는 모든 항목이 전술 자산에 매핑되면 True다. plans/74 가드를 대체한다.
    - `current_groups`는 상태 응답에 그룹 구성 요약(대표 종목, 멤버 수, 국내 대체 종목)을 넣는다.
  - 적용(`apply_regime_to_portfolio`)
    - "전부 삭제 후 재생성" 구조는 유지한다. 대신 삭제 전에 그룹 구성을 값으로 복사해 두고(`_plan_groups`), 그룹 항목과 멤버를 다시 만든다.
    - 기존 그룹이 있으면 대표 종목·멤버·국내 대체 종목을 보존하고 비중만 바꾼다.
    - 그룹이 없으면 `group_suggestions`로 새로 만들고, 제안이 없으면 대표 종목만으로 만든다. 레버리지 규칙도 여기서 반영한다.
  - 새 그룹을 만들어야 할 때만 `needs_group_suggestions`가 True를 돌려준다.
  - `format_weights`는 알림·이메일 문구에 `ASSET_LABELS`(나스닥100 / S&P500 / 다우존스 / 나스닥100 2배 / S&P500 2배 / 현금)를 쓴다.
- **`backend/app/api/v1/tactical.py`**: `_group_suggestions`가 `PortfolioAccount`에서 연결 계좌를 직접 조회한다. `linked_accounts`는 lazy 관계라서 async에서 쓰면 안 된다. 그다음 `get_index_group_suggestions`를 호출한다. 실패해도 적용은 막지 않는다(경고 로그만 남김).
- **프론트**
  - `tacticalLabels`: `ASSET_LABEL`을 지수 이름으로 바꾸고 `INDEX_GROUP_ASSETS`를 추가했다. `formatTacticalWeights`와 `TACTICAL_ASSET_LIST_TEXT`도 백엔드와 같은 이름을 쓴다.
  - 전술 탭 `WeightsCompare`: 행 아래 `GroupNote`가 "대표 VOO · 2종목 합산" 또는 "적용하면 같은 지수 보유 종목을 묶어요"를 보여준다.
  - 적용 확인 모달에 "그룹 구성은 그대로 두고 비중만 바꿔요" 문구를 추가했다.
  - 편집기 입력 라벨을 나스닥100 / S&P500 / 다우 / 나스닥 2배 / S&P 2배로 바꿨다.
  - 화면 문구의 "QQQ·SPY"를 "나스닥·S&P500"으로 바꿨다(목표 조정 소개, 진단 배너, 알림 설정).

## 남은 한계
- QLD를 0%로 바꿀 때 짝 그룹에 레버리지 멤버로 옮기는 것은 **예전 단독 항목이었던 경우**와 **새 그룹을 제안으로 만들 때 보유 종목에 있는 경우**뿐이다. 기존 그룹이 있고 QLD를 따로 보유만 하는 경우에는 제안을 조회하지 않는다. 사용자가 확정한 그룹 구성을 존중하기 위해서다.
- 비중이 0이 된 그룹 자산(예: DIA 0%)은 그룹째 삭제된다. 나중에 다시 비중이 생기면 제안으로 새로 만들기 때문에, 사용자가 지정했던 대표 종목은 기억하지 않는다.
- 백테스트 비교선 이름(SPY·QQQ·DIA 단순보유)은 그대로 두었다.

## 검증
- 백엔드: `tests/test_tactical_allocation.py::TestIndexGroups` 6건을 추가했다.
  - 그룹 매핑과 `pending_action`
  - 다른 지수 그룹은 비호환으로 판정
  - 기존 그룹 보존과 새 그룹 생성(멤버, 국내 대체, QLD 레버리지 멤버)
  - 제안이 없을 때 대표 종목만으로 그룹 생성
  - QLD 0→10→0에서 단독 항목과 레버리지 멤버 사이 이동(한 종목이 한 항목에만 있는지 불변식 확인)
  - 그룹 포트폴리오의 분할 적용
- API 적용 테스트에서 그룹 생성과 제안 조회를 확인했다. 라벨 관련 단언은 갱신했다.
- 결과: 전체 2953 passed, ruff·mypy clean.
- 프론트: `TacticalAllocationTab.test.tsx`에 그룹 보조 문구 테스트를 추가하고 라벨 단언을 갱신했다. 전체 1806 passed, tsc·eslint·prettier clean.
- 실기기·브라우저 확인은 하지 않았다.
