"""재시작에도 유지되어야 하는 소규모 상태의 Postgres 기반 key-value 헬퍼.

`AppState` 테이블 전용 — 시장신호 등급전환 감지 마지막 값, 알림 dedup 플래그처럼
콜드스타트 후에도 값이 남아있어야 정확성(중복/누락 방지)이 보장되는 상태만 사용한다.
그 외 응답 캐시 등 휘발성 데이터는 `app.core.cache_store`(in-memory)를 사용할 것.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_state import AppState


async def get_durable(db: AsyncSession, key: str) -> str | None:
    """key의 값을 조회한다. 없거나 만료됐으면 None (만료 row는 opportunistic하게 삭제)."""
    row = await db.get(AppState, key)
    if row is None:
        return None
    if row.expires_at is not None and row.expires_at <= datetime.now(UTC):
        await db.delete(row)
        await db.commit()
        return None
    return row.value


async def set_durable(db: AsyncSession, key: str, value: str, ttl: int | None = None) -> None:
    """key에 value를 저장한다 (upsert). ttl(초) 지정 시 그 시점 이후 조회 시 미스로 취급."""
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl) if ttl is not None else None
    stmt = insert(AppState).values(key=key, value=value, expires_at=expires_at)
    stmt = stmt.on_conflict_do_update(
        index_elements=[AppState.key],
        set_={"value": stmt.excluded.value, "expires_at": stmt.excluded.expires_at},
    )
    await db.execute(stmt)
    await db.commit()


async def delete_durable(db: AsyncSession, key: str) -> None:
    await db.execute(delete(AppState).where(AppState.key == key))
    await db.commit()
