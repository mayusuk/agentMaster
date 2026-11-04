"""Shared test setup.

Every test runs with network access blocked (Spec 001 NFR-2), unless it is
marked ``network``. That marker is reserved for explicit LLM provider tests.
"""

from __future__ import annotations

import socket
from typing import Any

import pytest


class NetworkAccessError(RuntimeError):
    pass


def _blocked(*_args: Any, **_kwargs: Any) -> Any:
    raise NetworkAccessError("network access attempted in a test not marked 'network'")


@pytest.fixture(autouse=True)
def _block_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    # monkeypatch undoes these patches after each test.
    if request.node.get_closest_marker("network") is None:
        monkeypatch.setattr(socket.socket, "connect", _blocked)
        monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
        monkeypatch.setattr(socket, "create_connection", _blocked)
        monkeypatch.setattr(socket, "getaddrinfo", _blocked)
