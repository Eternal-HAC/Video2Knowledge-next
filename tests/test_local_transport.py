"""Real loopback HTTP/SSE integration, using only isolated synthetic artifacts."""
import asyncio
from datetime import timedelta
import importlib
import json
import socket
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client
import pytest
import uvicorn


@pytest.fixture
def live(tmp_path, monkeypatch):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    monkeypatch.setenv('VIDEO2KNOWLEDGE_WORKSPACE', str(workspace))
    with patch('dotenv.load_dotenv', return_value=False):
        main = importlib.import_module('backend.main')
    mcp_server = importlib.import_module('backend.mcp_server')
    monkeypatch.setattr(main, 'WORKSPACE_DIR', workspace)
    monkeypatch.setattr(main, 'tasks', {})
    monkeypatch.setattr(main, 'running_jobs', {})
    monkeypatch.setattr(mcp_server, '_backend', mcp_server.InProcessBackend())
    seed = workspace / 'synthetic-note'
    seed.mkdir()
    (seed / 'notes.md').write_text('# Synthetic note\n\nLOCAL-HTTP-17', encoding='utf-8')
    (seed / 'transcript.json').write_text(json.dumps({
        'language': 'zh', 'source': 'subtitle_import',
        'segments': [{'start': 0, 'end': 2, 'text': 'LOCAL-HTTP-17'}],
    }), encoding='utf-8')
    (seed / 'transcript.md').write_text('[00:00-00:02] LOCAL-HTTP-17', encoding='utf-8')
    (seed / 'task.json').write_text(json.dumps({
        'task_id': seed.name, 'title': 'Synthetic note', 'output': 'note', 'origin': 'web',
        'subtitle_import': True, 'runtime': {'status': 'completed', 'result': {}},
    }), encoding='utf-8')
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(
        main.app, host='127.0.0.1', port=port, proxy_headers=False,
        log_level='critical', access_log=False, lifespan='off',
    ))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, 'Isolated loopback server failed to start'
        yield SimpleNamespace(url=f'http://127.0.0.1:{port}', workspace=workspace,
                              main=main, mcp_server=mcp_server)
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        if thread.is_alive():
            server.force_exit = True
            thread.join(timeout=2)
        sock.close()
        assert not thread.is_alive(), 'Owned loopback server failed to stop'


def test_real_http_native_client_and_subtitle_upload(live):
    with httpx.Client(base_url=live.url, trust_env=False, timeout=5) as client:
        assert client.get('/api/health').json()['product'] == 'Video2Knowledge'
        blocked = client.post('/api/upload', headers={'Origin': 'https://untrusted.example'},
                              files={'file': ('synthetic.srt', b'unused', 'text/plain')})
        assert blocked.status_code == 403
        assert sorted(p.name for p in live.workspace.iterdir()) == ['synthetic-note']
        uploaded = client.post('/api/upload', files={'file': (
            'synthetic.srt', b'1\n00:00:00,000 --> 00:00:02,000\nLOCAL-UPLOAD-42\n', 'text/plain')})
        assert uploaded.status_code == 200
        task_id = uploaded.json()['task_id']
        transcript = client.get(f'/api/task/{task_id}/transcript', params={'output_format': 'srt'})
        assert transcript.status_code == 200
        assert 'LOCAL-UPLOAD-42' in transcript.json()['text']
        manifest = json.loads((live.workspace / task_id / 'task.json').read_text(encoding='utf-8'))
        assert manifest['subtitle_import'] is True
        assert not live.main.running_jobs
    native = live.mcp_server.BackendClient(live.url)
    # No port discovery or proxy fallback is permitted in this compatibility probe.
    with patch.object(live.mcp_server, '_discover_backend_url', side_effect=AssertionError('no scan')):
        try:
            data = asyncio.run(native.get_task('synthetic-note'))
            assert data['status'] == 'completed'
            assert 'LOCAL-HTTP-17' in data['result']['markdown']
        finally:
            native._client.close()


@pytest.mark.parametrize('same_origin', [False, True])
def test_real_mcp_sse_initialize_list_and_read(live, same_origin):
    def client_factory(headers=None, timeout=None, auth=None):
        return httpx.AsyncClient(headers=headers, timeout=timeout, auth=auth, trust_env=False)

    async def session_roundtrip():
        async with sse_client(
            live.url + '/mcp/sse', headers={'Origin': live.url} if same_origin else None,
            timeout=5, sse_read_timeout=5, httpx_client_factory=client_factory,
        ) as streams:
            async with ClientSession(*streams, read_timeout_seconds=timedelta(seconds=5)) as session:
                initialized = await session.initialize()
                assert initialized.serverInfo.name == 'Video2Knowledge'
                listed = await session.list_tools()
                assert {'get_task_status', 'get_transcript'} <= {tool.name for tool in listed.tools}
                result = await session.call_tool('get_task_status', {'task_id': 'synthetic-note'})
                assert not result.isError
                data = json.loads(result.content[0].text)
                assert data['status'] == 'completed'
                assert 'LOCAL-HTTP-17' in data['result']['markdown']
                transcript = await session.call_tool('get_transcript', {
                    'task_id': 'synthetic-note', 'output_format': 'json'})
                assert not transcript.isError
                assert json.loads(transcript.content[0].text)['segments'][0]['text'] == 'LOCAL-HTTP-17'

    asyncio.run(asyncio.wait_for(session_roundtrip(), timeout=20))
    assert not live.main.running_jobs
    assert not (live.workspace / 'llm_keys.json').exists()
