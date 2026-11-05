"""Konfigurasi koneksi database dari environment variable (+ .env lewat
python-dotenv). Dipakai database/apply_schema.py.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # fine — use raw env vars


@dataclass
class DatabaseConfig:
    host:         str = field(default_factory=lambda: os.getenv("DB_HOST",     "localhost"))
    port:         int = field(default_factory=lambda: int(os.getenv("DB_PORT", "5432")))
    name:         str = field(default_factory=lambda: os.getenv("DB_NAME",     "themonitor"))
    user:         str = field(default_factory=lambda: os.getenv("DB_USER",     "postgres"))
    password:     str = field(default_factory=lambda: os.getenv("DB_PASSWORD", ""))
    pool_size:    int = field(default_factory=lambda: int(os.getenv("DB_POOL_SIZE",    "5")))
    max_overflow: int = field(default_factory=lambda: int(os.getenv("DB_MAX_OVERFLOW", "10")))
    echo:         bool = field(default_factory=lambda: os.getenv("DB_ECHO", "false").lower() == "true")

    @property
    def url(self) -> str:
        return f"postgresql+psycopg2://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
