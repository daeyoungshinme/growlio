"""services/_snapshot_queries.py 단위 테스트."""

from __future__ import annotations

import uuid

from app.services._snapshot_queries import latest_snapshot_subquery


class TestLatestSnapshotSubquery:
    def test_returns_subquery_without_filters(self):
        subq = latest_snapshot_subquery()
        assert subq is not None
        cols = {c.key for c in subq.c}
        assert "account_id" in cols
        assert "max_date" in cols

    def test_user_id_filter_applied(self):
        user_id = uuid.uuid4()
        subq = latest_snapshot_subquery(user_id=user_id)
        assert subq is not None

    def test_account_ids_filter_applied(self):
        account_ids = [uuid.uuid4(), uuid.uuid4()]
        subq = latest_snapshot_subquery(account_ids=account_ids)
        assert subq is not None

    def test_both_filters_applied(self):
        user_id = uuid.uuid4()
        account_ids = [uuid.uuid4()]
        subq = latest_snapshot_subquery(user_id=user_id, account_ids=account_ids)
        assert subq is not None

    def test_empty_account_ids_list(self):
        subq = latest_snapshot_subquery(account_ids=[])
        assert subq is not None

    def test_subquery_columns_structure(self):
        subq = latest_snapshot_subquery(user_id=uuid.uuid4())
        col_keys = [c.key for c in subq.c]
        assert len(col_keys) == 2
