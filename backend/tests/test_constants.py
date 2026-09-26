"""app.constants 불변식 테스트."""

from __future__ import annotations

from app.constants import POSITION_STOCK_ASSET_TYPES
from app.enums import AssetType
from app.services.rebalancing.order_builder import ORDER_EXECUTABLE_ASSET_TYPES


def test_every_stock_asset_type_tracks_positions():
    """STOCK_* asset_type이 추가되면 POSITION_STOCK_ASSET_TYPES에도 반드시 들어가야 한다 —
    누락 시 대시보드 주식평가액·자산구성·세금·자산추이 집계에서 조용히 빠진다(토스 연동 회귀)."""
    stock_types = {t.value for t in AssetType if t.value.startswith("STOCK_")}
    assert stock_types == POSITION_STOCK_ASSET_TYPES


def test_order_executable_types_are_subset_of_position_types():
    assert ORDER_EXECUTABLE_ASSET_TYPES <= POSITION_STOCK_ASSET_TYPES
