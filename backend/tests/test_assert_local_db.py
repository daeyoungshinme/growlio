"""scripts/assert_local_db.py — 파괴적 DB 명령이 운영(공유 Supabase)으로 가지 않게 막는다 (plans/156 C1)."""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "assert_local_db.py"
_spec = importlib.util.spec_from_file_location("assert_local_db", _SCRIPT)
assert _spec
assert _spec.loader
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

_SUPABASE = "postgresql+asyncpg://postgres.x:pw@aws-1-ap-northeast-2.pooler.supabase.com:6543/postgres"
_LOCAL = "postgresql+asyncpg://postgres:postgres@localhost:5432/growlio"


def test_migration_url_takes_precedence_like_alembic_env():
    assert mod.target_host(_SUPABASE, _LOCAL) == "aws-1-ap-northeast-2.pooler.supabase.com"
    assert mod.target_host("", _LOCAL) == "localhost"


def test_blocks_remote_host_without_override():
    assert mod.check("aws-1-ap-northeast-2.pooler.supabase.com", allow_remote=False)
    assert mod.check("aws-1-ap-northeast-2.pooler.supabase.com", allow_remote=True) is None


def test_allows_local_hosts():
    for host in ("localhost", "127.0.0.1", "db"):
        assert mod.check(host, allow_remote=False) is None
