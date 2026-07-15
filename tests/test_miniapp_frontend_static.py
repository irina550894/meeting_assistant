from fastapi.testclient import TestClient

from app.main import create_app
from app.settings.config import get_settings


def test_miniapp_frontend_static_mount_serves_dist(tmp_path, monkeypatch) -> None:
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=\"root\"></div>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('miniapp');", encoding="utf-8")

    monkeypatch.setenv("MINI_APP_FRONTEND_DIST_PATH", str(dist))
    monkeypatch.setenv("MINI_APP_PUBLIC_PATH", "/miniapp")
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
    finally:
        get_settings.cache_clear()

    index_response = client.get("/miniapp/")
    asset_response = client.get("/miniapp/assets/app.js")

    assert index_response.status_code == 200
    assert "<div id=\"root\"></div>" in index_response.text
    assert asset_response.status_code == 200
    assert "miniapp" in asset_response.text


def test_miniapp_frontend_static_mount_does_not_shadow_api(tmp_path, monkeypatch) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><div id=\"root\"></div>", encoding="utf-8")

    monkeypatch.setenv("MINI_APP_FRONTEND_DIST_PATH", str(dist))
    monkeypatch.setenv("MINI_APP_PUBLIC_PATH", "/miniapp")
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
    finally:
        get_settings.cache_clear()

    response = client.get("/api/miniapp/config")

    assert response.status_code == 200
    assert response.json()["mini_app_public_path"] == "/miniapp"
