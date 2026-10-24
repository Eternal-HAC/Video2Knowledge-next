"""Request-boundary tests use ASGI messages, never a live login or provider."""
import asyncio
import importlib
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.fixture
def main(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO2KNOWLEDGE_WORKSPACE", str(tmp_path / "workspace"))
    with patch("dotenv.load_dotenv", return_value=False):
        return importlib.import_module("backend.main")


def invoke(app, headers, *, client=("127.0.0.1", 45678), method="POST",
           path="/api/douyin-login/start", scheme="http", body=b"payload"):
    messages, reads = [], []
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
             "method": method, "scheme": scheme, "path": path, "raw_path": path.encode(),
             "root_path": "", "query_string": b"", "headers": headers,
             "client": client, "server": ("127.0.0.1", 18755)}

    async def receive():
        reads.append(True)
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))
    return messages, reads


HOST = (b"host", b"127.0.0.1:18755")


@pytest.mark.parametrize("headers,status", [
    ([], 400),
    ([(b"host", b"untrusted.example")], 400),
    ([HOST, HOST], 400),
    ([(b"host", b"localhost.evil.example")], 400),
    ([(b"host", b"localhost.")], 400),
    ([(b"host", b"127.1")], 400),
    ([(b"host", b"127.0.0.2")], 400),
    ([(b"host", b"127.0.0.1:0")], 400),
    ([(b"host", b"127.0.0.1:65536")], 400),
    ([(b"host", b"127.0.0.1:")], 400),
    ([(b"host", b"user@localhost")], 400),
    ([(b"host", b"localhost/path")], 400),
    ([(b"host", b" localhost")], 400),
    ([(b"host", b"localhost\x00")], 400),
    ([(b"host", b"[::01]")], 400),
    ([(b"host", b"::1")], 400),
    ([HOST, (b"origin", b"http://untrusted.example")], 403),
    ([HOST, (b"origin", b"null")], 403),
    ([HOST, (b"origin", b"http://127.0.0.1:18756")], 403),
    ([HOST, (b"origin", b"https://127.0.0.1:18755")], 403),
    ([HOST, (b"origin", b"http://localhost:18755")], 403),
    ([HOST, (b"origin", b"http://127.0.0.1:18755/")], 403),
    ([HOST, (b"origin", b"http://127.0.0.1:18755?")], 403),
    ([HOST, (b"origin", b"http://127.0.0.1:18755#")], 403),
    ([HOST, (b"origin", b"http://u@127.0.0.1:18755")], 403),
    ([HOST, (b"origin", b"http://127.0.0.1:18755"), (b"origin", b"null")], 403),
    ([HOST, (b"origin", b"")], 403),
    ([HOST, (b"origin", b"http://127.0.0.1:18755 http://untrusted.example")], 403),
    ([HOST, (b"origin", b"http://127.0.0.1:18755\t")], 403),
    ([HOST, (b"origin", b"http://127.0.0.1:18755"), (b"sec-fetch-site", b"cross-site")], 403),
    ([(b"host", b"localhost:\xff")], 400),
    ([HOST, (b"origin", b"\xff")], 403),
    ([HOST, (b"sec-fetch-site", b"cross-site")], 403),
    ([HOST, (b"sec-fetch-site", b"same-site")], 403),
    ([HOST, (b"sec-fetch-site", b"nonsense")], 403),
    ([HOST, (b"sec-fetch-site", b"same-origin"), (b"sec-fetch-site", b"none")], 403),
])
@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def test_bad_headers_rejected_before_body_or_business(main, headers, status, method):
    async def forbidden(*args):
        pytest.fail("untrusted request reached business code")

    messages, reads = invoke(main.LocalSecurityMiddleware(forbidden), headers, method=method)
    assert not reads
    assert messages[0]["status"] == status
    assert len([m for m in messages if m["type"] == "http.response.start"]) == 1
    response_headers = dict(messages[0]["headers"])
    assert b"content-security-policy" in response_headers
    assert b"access-control-allow-origin" not in response_headers
    payload = json.loads(messages[1]["body"])
    assert list(payload) == ["detail"]
    assert "untrusted" not in payload["detail"]


@pytest.mark.parametrize("peer", [None, ("", 1), ("192.0.2.1", 1), ("testclient", 1)])
def test_missing_or_remote_peer_fails_closed(main, peer):
    async def forbidden(*args):
        pytest.fail("unknown peer reached business code")
    messages, reads = invoke(main.LocalSecurityMiddleware(forbidden), [HOST], client=peer)
    assert messages[0]["status"] == 403 and not reads


@pytest.mark.parametrize("host,origin,scheme", [
    ("127.0.0.1:18755", None, "http"),
    ("localhost:18755", "http://LOCALHOST:18755", "http"),
    ("LOCALHOST:18755", "http://localhost:18755", "http"),
    ("[::1]:18755", "http://[::1]:18755", "http"),
    ("127.0.0.1", "http://127.0.0.1:80", "http"),
    ("localhost:443", "https://localhost", "https"),
])
@pytest.mark.parametrize("metadata", [None, "same-origin", "none"])
def test_native_and_same_origin_streams_untouched(main, host, origin, scheme, metadata):
    headers = [(b"host", host.encode())]
    if origin is not None:
        headers.append((b"origin", origin.encode()))
    if metadata is not None:
        headers.append((b"sec-fetch-site", metadata.encode()))

    async def stream(scope, receive, send):
        assert (await receive())["body"] == b"payload"
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/event-stream")]})
        await send({"type": "http.response.body", "body": b"event: one\n\n", "more_body": True})
        await send({"type": "http.response.body", "body": b"event: two\n\n", "more_body": False})

    messages, reads = invoke(main.LocalSecurityMiddleware(stream), headers, path="/mcp/sse", scheme=scheme)
    assert len(reads) == 1 and messages[0]["status"] == 200
    assert [m["body"] for m in messages[1:]] == [b"event: one\n\n", b"event: two\n\n"]


