from __future__ import annotations

from collections.abc import Generator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.config import ROOT_DIR, Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        mock_data_dir=ROOT_DIR / "mock-data",
        llm_mode="mock",
        demo_today=date(2026, 10, 26),
        deepseek_api_key=None,
    )


@pytest.fixture
def client(settings: Settings) -> Generator[TestClient, None, None]:
    application = create_app(settings)
    with TestClient(application) as test_client:
        yield test_client

