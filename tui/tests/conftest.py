"""Fixtures for the terminal client's tests: a fake server, a token on disk, the app wired to both.
None of this touches the network, the database or the reader's config directory."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from jinnverse_tui import emoji
from jinnverse_tui.api import Api
from jinnverse_tui.app import JinnverseApp
from jinnverse_tui.config import Config, TokenStore
from tui_support import emoji_table
from tui_support import fake_server as fake

FakeServer = fake.FakeServer


@pytest.fixture(autouse=True)
def emoji_read() -> None:
    """Every test starts with the API's emoji table held, as the app has it after one read."""
    emoji.load(emoji_table.shortcodes())


@pytest.fixture
def server() -> fake.FakeServer:
    return fake.FakeServer()


@pytest.fixture
def tokens(tmp_path: Path) -> TokenStore:
    return TokenStore(tmp_path / "token")


@pytest.fixture
def api(server: fake.FakeServer, tokens: TokenStore) -> Api:
    return Api("http://api.test", tokens, transport=server.transport())


@pytest.fixture
def make_app(api: Api, tokens: TokenStore) -> Callable[..., JinnverseApp]:
    """An app against the fake server; ``signed_in=False`` starts without a token."""

    def make(*, signed_in: bool = True, config: Config | None = None) -> JinnverseApp:
        if signed_in:
            tokens.write(fake.TOKEN)
        return JinnverseApp(
            config or Config(server="http://api.test"), api, wake_waits=(0.02, 0.02)
        )

    return make


@pytest.fixture
def app(make_app: Callable[..., JinnverseApp]) -> JinnverseApp:
    return make_app()
