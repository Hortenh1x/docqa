"""Declarative base.

The naming convention is set up front: without it Alembic generates unnamed constraints,
which makes downgrades and later ALTERs painful. ``str`` maps to TEXT (PostgreSQL-idiomatic),
datetimes are always timezone-aware.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, Text, Uuid
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        str: Text(),
        datetime: DateTime(timezone=True),
        uuid.UUID: Uuid(as_uuid=True),
    }
