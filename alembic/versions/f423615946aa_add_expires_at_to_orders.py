"""add expires_at to orders

Revision ID: f423615946aa
Revises: 0b72d32efc6a
Create Date: 2026-04-07 15:42:58.789723

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f423615946aa"
down_revision: Union[str, Sequence[str], None] = "0b72d32efc6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "orders", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("orders", "expires_at")
    # ### end Alembic commands ###
