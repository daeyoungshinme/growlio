"""계좌 KIS/키움/토스 자격증명 검증·삭제 — assets.py 라우터에서 분리된 서비스 레이어.

credential_service.py(AES-256 암복호화 순수 유틸)와 책임 레벨이 다르다 — 이 모듈은
계좌 상태 변경(토큰 삭제·캐시 무효화)과 브로커 API 호출(검증)을 포함하는 유스케이스를 담당한다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.kis.auth import ACCOUNT_TOKEN_CACHE_KEY as KIS_ACCOUNT_TOKEN_CACHE_KEY
from app.kiwoom.constants import KIWOOM_TOKEN_CACHE_KEY
from app.models.asset import AssetAccount
from app.models.token import KisToken, KiwoomToken, TossToken
from app.toss.constants import TOSS_TOKEN_CACHE_KEY
from app.utils.cache_keys import account_detail_key, invalidate_user_caches


async def verify_kis_credentials(
    kis_app_key: str,
    kis_app_secret: str,
    is_mock: bool,
    user_id: uuid.UUID,
    cache,
) -> None:
    """KIS 자격증명 유효성을 확인한다 (계좌 생성 없이). 실패 시 httpx 예외를 그대로 전파한다.

    요청 스코프 세션이 아닌 별도의 짧게 스코프된 세션을 사용한다 — KIS OAuth HTTP 호출 동안
    요청의 DB 커넥션 풀 슬롯을 오래 붙잡지 않기 위함.
    """
    from app.kis.auth import _fetch_and_store_token

    async with AsyncSessionLocal() as db:
        await _fetch_and_store_token(
            kis_app_key,
            kis_app_secret,
            is_mock=is_mock,
            cache=cache,
            db=db,
            user_id=str(user_id),
            account_id=None,
        )


async def verify_kiwoom_credentials(kiwoom_app_key: str, kiwoom_app_secret: str, is_mock: bool) -> None:
    """키움 자격증명 유효성을 확인한다 (계좌 생성/토큰 저장 없이). 실패 시 예외를 그대로 전파한다.

    키움 토큰은 계좌 단위로만 저장되므로(전역 자격증명 없음) KIS와 달리 DB 세션 없이 발급 API만 호출한다.
    """
    from app.kiwoom.auth import verify_credentials

    await verify_credentials(kiwoom_app_key, kiwoom_app_secret, is_mock=is_mock)


async def verify_toss_credentials(toss_client_id: str, toss_client_secret: str) -> None:
    """토스 자격증명 유효성을 확인한다 (계좌 생성/토큰 저장 없이). 실패 시 예외를 그대로 전파한다."""
    from app.toss.auth import verify_credentials

    await verify_credentials(toss_client_id, toss_client_secret)


@dataclass(frozen=True)
class BrokerCredentialSpec:
    """브로커별 계좌 자격증명 스펙 — assets 라우터의 생성/수정/응답/삭제가 이 테이블만 보고 동작한다.

    검증(verify)은 요청 스키마·함수 시그니처·브로커 고유 에러가 달라 브로커별 라우트로 남긴다.
    """

    data_source: str
    key_attr: str  # AssetAccount/요청 스키마 공통 필드명 (암호화 저장)
    secret_attr: str
    has_own_attr: str  # AssetAccountResponse의 계좌별 키 보유 플래그
    # 생성 시 라우터가 필수로 확인하는 계좌번호 필드. KIS는 스키마 validator가 형식까지 검증하므로 None.
    required_account_no_attr: str | None
    forced_asset_type: str | None  # 생성 시 강제 asset_type (KIS는 요청값 유지)
    missing_detail: str  # 생성 시 필수값 누락 400 메시지
    token_model: type[KisToken] | type[KiwoomToken] | type[TossToken]
    token_cache_key: str  # "{account_id}" 템플릿

    @property
    def credential_attrs(self) -> tuple[str, str]:
        return (self.key_attr, self.secret_attr)


BROKER_CREDENTIAL_SPECS: dict[str, BrokerCredentialSpec] = {
    spec.data_source: spec
    for spec in (
        BrokerCredentialSpec(
            data_source="KIS_API",
            key_attr="kis_app_key",
            secret_attr="kis_app_secret",  # nosec B106 — 속성명 문자열, 비밀번호 아님
            has_own_attr="has_own_kis_credentials",
            required_account_no_attr=None,
            forced_asset_type=None,
            missing_detail="KIS API 자격증명(App Key, App Secret)을 모두 입력하세요.",
            token_model=KisToken,
            token_cache_key=KIS_ACCOUNT_TOKEN_CACHE_KEY,
        ),
        BrokerCredentialSpec(
            data_source="KIWOOM_API",
            key_attr="kiwoom_app_key",
            secret_attr="kiwoom_app_secret",  # nosec B106 — 속성명 문자열, 비밀번호 아님
            has_own_attr="has_own_kiwoom_credentials",
            required_account_no_attr="kiwoom_account_no",
            forced_asset_type="STOCK_KIWOOM",
            missing_detail="키움 계좌번호와 API 자격증명(App Key, App Secret)을 모두 입력하세요.",
            token_model=KiwoomToken,
            token_cache_key=KIWOOM_TOKEN_CACHE_KEY,
        ),
        BrokerCredentialSpec(
            data_source="TOSS_API",
            key_attr="toss_client_id",
            secret_attr="toss_client_secret",  # nosec B106 — 속성명 문자열, 비밀번호 아님
            has_own_attr="has_own_toss_credentials",
            required_account_no_attr="toss_account_no",
            forced_asset_type="STOCK_TOSS",
            missing_detail="토스 계좌번호와 API 자격증명(Client ID, Client Secret)을 모두 입력하세요.",
            token_model=TossToken,
            token_cache_key=TOSS_TOKEN_CACHE_KEY,
        ),
    )
}

# 요청 스키마에서 평문으로 들어오는 자격증명 필드 전체 — model_dump 시 제외하고 암호화해 따로 저장한다
CREDENTIAL_FIELDS: set[str] = set(attr for spec in BROKER_CREDENTIAL_SPECS.values() for attr in spec.credential_attrs)


async def delete_credentials(account: AssetAccount, db: AsyncSession, cache, spec: BrokerCredentialSpec) -> None:
    """계좌별 브로커 자격증명과 발급 토큰(DB·캐시)을 삭제한다. KIS는 이후 전역 자격증명으로 폴백된다."""
    setattr(account, spec.key_attr, None)
    setattr(account, spec.secret_attr, None)
    token_model = spec.token_model
    await db.execute(sql_delete(token_model).where(token_model.account_id == account.id))
    await db.commit()

    await cache.delete(spec.token_cache_key.format(account_id=account.id))
    await invalidate_user_caches(cache, account_detail_key(account.user_id, account.id))
