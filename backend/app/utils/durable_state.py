"""재시작에도 유지되어야 하는 소규모 상태의 Postgres 기반 key-value 헬퍼.

`AppState` 테이블 전용 — 시장신호 등급전환 감지 마지막 값, 알림 dedup 플래그처럼
콜드스타트 후에도 값이 남아있어야 정확성(중복/누락 방지)이 보장되는 상태만 사용한다.
그 외 응답 캐시 등 휘발성 데이터는 `app.core.cache_store`(in-memory)를 사용할 것.

세 함수 모두 기본적으로 커밋까지 한다. `commit=False`면 커밋을 호출부에 위임한다 — savepoint
(`begin_nested`) 안에서 쓸 때 필수(내부 commit이 바깥 트랜잭션까지 커밋해 버린다).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_state import AppState


async def get_durable(db: AsyncSession, key: str, *, commit: bool = True) -> str | None:
    """key의 값을 조회한다. 없거나 만료됐으면 None (만료 row는 opportunistic하게 삭제)."""
    row = await db.get(AppState, key)
    if row is None:
        return None
    if row.expires_at is not None and row.expires_at <= datetime.now(UTC):
        await db.delete(row)
        if commit:
            await db.commit()
        return None
    return row.value


async def set_durable(db: AsyncSession, key: str, value: str, ttl: int | None = None, *, commit: bool = True) -> None:
    """key에 value를 저장한다 (upsert). ttl(초) 지정 시 그 시점 이후 조회 시 미스로 취급."""
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl) if ttl is not None else None
    stmt = insert(AppState).values(key=key, value=value, expires_at=expires_at)
    stmt = stmt.on_conflict_do_update(
        index_elements=[AppState.key],
        set_={"value": stmt.excluded.value, "expires_at": stmt.excluded.expires_at},
    )
    await db.execute(stmt)
    if commit:
        await db.commit()


async def claim_durable(db: AsyncSession, key: str, ttl: int, *, commit: bool = True) -> bool:
    """key를 원자적으로 선점한다 — 이 호출이 처음 차지했으면 True, 이미 살아 있는 claim이 있으면 False.

    `get_durable` 후 `set_durable`은 읽고 쓰는 사이에 다른 프로세스가 끼어들 수 있다(Render 무중단 배포로
    두 인스턴스가 겹치면 in-proc 락도 소용없다). 여기서는 PK 충돌을 DB가 판정한다:
    `INSERT … ON CONFLICT DO NOTHING RETURNING key`가 행을 돌려주면 선점 성공(plans/61 C1).
    만료된 claim은 먼저 지워서 TTL이 지난 키는 다시 차지할 수 있게 한다. Transaction Pooler(6543)에서는
    session advisory lock을 쓸 수 없어서 이 방식을 쓴다.
    """
    now = datetime.now(UTC)
    await db.execute(
        delete(AppState).where(AppState.key == key, AppState.expires_at.is_not(None), AppState.expires_at <= now)
    )
    stmt = (
        insert(AppState)
        .values(key=key, value="1", expires_at=now + timedelta(seconds=ttl))
        .on_conflict_do_nothing(index_elements=[AppState.key])
        .returning(AppState.key)
    )
    result = await db.execute(stmt)
    claimed = result.scalar_one_or_none() is not None
    if commit:
        await db.commit()
    return claimed


async def delete_durable(db: AsyncSession, key: str, *, commit: bool = True) -> None:
    await db.execute(delete(AppState).where(AppState.key == key))
    if commit:
        await db.commit()


async def purge_expired_durable(db: AsyncSession) -> int:
    """만료된 row를 일괄 삭제하고 삭제 건수를 돌려준다.

    get_durable은 같은 키를 다시 읽을 때만 만료 row를 지우는데, 날짜가 들어간 dedup 키
    (composite_alert_sent_key 등)는 다음 날부터 다시 읽히지 않아 영원히 남는다.
    """
    result = await db.execute(delete(AppState).where(AppState.expires_at <= datetime.now(UTC)))
    await db.commit()
    return int(getattr(result, "rowcount", 0) or 0)
