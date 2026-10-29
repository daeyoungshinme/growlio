"""services/accounts/_snapshot_queries.py 단위 테스트."""

from __future__ import annotations

import uuid

from sqlalchemy.dialects import postgresql

from app.services.accounts._snapshot_queries import latest_snapshot_subquery


def _where_sql(subq) -> str:
    """서브쿼리의 WHERE 절만 컴파일한다 — `is not None`만 보면 필터가 빠져도 통과한다."""
    sql = str(subq.element.compile(dialect=postgresql.dialect()))
    return sql.split("WHERE", 1)[1] if "WHERE" in sql else ""


class TestLatestSnapshotSubquery:
    def test_returns_subquery_without_filters(self):
        subq = latest_snapshot_subquery()
        assert _where_sql(subq) == ""
        cols = {c.key for c in subq.c}
        assert "account_id" in cols
        assert "max_date" in cols

    def test_user_id_filter_applied(self):
        user_id = uuid.uuid4()
        subq = latest_snapshot_subquery(user_id=user_id)
        where = _where_sql(subq)
        assert "asset_snapshots.user_id =" in where
        assert "account_id IN" not in where

    def test_account_ids_filter_applied(self):
        account_ids = [uuid.uuid4(), uuid.uuid4()]
        subq = latest_snapshot_subquery(account_ids=account_ids)
        where = _where_sql(subq)
        assert "asset_snapshots.account_id IN" in where
        assert "user_id" not in where

    def test_both_filters_applied(self):
        user_id = uuid.uuid4()
        account_ids = [uuid.uuid4()]
        subq = latest_snapshot_subquery(user_id=user_id, account_ids=account_ids)
        where = _where_sql(subq)
        assert "asset_snapshots.user_id =" in where
        assert " AND " in where
        assert "asset_snapshots.account_id IN" in where

    def test_empty_account_ids_list(self):
        subq = latest_snapshot_subquery(account_ids=[])
        assert subq is not None

    def test_subquery_columns_structure(self):
        subq = latest_snapshot_subquery(user_id=uuid.uuid4())
        col_keys = [c.key for c in subq.c]
        assert len(col_keys) == 2
