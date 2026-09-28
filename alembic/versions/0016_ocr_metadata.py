"""OCR metadata on documents.

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("ocr_pages", sa.Integer()))
    op.add_column("documents", sa.Column("ocr_confidence", sa.Float()))
    # content address of the derived OCR copy (invisible text layer), when one exists
    op.add_column("documents", sa.Column("searchable_sha256", sa.Text()))


def downgrade() -> None:
    op.drop_column("documents", "searchable_sha256")
    op.drop_column("documents", "ocr_confidence")
    op.drop_column("documents", "ocr_pages")
