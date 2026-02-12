"""add_password_hash_email_rename_display_name

Revision ID: 8545f46a563d
Revises:
Create Date: 2026-02-13 03:57:59.764715
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '8545f46a563d'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename display_name -> username
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("display_name", new_column_name="username")
        batch_op.create_unique_constraint("uq_users_username", ["username"])
        batch_op.add_column(sa.Column("email", sa.String(256), nullable=True))
        batch_op.create_unique_constraint("uq_users_email", ["email"])
        batch_op.add_column(sa.Column("password_hash", sa.String(128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("password_hash")
        batch_op.drop_constraint("uq_users_email", type_="unique")
        batch_op.drop_column("email")
        batch_op.drop_constraint("uq_users_username", type_="unique")
        batch_op.alter_column("username", new_column_name="display_name")
