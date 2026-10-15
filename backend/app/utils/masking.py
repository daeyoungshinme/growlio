"""로그·외부 보고용 개인정보 마스킹."""


def mask_account_no(account_no: str | None) -> str:
    """계좌번호는 뒤 4자리만 남긴다 — 로그로 계좌를 구분할 수는 있되 전체 번호는 남기지 않는다."""
    digits = (account_no or "").strip()
    if len(digits) <= 4:
        return "*" * len(digits)
    return "*" * (len(digits) - 4) + digits[-4:]


def mask_email(email: str | None) -> str:
    """이메일 로컬파트를 첫 글자만 남긴다 (a***@example.com)."""
    local, sep, domain = (email or "").partition("@")
    if not sep:
        return "***"
    return f"{local[:1]}***@{domain}"
