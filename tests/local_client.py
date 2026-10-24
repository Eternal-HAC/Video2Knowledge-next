"""Use a real loopback authority/peer, never a production testserver exemption."""
from fastapi.testclient import TestClient as FastAPITestClient


class TestClient(FastAPITestClient):
    __test__ = False

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("base_url", "http://127.0.0.1")
        kwargs.setdefault("client", ("127.0.0.1", 50000))
        super().__init__(*args, **kwargs)
