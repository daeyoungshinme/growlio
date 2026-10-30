# 98 — 기술부채 감사 7차 (2026-10-30c)

## 배경

97의 이관 항목은 모두 95에서 넘어온 것이다. 정리만 하면 된다고 봤던 항목 둘에서 실버그가 나왔다. Dockerfile 항목은 95 계획대로 고치면 배포가 깨지는 상태였다.

브랜치: `chore/tech-debt-2026-10-30c`(96·97이 머지된 `main` 기준). 클러스터마다 커밋 1개.

## 결과

| # | 항목 | 결과 |
|---|---|---|
| A | backend 이미지 | uv를 `ghcr.io/astral-sh/uv:0.11.15` 단계로 고정했다(`pip install uv` 제거, Dependabot docker가 추적). `uv sync --locked --no-dev --no-install-project`로 의존성만 설치하고 builder의 `COPY app/`를 지웠다. 이제 코드만 바뀌어도 의존성 레이어 캐시가 유지된다. **함정**: 지금까지는 `uv export`가 `-e .`를 내보내 프로젝트를 editable로 설치했다. preDeploy의 `scripts/bootstrap_alembic.py`는 이 설치 덕분에 `import app`이 됐다. 그래서 runtime에 `PYTHONPATH=/app`을 넣었다. `nginx:alpine`은 `nginx:1.29-alpine`으로 고정했다. 로컬에 Docker가 없어서 `ci.yml`에 `docker-build` 잡을 추가했다. 두 이미지를 빌드하고, scripts/ 작업 경로에서 `import app.core.config`, `import app.main`, `alembic --help`를 실행하는 스모크를 돌린다 |
| B | 거래 입력 달러 환산 | **실버그.** TransactionModal 경로(`useTransactionFormState`)는 환율 없이 USD로 바꾸면 `amountUsd`만 0이 되고 이전 원화 금액이 남았다. 그래서 빈 `$` 칸 뒤로 그 금액이 저장됐다(95 F3는 TransactionForm에만 적용됐다). `useUsdAmountInput`이 두 폼의 통화 상태·환산·제출 가드를 맡는다. 환율이 있으면 전환할 때 환산값을 유지하고, 없으면 금액을 비우고 제출을 막는다 |
| C | 리밸런싱 실행 훅 | **실버그.** 계좌별 현금 바(`getCashAnalysis`)만 매도 수량을 보유량으로 자르지 않았다. `SET_QTY_AND_SELECT`·일괄 조정·잔고 갱신 뒤에는 매도 예상 대금이 전체 요약·실제 주문보다 크게 나왔다(테스트 재현: 5주 보유, 100주 입력 → 2,000만 원, 정답 100만 원). 행·대금 계산은 `rows.ts` 순수 함수로 옮겼다. 주문·계좌 바·전체 요약은 모두 `effectiveQty`·`sumSelectedEstimates`를 쓴다. useMemo의 exhaustive-deps disable 3곳을 지웠다(마운트 1회 effect만 남김) |
| D | CashSummaryBar | `!` 단언 6곳을 `?? 0` 지역값과 `surplus !== null` 좁히기로 바꿨다. 렌더 결과는 같다 |

## 검증

- 프론트: eslint `--max-warnings 0`, prettier, `npm run typecheck`(앱+테스트) 클린. 1904 tests. 새 테스트: `useUsdAmountInput` 3건, 계좌 바 보유량 상한 1건(수정 전 코드에서 실패 확인).
- 백엔드: Python 코드 변경 없음. `uv sync --no-install-project --dry-run`으로 dev 패키지와 프로젝트 자체가 빠지는 것만 확인했다.
- **미검증(로컬 Docker 없음)**: 이미지 빌드·스모크는 PR CI `docker-build` 잡에서 처음 돈다. Render 배포 뒤 preDeploy 로그(bootstrap·alembic)는 직접 확인해야 한다.

## 이관

- `vite-plugin-pwa → workbox-build` low 4건: 2.0.0이 최신이라 상위 수정을 기다린다. `--omit=dev`는 0건.
- 95 "유지" 목록 그대로.
