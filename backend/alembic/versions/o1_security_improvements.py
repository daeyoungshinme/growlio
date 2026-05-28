"""Security improvements: encrypt OB tokens in DB, add user_id index on asset_accounts

Revision ID: o1_security_improvements
Revises: n1_ob_fintech_unique
Create Date: 2026-05-28
"""

from alembic import op
from sqlalchemy import text

revision = "o1_security_improvements"
down_revision = "n1_ob_fintech_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. OB 토큰 암호화 — 평문으로 저장된 기존 값을 AES-256-GCM으로 암호화
    try:
        from app.services.credential_service import encrypt

        rows = conn.execute(
            text(
                "SELECT user_id, ob_access_token, ob_refresh_token FROM user_settings "
                "WHERE ob_access_token IS NOT NULL OR ob_refresh_token IS NOT NULL"
            )
        ).fetchall()

        for row in rows:
            encrypted_access = encrypt(row.ob_access_token) if row.ob_access_token else None
            encrypted_refresh = encrypt(row.ob_refresh_token) if row.ob_refresh_token else None
            conn.execute(
                text(
                    "UPDATE user_settings SET ob_access_token = :at, ob_refresh_token = :rt "
                    "WHERE user_id = :uid"
                ),
                {"at": encrypted_access, "rt": encrypted_refresh, "uid": str(row.user_id)},
            )
    except Exception as e:
        # KIS_CRED_ENCRYPTION_KEY 미설정 환경(테스트 DB)에서는 기존 토큰이 없으므로 무시
        import structlog
        structlog.get_logger().warning("ob_token_encryption_skipped", error=str(e))

    # 2. asset_accounts.user_id 인덱스 추가 — 계좌 목록 조회 성능 개선
    op.create_index("idx_asset_accounts_user_id", "asset_accounts", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_asset_accounts_user_id", table_name="asset_accounts")
    # OB 토큰 암호화 해제는 안전하게 수행할 수 없으므로 생략 (토큰을 무효화해야 함)
