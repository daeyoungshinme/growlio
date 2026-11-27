"""파괴적 DB 명령(`make migrate-down`·`make db-reset`) 전에 대상이 로컬 DB인지 확인한다 (plans/156 C1).

`alembic/env.py`와 같은 순서(`MIGRATION_DATABASE_URL` → `DATABASE_URL`)로 대상을 정한다. 로컬 `backend/.env`가
공유 Supabase(운영, nestlio와 `public` 공유)를 가리키는 경우가 흔해서, 개발용이라 믿고 실행하면 운영 스키마가
롤백된다. 호스트가 로컬이 아니면 `ALLOW_REMOTE_DB=1` 없이는 종료 코드 1로 멈춘다.
"""

from __future__ import annotations

import os
import sys

from sqlalchemy.engine import make_url

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "db", "host.docker.internal"})


def target_host(migration_url: str, database_url: str) -> str:
    return make_url(migration_url or database_url).host or ""


def check(host: str, allow_remote: bool) -> str | None:
    """막아야 하면 이유 문장, 통과면 None."""
    if host in LOCAL_HOSTS or allow_remote:
        return None
    return (
        f"대상 DB 호스트가 로컬이 아닙니다: {host}\n"
        "backend/.env의 MIGRATION_DATABASE_URL/DATABASE_URL이 운영(공유 Supabase)일 수 있습니다.\n"
        "정말 원격 DB에 실행하려면 ALLOW_REMOTE_DB=1을 붙여 다시 실행하세요."
    )


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows 콘솔 기본(cp949)에서 한글이 깨지지 않게
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app.core.config import settings

    host = target_host(settings.migration_database_url, settings.database_url)
    reason = check(host, os.environ.get("ALLOW_REMOTE_DB") == "1")
    if reason:
        print(reason, file=sys.stderr)
        return 1
    print(f"대상 DB: {host or '(호스트 없음)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
