"""도메인 상수 Enum — 모델/서비스 전반의 매직 스트링을 중앙화."""

from enum import StrEnum


class AssetType(StrEnum):
    BANK_ACCOUNT = "BANK_ACCOUNT"
    DEPOSIT = "DEPOSIT"
    STOCK_KIS = "STOCK_KIS"
    STOCK_KIWOOM = "STOCK_KIWOOM"
    STOCK_OTHER = "STOCK_OTHER"
    CASH_OTHER = "CASH_OTHER"
    CASH_STOCK = "CASH_STOCK"
    OTHER = "OTHER"
    REAL_ESTATE = "REAL_ESTATE"


class DataSource(StrEnum):
    MANUAL = "MANUAL"
    KIS_API = "KIS_API"
    KIWOOM_API = "KIWOOM_API"
    OPEN_BANKING = "OPEN_BANKING"


class TransactionType(StrEnum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    DIVIDEND = "DIVIDEND"


class PortfolioBaseType(StrEnum):
    STOCK_ONLY = "STOCK_ONLY"
    TOTAL_ASSETS = "TOTAL_ASSETS"


class AlertDirection(StrEnum):
    ABOVE = "ABOVE"
    BELOW = "BELOW"
