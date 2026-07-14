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


class IsaType(StrEnum):
    GENERAL = "GENERAL"  # 일반형 — 비과세 한도 200만원
    PREFERENTIAL = "PREFERENTIAL"  # 서민형·농어민형 통합 — 비과세 한도 400만원


class InvestmentHorizon(StrEnum):
    SHORT_TERM = "SHORT_TERM"
    MID_TERM = "MID_TERM"
    LONG_TERM = "LONG_TERM"


class AssetClass(StrEnum):
    """목표 역산 추천 후보 종목의 자산군 — 기간별(단기/중기/장기) 추천 시 후보 필터링에 사용."""

    EQUITY = "EQUITY"
    BOND = "BOND"
    CASH = "CASH"


class IndexRegion(StrEnum):
    """목표 역산 추천 후보 ETF/주식이 추종하는 지수의 지역 — 상장거래소와는 별개 개념.

    예: `133690 TIGER 미국나스닥100`은 KRX(국내) 상장이지만 나스닥100(해외) 지수를 추종한다.
    세제유형별(ISA/연금저축/IRP는 해외지수, 일반은 국내지수) 후보 선호도 필터링에 사용된다.
    """

    DOMESTIC = "DOMESTIC"
    OVERSEAS = "OVERSEAS"
