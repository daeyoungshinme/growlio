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
    detail = "외부 API 오류가 발생했습니다."
