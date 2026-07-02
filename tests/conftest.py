"""Shared pytest fixtures. Everything runs in forced offline/mock mode against a
temporary home directory so tests never touch real APIs or the real database."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from mark import store
from mark.app import get_app
from mark.config import ProductConfig

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app(tmp_path, monkeypatch):
    for key in ("OPENAI_API_KEY", "FAL_KEY", "UPLOAD_POST_API_KEY", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    shutil.copytree(REPO_ROOT / "config", tmp_path / "config")
    a = get_app(home=tmp_path, force_mock=True)
    product = ProductConfig(
        id="testco", name="TestCo",
        description="A tool that automates boring repetitive work for builders.",
        target_audience="indie builders who ship side projects",
        brand_voice="casual, punchy, no corporate-speak",
        website_url="https://testco.example",
        platforms=["instagram", "x", "linkedin"],
        posting_cadence={"instagram": 1, "x": 1, "linkedin": 1},
    )
    store.upsert_product(a.conn, product, active=True)
    yield a
    a.close()


@pytest.fixture
def llm(app):
    from mark.llm import LLM

    return LLM(app)


@pytest.fixture
def product(app):
    return store.get_active_product(app.conn)
