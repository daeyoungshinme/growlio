"""계획 133 버그로 과다 저장된 수기 계좌 일별 스냅샷 보정 (plans/135 A2).

2026-11-02(#217 배포)부터 2026-11-15(#279 배포)까지 수기 계좌(MANUAL) 동기화가 달러 예수금을
`deposit_usd × 1300(fallback)`만큼 한 번 더 더해 `asset_snapshots.amount_krw`에 저장했다.
11월 월별 대표값은 이후 재동기화로 정상화됐고, 기간 안 일별 행만 남아 있다.

사용법 (backend/ 에서):
    uv run python scripts/fix_manual_usd_double_count_133.py                 # dry-run: 후보 출력만
    uv run python scripts/fix_manual_usd_double_count_133.py --apply --ids <id,id,...>

- 접속은 `MIGRATION_DATABASE_URL`(없으면 `DATABASE_URL`) — 운영 DB면 dry-run 결과를 먼저 확인한다.
- 과거 `deposit_usd` 이력이 없어 **현재 값**으로 계산한다. 기간 중 달러 예수금을 바꿨거나, 그날 마지막 쓰기가
  종목 저장·현재가 동기화(정상 합계)였던 행은 보정하면 오히려 틀린다 — 인접 정상 스냅샷과 비교한 `check` 열이
  `ALREADY_OK?`면 빼고 `--ids`에 넘긴다.
- 서버 캐시는 프로세스 로컬이라 여기서 지울 수 없다. 대시보드·추이는 캐시 TTL이 지나거나 계좌를 동기화하면 반영된다.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.asset import AssetAccount, AssetSnapshot

BUG_START = date(2026, 11, 2)
BUG_END = date(2026, 11, 15)
# 버그 당시 BalanceResult.usd_krw_rate 기본값(settings.usd_krw_fallback_rate) — 설정이 바뀌어도 당시 값으로 고정
BUG_RATE = Decimal("1300")


@dataclass
class Candidate:
    snapshot_id: uuid.UUID
    account_id: uuid.UUID
    account_name: str
    snapshot_date: date
    amount_krw: Decimal
    excess_krw: Decimal
    neighbor_krw: Decimal | None

    @property
    def corrected_krw(self) -> Decimal:
        return self.amount_krw - self.excess_krw

    @property
    def check(self) -> str:
        """인접 정상 스냅샷에 보정값이 더 가까우면 OK, 원래 값이 더 가까우면 이미 정상일 가능성."""
        if self.neighbor_krw is None:
            return "NO_NEIGHBOR"
        if abs(self.amount_krw - self.neighbor_krw) < abs(self.corrected_krw - self.neighbor_krw):
            return "ALREADY_OK?"
        return "OK"


async def _neighbor_amount(db: AsyncSession, account_id: uuid.UUID) -> Decimal | None:
    """버그 기간 밖 가장 가까운 스냅샷(직전 우선, 없으면 직후) — 정상값 비교 기준."""
    before = await db.scalar(
        select(AssetSnapshot.amount_krw)
        .where(AssetSnapshot.account_id == account_id, AssetSnapshot.snapshot_date < BUG_START)
        .order_by(AssetSnapshot.snapshot_date.desc())
        .limit(1)
    )
    if before is not None:
        return Decimal(before)
    after = await db.scalar(
        select(AssetSnapshot.amount_krw)
        .where(AssetSnapshot.account_id == account_id, AssetSnapshot.snapshot_date > BUG_END)
        .order_by(AssetSnapshot.snapshot_date.asc())
        .limit(1)
    )
    return Decimal(after) if after is not None else None


async def find_candidates(db: AsyncSession) -> list[Candidate]:
    rows = (
        await db.execute(
            select(AssetSnapshot, AssetAccount)
            .join(AssetAccount, AssetAccount.id == AssetSnapshot.account_id)
            .where(
                AssetAccount.data_source == "MANUAL",
                AssetAccount.deposit_usd > 0,
                AssetSnapshot.source == "MANUAL",
                AssetSnapshot.snapshot_date.between(BUG_START, BUG_END),
            )
            .order_by(AssetSnapshot.account_id, AssetSnapshot.snapshot_date)
        )
    ).all()
    neighbors: dict[uuid.UUID, Decimal | None] = {}
    out: list[Candidate] = []
    for snap, account in rows:
        if account.id not in neighbors:
            neighbors[account.id] = await _neighbor_amount(db, account.id)
        out.append(
            Candidate(
                snapshot_id=snap.id,
                account_id=account.id,
                account_name=account.name,
                snapshot_date=snap.snapshot_date,
                amount_krw=Decimal(snap.amount_krw),
                excess_krw=(Decimal(str(account.deposit_usd or 0)) * BUG_RATE).quantize(Decimal("0.01")),
                neighbor_krw=neighbors[account.id],
            )
        )
    return out


async def apply_fix(db: AsyncSession, ids: set[uuid.UUID]) -> int:
    """지정한 id 중 후보로 확인되는 행만 보정한다(후보 밖 id는 무시). 반환: 수정 행 수."""
    targets = [c for c in await find_candidates(db) if c.snapshot_id in ids]
    for c in targets:
        await db.execute(
            update(AssetSnapshot).where(AssetSnapshot.id == c.snapshot_id).values(amount_krw=c.corrected_krw)
        )
    return len(targets)


def _engine_url() -> str:
    return settings.migration_database_url or settings.database_url


def _connect_args() -> dict:
    # bootstrap_alembic.py와 같은 규칙: pooler(6543)는 prepared statement 캐시 비호환
    args: dict = {"statement_cache_size": 0}
    if settings.supabase_project_url or settings.app_env == "production":
        args["ssl"] = "require"
    return args


def _print(cands: list[Candidate]) -> None:
    if not cands:
        print("후보 없음")
        return
    print(
        f"{'snapshot_id':36}  {'date':10}  {'amount':>15}  {'excess':>12}  "
        f"{'corrected':>15}  {'neighbor':>15}  check  account"
    )
    for c in cands:
        neighbor = f"{c.neighbor_krw:,.0f}" if c.neighbor_krw is not None else "-"
        print(
            f"{c.snapshot_id}  {c.snapshot_date}  {c.amount_krw:>15,.0f}  {c.excess_krw:>12,.0f}  "
            f"{c.corrected_krw:>15,.0f}  {neighbor:>15}  {c.check}  {c.account_name}"
        )
    print(f"\n후보 {len(cands)}건 — check가 OK인 id만 골라 --apply --ids 로 넘긴다")


async def _run(apply: bool, ids: set[uuid.UUID]) -> None:
    engine = create_async_engine(_engine_url(), poolclass=NullPool, connect_args=_connect_args())
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            if not apply:
                _print(await find_candidates(db))
                return
            async with db.begin():
                changed = await apply_fix(db, ids)
            print(f"보정 {changed}건 (요청 {len(ids)}건)")
    finally:
        await engine.dispose()


def main() -> None:
    # Windows 콘솔(cp949)은 도움말의 대시·곱셈 기호를 못 찍어 죽는다 — 못 찍는 문자만 치환
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="보정 실행(없으면 dry-run)")
    parser.add_argument("--ids", default="", help="보정할 snapshot id, 쉼표 구분 (--apply와 함께)")
    args = parser.parse_args()
    ids = {uuid.UUID(s.strip()) for s in args.ids.split(",") if s.strip()}
    if args.apply and not ids:
        parser.error("--apply에는 --ids가 필요하다 (dry-run 결과에서 고른다)")
    asyncio.run(_run(args.apply, ids))


if __name__ == "__main__":
    main()
