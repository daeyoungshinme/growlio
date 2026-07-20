# 계획 10: 캐시 키 중앙화 + 회원 탈퇴 시 캐시 미무효화 버그 수정

**리스크: 낮음 — 캐시 키 포맷 변경 + 헬퍼 추출, 조회 로직 자체는 변경 없음. 단, 배포 시 기존 캐시 키와 새 키가 한동안 공존하므로 TTL 경과 전까지는 구 키가 잔존(무해).**

## 배경 (Why)

`backend/app/utils/cache_keys.py`는 "캐시 키 포맷을 한 곳에서 관리"하기 위한 모듈이고, 대부분의 서비스가 여기 정의된 `*_key()` 빌더 함수를 사용한다. 하지만 아래 4개 파일은 이를 거치지 않고 각자 f-string으로 캐시 키를 직접 생성한다:

- `app/services/factor_service.py:169,215`
- `app/services/risk_service.py:110`
- `app/services/portfolio_optimizer.py:179`
- `app/services/insight_service.py:27-28`

이 4개 키는 `cache_keys.py`의 `_env_prefix()`(운영/개발 환경 분리 접두사)를 거치지 않는다. 그 결과 **실제 버그**가 있다: `cache_keys.py:300-302`의 `invalidate_all_user_caches(redis, user_id)`는 `SCAN {env_prefix}*{user_id}*` 패턴으로 유저 관련 캐시를 전부 지우는데, 위 4개 키(`factor_analysis:`, `risk:`, `efficient_frontier:`, `insights:` 접두사)는 `_env_prefix()`가 없어 이 SCAN 패턴에 매칭되지 않는다. `app/api/v1/auth.py:133`(회원 탈퇴)에서 이 함수를 호출하지만, 탈퇴한 유저의 팩터/리스크/최적화/인사이트 캐시는 TTL(기본 1시간)이 지날 때까지 남아있게 된다. 개인정보 관점에서 사소하지 않은 결함이다.

부수적으로 `app/api/v1/assets.py:357`, `app/api/v1/positions.py:91,168`에 `f"sync_lock:{account_id}"` 락 키 리터럴이 3곳 중복되어 있다(공용 헬퍼 없음).

## 구현 단계

1. **`cache_keys.py`에 4개 키 빌더 추가**: 기존 함수들의 시그니처/네이밍 컨벤션을 따라 `factor_analysis_key(user_id, ...)`, `risk_key(user_id, ...)`, `efficient_frontier_key(user_id, ...)`, `insights_key(user_id, ...)` 형태로 추가 — 반드시 `_env_prefix()`를 거치도록 구현(기존 다른 빌더와 동일 패턴).
2. **4개 서비스 파일 수정**: `factor_service.py`, `risk_service.py`, `portfolio_optimizer.py`, `insight_service.py`에서 인라인 f-string 대신 1번에서 만든 빌더 호출로 교체.
3. **`invalidate_all_user_caches` 동작 재확인**: 수정 후 4개 키가 `SCAN {env_prefix}*{user_id}*` 패턴에 실제로 매칭되는지 로컬 Redis로 확인(또는 관련 유닛 테스트 추가).
4. **`sync_lock` 키 헬퍼 추출**: `cache_keys.py`(또는 `app/utils/redis_lock.py`)에 `sync_lock_key(account_id)` 추가 후 `assets.py:357`, `positions.py:91,168` 3곳 교체.
5. **테스트**: 기존 캐시 관련 테스트(factor/risk/optimizer/insight 캐시 hit/miss 테스트)가 있다면 키 포맷 변경에 맞춰 패치 확인. 회원 탈퇴 캐시 무효화 테스트가 없다면 4개 키가 실제로 삭제되는 케이스 하나 추가.
6. **검증**: `cd backend && uv run pytest && uv run ruff check . && uv run mypy app/`.

## 부수 정리 (선택, 별도 diff로 진행 권장)

- `app/models/alert.py:34-36`(`_AlertMixin.is_active` declared_attr)와 `:61`(`RebalancingAlert`가 동일 컬럼 재선언)의 중복 제거 — 다른 alert 서브클래스는 재선언하지 않으므로 의도적 이유가 없다면 제거. 재선언에 특별한 이유가 있는지 git blame으로 먼저 확인.

## 주의사항

- 배포 직후에는 기존(구 포맷) 캐시 키가 새 무효화 패턴에도 안 걸리는 과도기가 하루 정도(TTL) 있을 수 있음 — 기능 영향 없음(단순 캐시 미스 증가).
- `_env_prefix()` 적용 후 캐시 키 문자열이 바뀌므로, 이 키를 하드코딩해서 참조하는 모니터링/디버깅 스크립트가 있다면 함께 확인.
