# 34. 기술부채 감사 (2026-09-15)

`docs/plans/32`(2026-09-13) 이후 HEAD 전진분은 챌린지 알림 이중게이트 버그 수정 + 홈 CTA 카드
(`d9c71bc`, 문서 33번에서 처리 완료) + dependabot PR 3건(#69 actions/#70 frontend 12개/#71
backend 2개, 전부 semver minor/patch, breaking change 없음)뿐. Explore 3개(이관 항목 코드대조 /
코드베이스 전반 스캔 / 최근 커밋·챌린지 기능 점검) 병렬 조사 + plan 32 이관 항목 8건 재검증.

## 같은 세션에 구현 완료

### 배치 A — 백엔드 저위험
- **`alert_service.py` 하위호환 shim 제거**(신규 발견) — 2026-07-20 감사(plan 10~12)에서
  "의도된 설계, 문제없음"으로 결론났던 `__all__`(`# noqa: F822`) + `__getattr__` lazy
  re-export(`check_and_trigger_alerts`/`check_and_trigger_stock_price_alerts`/
  `check_rebalancing_alerts`/`send_test_rebalancing_alert`)가, 그 사이 프로덕션 코드가 전부
  원본 모듈(`exchange_rate_service`/`stock_price_service`/`rebalancing.alert_check`/
  `rebalancing.alert_test`)에서 직접 import하도록 바뀌면서 실제로는 테스트 2개 파일에서만
  쓰이고 있었음을 확인 — 프로덕션 소비처가 사라지며 "의도된 설계"가 "죽은 shim"으로 드리프트한
  사례. shim 삭제 + `test_alert_service.py`/`test_alert_service_extended.py`의 import 11곳을
  원본 모듈 경로로 교체(patch 대상 문자열은 애초에 원본 모듈을 가리키고 있어 변경 불필요).
- **`noqa: E711` 16건 → SQLAlchemy 관용 표현 전환** — `Column == None`/`!= None` 패턴을
  `.is_(None)`/`.is_not(None)`으로 교체해 noqa 억제 자체를 불필요하게 만듦. `kis/auth.py`(5곳),
  `jobs/token_refresh.py`/`providers/manual_provider.py`/`services/asset_service.py`(2곳)/
  `api/v1/positions.py`/`services/credential_service.py`/`services/composition_calculator.py`/
  `services/price_service.py`/`services/snapshot_service.py`/`services/_position_queries.py`/
  `services/_settings_queries.py` 등 11개 파일.
- **`pyproject.toml` 의존성 상한 추가** — 상한 없이 방치돼 있던 보안/안정성 민감 패키지 10종
  (`PyJWT`, `apscheduler`, `python-multipart`, `structlog`, `httpx`, `asyncpg`, `alembic`,
  `prometheus-client`, `python-dateutil`, `scipy`)에 기존 스타일(`>=X,<Y`, 메이저 버전 1~2개
  여유)로 상한 추가 — plan 20번에서 세운 패턴을 나머지 미적용 의존성까지 확장. 재설치 후
  현재 설치본(structlog 25.5.0/httpx 0.28.1/asyncpg 0.31.0/alembic 1.19.2/scipy 1.17.1) 전부
  새 상한 이내임을 확인.

## 이관 항목 (이번 세션 미착수)

plan 31→32에서 이미 이관됐고, 이번 세션 코드대조 결과 관련 파일에 커밋이 없어 **전부 여전히
유효**함을 재확인:

### 1. 대형 `_compute_*` near-clone 5개 분해 — 구 plan 30 #2 / 31 #1 / 32 #1
`goal_portfolio_optimizer._optimize_goal_portfolio` 외 4개(`goal_age_recommendation_service`/
`goal_horizon_recommendation_service` ×2/`goal_recommendation_service`). characterization
스냅샷 테스트 하네스 선행 필수, 멀티 세션.

### 2. `assets.py` 브로커 분기 스펙테이블화 — 구 plan 30 #3 / 31 #2 / 32 #2
`create_account`/`update_account`의 KIS/키움/토스 near-identical 분기 3벌, 미변경.

### 3. `market_signal_service.py`(835줄) 분해 — 구 plan 24 #2 / 29 #3 / 30 #5 / 31 #3 / 32 #3
미변경. AUTO 게이트 신호원이라 회귀 리스크로 저긴급 유지.

### 4. 키움 해외 주문 NASDAQ 폴백 7일 캐시 — 구 plan 31 #4 / 32 #4
설계 리스크 모니터링 노트, 실제 버그 아님. 미변경.

### 5. 토스 `market` 판별 필터 불일치 — 구 plan 31 #5 / 32 #5
`toss/balance.py:129`(`marketCountry != "KR"`) vs `toss_provider.py:119`(`currency == "USD"`).
이번 세션에 두 파일을 직접 읽어 재확인 — 현재 토스가 지원하는 시장 범위(국내 KRW / 해외
US-USD)에서는 두 기준이 항상 일치해 지금 재현 가능한 버그는 아니나, 서로 다른 필드를 기준으로
삼는 구조 자체는 향후 토스가 시장을 확장하면 조용히 어긋날 잠재 리스크로 남음. 4회 연속 이관.

### 6. 2-leg 부분실행 가시성 재확인 — 구 plan 27 이관분 / 31 #7 / 32 #6
브로커 API 응답 심층 조사 필요, 이번 세션도 착수 못함.

### 7. `useRebalancingExecution`(525줄) 커버리지 45% — 구 plan 31 #9 / 32 #7
미변경, 커버리지 보강 우선 기존 결론 유지.

### 8. 경쟁앱 대비 기능격차 — 로드맵 전용(변경 없음)
정기 자동매수, ETF TER. 착수 계획 없음.

### 9. `cache_keys.py`(515줄) 비대화 — 신규 발견
"단순 캐시 키 빌더" 치고 이례적으로 큼. 실제 책임 분리(키 네임스페이스별 분할 등)가 필요한지는
다음 감사에서 판단 — 이번엔 규모만 확인, 착수하지 않음.

### 10. provider 계층 완전 스왈로우 `except Exception:` 5곳 — 신규 발견
`http_client.py:77,149`, `toss_provider.py:42`, `_error_mapping.py:18`,
`dividend/sync_sources.py:57`. 코드 확인 결과 대부분 "에러 응답 형식 판별"류 방어적 파싱으로
보이나 5곳 전부를 개별적으로 검증하지는 못함 — 다음 세션 검토 항목으로 유지.

## 검증

```bash
cd backend && .venv/Scripts/python.exe -m pytest --cov=app --cov-fail-under=80 -q
cd backend && .venv/Scripts/python.exe -m ruff check app tests
cd backend && .venv/Scripts/python.exe -m mypy app
```

백엔드 2160 tests, 커버리지 88.56%(임계값 80% 대비 여유), ruff/mypy 클린. `pip install -e
".[dev]"` 재설치로 새 의존성 상한과의 충돌 없음도 확인.
