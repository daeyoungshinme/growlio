"""merge_account_ids_and_per_account_kis

Revision ID: 18bc774cd76e
Revises: a2b3c4d5e6f7, h1i2j3k4l5m6
Create Date: 2026-05-24 18:06:06.393874

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "18bc774cd76e"
down_revision: str | None = ("a2b3c4d5e6f7", "h1i2j3k4l5m6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
