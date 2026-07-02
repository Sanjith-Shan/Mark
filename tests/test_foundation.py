"""Config, database, and vector-utility tests."""

import numpy as np

from mark import db, store, vectors
from mark.config import Paths, load_settings


def test_settings_load(app):
    settings = load_settings(Paths(app.paths.home))
    assert "instagram" in settings.platforms
    assert settings.llm.text_model
    assert settings.platform("instagram").enabled


def test_db_json_roundtrip(app):
    cid = store.insert_content(
        app.conn, product_id="testco", platform="x", content_type="text",
        caption="hi", hashtags=["#a", "#b"], hook="hook", media_paths=[], status="draft")
    row = store.get_content(app.conn, cid)
    assert db.loads(row["hashtags"], []) == ["#a", "#b"]
    assert row["status"] == "draft"


def test_product_active_switch(app):
    from mark.config import ProductConfig

    store.upsert_product(app.conn, ProductConfig(
        id="second", name="Second", description="d", target_audience="a",
        brand_voice="b", platforms=["x"], posting_cadence={"x": 1}), active=True)
    assert store.get_active_product(app.conn)["id"] == "second"
    store.set_active_product(app.conn, "testco")
    assert store.get_active_product(app.conn)["id"] == "testco"


def test_vectors_cosine_and_blob():
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    c = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    assert abs(vectors.cosine(a, b) - 1.0) < 1e-6
    assert abs(vectors.cosine(a, c)) < 1e-6
    restored = vectors.from_blob(vectors.to_blob(a))
    assert np.allclose(restored, a)


def test_vectors_top_k():
    q = np.array([1.0, 0.0], dtype=np.float32)
    m = np.array([[1.0, 0.0], [0.0, 1.0], [0.9, 0.1]], dtype=np.float32)
    ranked = vectors.top_k(q, m, 2)
    assert ranked[0][0] == 0  # most similar is the identical row
    assert len(ranked) == 2
