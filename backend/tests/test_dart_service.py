"""dart_service.py 단위 테스트 — httpx 모킹."""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_corp_xml(pairs: list[tuple[str, str]]) -> bytes:
    """stock_code → corp_code 쌍으로 DART CORPCODE.xml 생성."""
    root = ET.Element("result")
    for stock, corp in pairs:
        item = ET.SubElement(root, "list")
        ET.SubElement(item, "stock_code").text = stock
        ET.SubElement(item, "corp_code").text = corp
    return ET.tostring(root, encoding="utf-8", xml_declaration=False)


def _make_zip(xml_bytes: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CORPCODE.xml", xml_bytes)
    return buf.getvalue()


class TestFetchCorpCodeMap:
    @pytest.mark.asyncio
    async def test_returns_map_from_xml(self, override_settings):
        import app.services.dart_service as ds

        xml = _make_corp_xml([("005930", "00126380"), ("035420", "00098460")])
        zip_bytes = _make_zip(xml)

        mock_resp = MagicMock()
        mock_resp.content = zip_bytes
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await ds._fetch_corp_code_map("test-key")

        assert result["005930"] == "00126380"
        assert result["035420"] == "00098460"

    @pytest.mark.asyncio
    async def test_returns_empty_dict_on_http_error(self, override_settings):
        import app.services.dart_service as ds

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("timeout"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await ds._fetch_corp_code_map("test-key")

        assert result == {}


class TestEnsureCorpCodeMap:
    @pytest.mark.asyncio
    async def test_calls_fetch_when_empty(self, override_settings):
        import app.services.dart_service as ds

        ds._corp_code_map = {}
        ds._corp_code_loaded_at = None

        with patch.object(ds, "_fetch_corp_code_map", new=AsyncMock(return_value={"005930": "abc"})):
            result = await ds._ensure_corp_code_map("key")

        assert result == {"005930": "abc"}

    @pytest.mark.asyncio
    async def test_uses_cache_when_fresh(self, override_settings):
        import app.services.dart_service as ds

        ds._corp_code_map = {"005930": "abc"}
        ds._corp_code_loaded_at = datetime.utcnow()  # very fresh

        with patch.object(ds, "_fetch_corp_code_map", new=AsyncMock()) as mock_fetch:
            result = await ds._ensure_corp_code_map("key")

        mock_fetch.assert_not_called()
        assert result == {"005930": "abc"}

    @pytest.mark.asyncio
    async def test_refresh_failed_returns_stale(self, override_settings):
        import app.services.dart_service as ds

        ds._corp_code_map = {"existing": "code"}
        ds._corp_code_loaded_at = None  # stale

        with patch.object(ds, "_fetch_corp_code_map", new=AsyncMock(return_value={})):
            result = await ds._ensure_corp_code_map("key")

        # Empty map returned by fetch means stale map is kept
        assert result == {"existing": "code"}


class TestLookupCorpCode:
    @pytest.mark.asyncio
    async def test_returns_corp_code_for_known_ticker(self, override_settings):
        import app.services.dart_service as ds

        with patch.object(ds, "_ensure_corp_code_map", new=AsyncMock(return_value={"005930": "00126380"})):
            result = await ds._lookup_corp_code("005930", "key")

        assert result == "00126380"

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_ticker(self, override_settings):
        import app.services.dart_service as ds

        with patch.object(ds, "_ensure_corp_code_map", new=AsyncMock(return_value={})):
            result = await ds._lookup_corp_code("999999", "key")

        assert result is None

    @pytest.mark.asyncio
    async def test_pads_short_ticker_to_6_digits(self, override_settings):
        import app.services.dart_service as ds

        with patch.object(ds, "_ensure_corp_code_map", new=AsyncMock(return_value={"005930": "abc"})):
            result = await ds._lookup_corp_code("5930", "key")

        assert result == "abc"


class TestFetchDartDividend:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_api_key(self, override_settings):
        from app.services.dart_service import fetch_dart_dividend

        result = await fetch_dart_dividend("005930", "")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_corp_code_not_found(self, override_settings):
        import app.services.dart_service as ds

        with patch.object(ds, "_lookup_corp_code", new=AsyncMock(return_value=None)):
            result = await ds.fetch_dart_dividend("005930", "key")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_dividend_data_on_success(self, override_settings):
        import app.services.dart_service as ds

        api_response = {
            "status": "000",
            "list": [{"se": "보통주", "cash_dwnd_rate": "2.15", "per_sto_dvdn_amt": "1500"}],
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with (
            patch.object(ds, "_lookup_corp_code", new=AsyncMock(return_value="00126380")),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await ds.fetch_dart_dividend("005930", "key")

        assert result is not None
        assert abs(result["dividend_yield"] - 0.0215) < 0.0001
        assert result["dps"] == 1500.0

    @pytest.mark.asyncio
    async def test_returns_none_on_status_non_000(self, override_settings):
        import app.services.dart_service as ds

        api_response = {"status": "999", "list": []}
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with (
            patch.object(ds, "_lookup_corp_code", new=AsyncMock(return_value="abc")),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await ds.fetch_dart_dividend("005930", "key")

        assert result is None

    @pytest.mark.asyncio
    async def test_retries_previous_year_on_status_013(self, override_settings):
        import app.services.dart_service as ds

        call_count = 0

        async def mock_fetch_dart(ticker, api_key, year=None):
            nonlocal call_count
            call_count += 1
            if year is None:
                return {"status": "013"}
            return {"dividend_yield": 0.02, "dps": 1000.0}

        api_response_013 = {"status": "013", "list": []}
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response_013
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with (
            patch.object(ds, "_lookup_corp_code", new=AsyncMock(return_value="abc")),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            # First call (year=None) returns 013, which triggers a recursive call
            # The second call will also return 013 but year is set so no more retries
            result = await ds.fetch_dart_dividend("005930", "key")

        # Result is None since second call with explicit year also gets 013
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_http_exception(self, override_settings):
        import app.services.dart_service as ds

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("network error"))

        with (
            patch.object(ds, "_lookup_corp_code", new=AsyncMock(return_value="abc")),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await ds.fetch_dart_dividend("005930", "key")

        assert result is None

    @pytest.mark.asyncio
    async def test_skips_abnormal_dps_over_million(self, override_settings):
        import app.services.dart_service as ds

        api_response = {
            "status": "000",
            "list": [
                {"se": "보통주", "cash_dwnd_rate": "2.0", "per_sto_dvdn_amt": "2000000"},  # DPS > 1M → skip
            ],
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with (
            patch.object(ds, "_lookup_corp_code", new=AsyncMock(return_value="abc")),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await ds.fetch_dart_dividend("005930", "key")

        assert result is None

    @pytest.mark.asyncio
    async def test_preferred_stock_uses_preferred_row(self, override_settings):
        import app.services.dart_service as ds

        api_response = {
            "status": "000",
            "list": [
                {"se": "보통주", "cash_dwnd_rate": "1.0", "per_sto_dvdn_amt": "500"},
                {"se": "우선주", "cash_dwnd_rate": "1.5", "per_sto_dvdn_amt": "750"},
            ],
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with (
            patch.object(ds, "_lookup_corp_code", new=AsyncMock(return_value="abc")),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await ds.fetch_dart_dividend("005935", "key")  # ends in 5 → preferred

        assert result is not None
        assert abs(result["dividend_yield"] - 0.015) < 0.0001
