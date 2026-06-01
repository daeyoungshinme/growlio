"""앱 전용 예외 클래스. 서비스 레이어에서 raise → API 레이어에서 HTTPException으로 변환."""
from __future__ import annotations


class AppError(Exception):
    """기본 앱 예외. status_code와 detail을 지정하면 전역 핸들러가 HTTP 응답으로 변환."""
    status_code: int = 500
    detail: str = "서버 오류가 발생했습니다."

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.__class__.detail
        super().__init__(self.detail)


class BadRequestError(AppError):
    status_code = 400
    detail = "잘못된 요청입니다."


class NotFoundError(AppError):
    status_code = 404
    detail = "리소스를 찾을 수 없습니다."


class CredentialMissingError(BadRequestError):
    detail = "자격증명이 설정되지 않았습니다."


class ExternalAPIError(AppError):
    status_code = 502
    detail = "외부 API 오류가 발생했습니다"


class RateLimitError(AppError):
    status_code = 429
    detail = "요청이 너무 많습니다. 잠시 후 다시 시도하세요"


class ConflictError(AppError):
    status_code = 409
    detail = "이미 존재하는 리소스입니다"


class PortfolioNotFoundError(NotFoundError):
    detail = "포트폴리오를 찾을 수 없습니다"


class AccountNotFoundError(NotFoundError):
    detail = "계좌를 찾을 수 없습니다"


class AlertNotFoundError(NotFoundError):
    detail = "알림을 찾을 수 없습니다"


class TransactionNotFoundError(NotFoundError):
    detail = "거래 내역을 찾을 수 없습니다"


class KisAuthError(ExternalAPIError):
    status_code = 401
    detail = "KIS 인증에 실패했습니다. 자격증명을 확인하세요"


class KiwoomAuthError(ExternalAPIError):
    status_code = 401
    detail = "키움 인증에 실패했습니다. 자격증명을 확인하세요"


# ── 증권사 동기화 오류 계층 ─────────────────────────────────────────────────────
# asset_service / BrokerProvider 구현체에서 raise → API 레이어에서 HTTPException 변환

class SyncError(Exception):
    """증권사 동기화 최상위 예외."""


class ProviderCredentialError(SyncError):
    """자격증명 누락 또는 불일치."""


class ProviderTokenError(SyncError):
    """토큰 만료/발급 실패."""


class ProviderApiError(SyncError):
    """증권사 API가 비정상 응답을 반환."""

    def __init__(self, detail: str, http_status: int = 400) -> None:
        self.detail = detail
        self.http_status = http_status
        super().__init__(detail)


class ProviderNetworkError(SyncError):
    """연결 실패 또는 타임아웃."""
