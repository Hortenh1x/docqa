"""Root test config: safe env defaults so the suite never depends on a local .env file.

Integration fixtures overwrite these with testcontainer URLs (and clear the settings cache).
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://docqa:docqa@localhost:5433/docqa")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("EMBEDDING_PROVIDER", "stub")
