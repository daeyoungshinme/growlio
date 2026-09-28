"""assets 라우터가 의존하는 브로커 자격증명 스펙 테이블의 정합성 테스트."""

from __future__ import annotations

import pytest

from app.enums import DataSource
from app.models.asset import AssetAccount
from app.schemas.asset import AssetAccountCreate, AssetAccountResponse, AssetAccountUpdate
from app.services.asset_credential_service import BROKER_CREDENTIAL_SPECS, CREDENTIAL_FIELDS

_SPECS = list(BROKER_CREDENTIAL_SPECS.values())


def test_covers_every_api_data_source():
    api_sources = {ds.value for ds in DataSource if ds != DataSource.MANUAL}
    assert set(BROKER_CREDENTIAL_SPECS) == api_sources


def test_credential_fields_are_all_key_secret_attrs():
    assert {attr for spec in _SPECS for attr in spec.credential_attrs} == CREDENTIAL_FIELDS
    assert len(CREDENTIAL_FIELDS) == 2 * len(_SPECS)


@pytest.mark.parametrize("spec", _SPECS, ids=lambda s: s.data_source)
def test_spec_attrs_exist_on_model_and_schemas(spec):
    columns = AssetAccount.__table__.columns.keys()
    for attr in spec.credential_attrs:
        assert attr in columns
        assert attr in AssetAccountCreate.model_fields
        assert attr in AssetAccountUpdate.model_fields
    assert spec.has_own_attr in AssetAccountResponse.model_fields
    if spec.required_account_no_attr is not None:
        assert spec.required_account_no_attr in columns
        assert spec.required_account_no_attr in AssetAccountCreate.model_fields
    assert "{account_id}" in spec.token_cache_key
