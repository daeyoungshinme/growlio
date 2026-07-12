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


class GoalRiskTolerance(StrEnum):
    CONSERVATIVE = "CONSERVATIVE"
    BALANCED = "BALANCED"
    AGGRESSIVE = "AGGRESSIVE"


class AccountTaxType(StrEnum):
    GENERAL = "GENERAL"
    ISA = "ISA"
    PENSION_SAVINGS = "PENSION_SAVINGS"
    IRP = "IRP"
    OVERSEAS_DEDICATED = "OVERSEAS_DEDICATED"


class InvestmentHorizon(StrEnum):
    SHORT_TERM = "SHORT_TERM"
    MID_TERM = "MID_TERM"
    LONG_TERM = "LONG_TERM"
