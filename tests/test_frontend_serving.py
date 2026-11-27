"""
Tests for serving the built React app from FastAPI.

Each test builds a small stand-in for frontend/dist in a temporary folder and
a fresh app with one API route, so the real build is never needed.
"""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import main as api

INDEX_PAGE = "<!doctype html><title>Discovery</title><div id=root></div>"
APP_SCRIPT = "console.log('app');"


def _app_with_api_route() -> FastAPI:
    test_app = FastAPI()

    @test_app.get("/api/health")
    def health():
        return {"status": "ok"}

    return test_app


@pytest.fixture
def build_folder(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_PAGE)
    (dist / "assets" / "index-abc123.js").write_text(APP_SCRIPT)
    (dist / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    # Something outside the build that must never be served.
    (tmp_path / "secret.txt").write_text("do not serve")
    return dist


@pytest.fixture
def client(build_folder):
    test_app = _app_with_api_route()
    assert api.serve_frontend(test_app, build_folder) is True
    return TestClient(test_app)


def test_root_serves_the_app(client):
    page = client.get("/")
    assert page.status_code == 200
    assert page.text == INDEX_PAGE
    assert page.headers["content-type"].startswith("text/html")


def test_built_files_are_served_with_their_types(client):
    script = client.get("/assets/index-abc123.js")
    assert script.text == APP_SCRIPT
    assert "javascript" in script.headers["content-type"]
    assert client.get("/favicon.svg").headers["content-type"].startswith("image/svg")


def test_any_other_page_path_loads_the_app_for_client_side_routing(client):
    for page_path in ("/assets-page", "/asset/AAPL", "/deep/link/with/parts"):
        page = client.get(page_path)
        assert page.status_code == 200
        assert page.text == INDEX_PAGE


def test_api_routes_still_answer_with_json(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_unknown_api_paths_stay_json_404s_not_the_page(client):
    for missing_path in ("/api", "/api/nope", "/api/assets/ZZZ/whatever"):
        missing = client.get(missing_path)
        assert missing.status_code == 404
        assert missing.json() == {"detail": "Not Found"}


def test_paths_cannot_climb_out_of_the_build(client):
    escaped = client.get("/..%2Fsecret.txt")
    assert "do not serve" not in escaped.text
    assert escaped.text == INDEX_PAGE


def test_without_a_build_the_api_runs_and_warns_once(tmp_path, caplog):
    test_app = _app_with_api_route()
    with caplog.at_level(logging.WARNING, logger="api"):
        assert api.serve_frontend(test_app, tmp_path / "no_build_here") is False
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "no built frontend" in warnings[0].getMessage()

    without_build = TestClient(test_app)
    assert without_build.get("/api/health").json() == {"status": "ok"}
    assert without_build.get("/").status_code == 404


def test_the_real_app_keeps_its_api_and_docs_ahead_of_the_page():
    real_client = TestClient(api.app)
    assert real_client.get("/openapi.json").json()["info"]["title"] == "Investment Discovery Engine"
    assert "swagger" in real_client.get("/docs").text.lower()
    assert real_client.get("/api/nope").status_code == 404