@pytest.mark.parametrize("path", ["/", "/script.js"])
def test_foreign_navigation_to_page_allowed(main, path):
    async def page(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"page"})
    messages, _ = invoke(main.LocalSecurityMiddleware(page),
                         [HOST, (b"sec-fetch-site", b"cross-site")], method="GET", path=path)
    assert messages[0]["status"] == 200


def test_real_login_route_rejects_before_stub(main, monkeypatch):
    async def forbidden():
        pytest.fail("foreign request reached login")
    monkeypatch.setattr(main, "douyin_login_manager", SimpleNamespace(start=forbidden))
    messages, reads = invoke(main.app, [HOST, (b"origin", b"http://untrusted.example")], body=b"")
    assert messages[0]["status"] == 403 and not reads


@pytest.mark.parametrize("path", ["/api", "/api/tasks", "/mcp", "/mcp/sse", "/mcp/messages/"])
@pytest.mark.parametrize("site", [b"same-site", b"cross-site"])
def test_all_api_and_mcp_paths_reject_cross_source_without_origin(main, path, site):
    async def forbidden(*args):
        pytest.fail("cross-source request reached protected route")
    messages, reads = invoke(main.LocalSecurityMiddleware(forbidden),
                             [HOST, (b"sec-fetch-site", site)], path=path)
    assert messages[0]["status"] == 403 and not reads


def test_proxy_headers_cannot_authorize_foreign_origin(main):
    async def forbidden(*args):
        pytest.fail("proxy headers authorized a foreign origin")
    messages, _ = invoke(main.LocalSecurityMiddleware(forbidden), [
        HOST, (b"origin", b"https://untrusted.example"),
        (b"x-forwarded-host", b"untrusted.example"), (b"x-forwarded-proto", b"https"),
        (b"forwarded", b"host=untrusted.example;proto=https"), (b"sec-fetch-site", b"same-origin"),
    ])
    assert messages[0]["status"] == 403


def test_invalid_host_precedes_origin_rejection(main):
    async def forbidden(*args):
        pytest.fail("invalid host reached business code")
    messages, reads = invoke(main.LocalSecurityMiddleware(forbidden),
                             [(b"host", b"untrusted.example"), (b"origin", b"http://other.example")])
    assert messages[0]["status"] == 400 and not reads


def test_business_error_and_existing_security_header_unchanged(main):
    async def business(scope, receive, send):
        await send({"type": "http.response.start", "status": 400,
                    "headers": [(b"content-security-policy", b"default-src 'none'")]})
        await send({"type": "http.response.body", "body": b"business error"})
    messages, _ = invoke(main.LocalSecurityMiddleware(business), [HOST])
    assert messages[0]["status"] == 400 and messages[1]["body"] == b"business error"
    assert [v for k, v in messages[0]["headers"] if k == b"content-security-policy"] == [b"default-src 'none'"]


def test_default_testserver_is_not_a_product_allowlist(main):
    from fastapi.testclient import TestClient
    with TestClient(main.app, client=("127.0.0.1", 50000)) as client:
        assert client.get("/api/health").status_code == 400


@pytest.mark.parametrize("peer", ["127.0.0.1", "::1", "::ffff:127.0.0.1"])
def test_real_loopback_peers_preserved(main, peer):
    async def okay(scope, receive, send):
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})
    messages, _ = invoke(main.LocalSecurityMiddleware(okay), [HOST], client=(peer, 50000))
    assert messages[0]["status"] == 204


def test_disconnect_and_cancellation_propagate(main):
    async def exercise():
        scope = {"type": "http", "headers": [HOST], "scheme": "http", "path": "/mcp/sse",
                 "client": ("127.0.0.1", 50000)}
        events = []

        async def receive():
            return {"type": "http.disconnect"}

        async def send(message):
            events.append(message)

        async def stream(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            assert (await receive())["type"] == "http.disconnect"
            raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await main.LocalSecurityMiddleware(stream)(scope, receive, send)
        assert len(events) == 1

    asyncio.run(exercise())


def test_launcher_disables_forwarded_header_trust(main, monkeypatch):
    import launcher
    monkeypatch.setattr(launcher, "set_env_aliases", lambda *args: None)
    monkeypatch.setattr(launcher.threading, "Thread", lambda **kwargs: SimpleNamespace(start=lambda: None))
    server, _ = launcher.start_server(18755)
    assert server.config.proxy_headers is False


def test_module_entry_disables_forwarded_header_trust():
    import ast
    from pathlib import Path
    tree = ast.parse((Path(__file__).resolve().parents[1] / "backend/main.py").read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
             and node.func.value.id == "uvicorn" and node.func.attr == "run"]
    assert len(calls) == 1
    assert any(key.arg == "proxy_headers" and isinstance(key.value, ast.Constant)
               and key.value.value is False for key in calls[0].keywords)
