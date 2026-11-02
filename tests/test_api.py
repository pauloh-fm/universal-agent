import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from pydantic import SecretStr

from universal_agent.api import create_app

from .conftest import tool_call


@pytest.fixture
def client(settings, make_runtime):
    rt = make_runtime([tool_call("create_ticket", {"title": "t", "description": "d"}), AIMessage(content="Done.")])
    with TestClient(create_app(settings, runtime=rt)) as c:
        yield c


def test_health_and_agents(client) -> None:
    assert client.get("/health").json()["status"] == "ok"
    names = {a["name"] for a in client.get("/agents").json()["agents"]}
    assert names == {"assistant", "support", "clinic-example", "ecommerce-example"}


def test_approval_flow_over_http(client) -> None:
    r = client.post("/agents/support/threads/u1/messages", json={"message": "open a ticket"})
    assert r.status_code == 200 and r.json()["status"] == "awaiting_approval"
    assert client.post("/agents/support/threads/u1/messages", json={"message": "again"}).status_code == 409
    r = client.post("/agents/support/threads/u1/approval", json={"approved": True})
    assert r.json() == {"status": "completed", "reply": "Done.", "pending_tool_calls": []}
    assert client.post("/agents/support/threads/u1/approval", json={"approved": True}).status_code == 409
    thread = client.get("/agents/support/threads/u1").json()
    assert thread["pending_tool_calls"] == [] and len(thread["messages"]) >= 4


def test_validation(client) -> None:
    assert client.post("/agents/nope/threads/u1/messages", json={"message": "x"}).status_code == 404
    assert client.post("/agents/assistant/threads/bad id!/messages", json={"message": "x"}).status_code == 422
    assert client.post("/agents/assistant/threads/u1/messages", json={"message": ""}).status_code == 422


def test_bearer_token(settings, make_runtime) -> None:
    secured = settings.model_copy(update={"api_token": SecretStr("s3cret")})
    with TestClient(create_app(secured, runtime=make_runtime())) as c:
        assert c.get("/health").status_code == 200
        assert c.get("/agents").status_code == 401
        assert c.get("/agents", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert c.get("/agents", headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_sqlite_persistence(settings, tmp_path) -> None:
    # Real lifespan path: SQLite checkpointer + fake model from settings.
    with TestClient(create_app(settings)) as c:
        r = c.post("/agents/assistant/threads/p1/messages", json={"message": "remember me"})
        assert r.json()["reply"] == "[fake model] You said: remember me"
    with TestClient(create_app(settings)) as c:  # new app, same database
        msgs = c.get("/agents/assistant/threads/p1").json()["messages"]
        assert msgs[0]["content"] == "remember me"
