"""Apply runtime grants after migration; never print connection credentials."""

import os
from pathlib import Path

import psycopg

if __name__ == "__main__":
    dsn = os.environ["DATABASE_URL_SYNC"].replace("postgresql+psycopg:", "postgresql:")
    with psycopg.connect(dsn) as connection:
        connection.execute((Path(__file__).parents[1] / "db/runtime-grants.sql").read_text())
    print("Runtime grants applied.")
