import json

import httpx
import pytest

from backend import workflow
from backend.page_cases import cases, routes
from backend.source_files import apply_changes


def test_file_patch_keeps_unmentioned_sources_and_rejects_missing_entry():
    base = {"index.html": "<body>Home</body>", "app.js": "let count = 0;", "styles.css": "body {color: red}"}
    files, html = apply_changes(base, {"styles.css": "body {color: blue}"})
    assert files["app.js"] == base["app.js"]
    assert "color: red" not in html
    assert "color: blue" in html and "let count = 0;" in html
    with pytest.raises(ValueError):
        apply_changes(base, {"index.html": None})


@pytest.mark.asyncio
async def test_secondary_route_failure_blocks_browser_pass(monkeypatch):
    declared = routes([{"path": "/"}, {"path": "/items"}])
    page_cases = cases([{"path": "/items", "state": "empty", "tests": []}], declared, [])
    requests = []
    artifacts = []

    def run(request):
        data = json.loads(request.content)
        requests.append((data["route"], data["state"]))
        return httpx.Response(200, json={"passed": data["route"] == "/", "screenshot": "fixture"})

    client = httpx.AsyncClient
    monkeypatch.setattr(workflow.httpx, "AsyncClient", lambda **kw: client(transport=httpx.MockTransport(run), **kw))
    monkeypatch.setattr(workflow, "artifact", lambda tid, kind, content: artifacts.append((kind, content)) or kind)
    result = await workflow.validate({"task_id": "task", "code_id": "code", "html": "<p>page</p>", "demo": False, "page_cases": page_cases})
    assert requests == [("/", "initial"), ("/items", "initial"), ("/items", "empty")]
    assert not result["passed"] and not result["feedback"]["browser_passed"]
    assert len([content for kind, content in artifacts if kind == "screenshot"]) == 3


def test_visual_model_object_coordinates_are_normalized():
    from backend.design_spec import normalize

    spec = normalize({"sections": [{"id": "hero", "label": "首页", "elements": [
        {"id": "game", "role": "canvas", "bounds": {"x": .3, "y": .2, "w": .5, "h": .4}}
    ]}]})
    assert spec["sections"][0]["elements"][0]["bounds"] == (.3, .2, .5, .4)
