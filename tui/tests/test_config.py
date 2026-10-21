"""The per-user config file and the token store."""

import sys
from pathlib import Path

from jinnverse_tui.config import (
    DEFAULT_SERVER,
    Config,
    TokenStore,
    carry_over,
    load,
    write_default,
)


def test_the_default_file_is_written_once_with_comments(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    write_default(path)
    text = path.read_text(encoding="utf-8")
    assert f'server = "{DEFAULT_SERVER}"' in text
    assert text.startswith("# JinnVerse")
    path.write_text('server = "http://kept.test"\n', encoding="utf-8")
    write_default(path)  # never overwrites
    assert load(path).server == "http://kept.test"


def test_a_missing_file_means_the_defaults(tmp_path: Path) -> None:
    assert load(tmp_path / "nowhere.toml") == Config()


def test_the_file_then_the_environment_then_the_command_line(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        'server = "http://file.test/"\nkeyboard = "Vim"\ntranscript_width_percent = 80\n'
        'mouse = true\nexport_directory = "out"\n',
        encoding="utf-8",
    )
    read = load(path, environ={})
    assert read.server == "http://file.test"  # the trailing slash goes
    assert (read.keyboard, read.transcript_width_percent, read.mouse) == ("vim", 80, True)
    assert read.export_directory == "out"
    assert load(path, environ={"JINNVERSE_SERVER": "http://env.test"}).server == "http://env.test"
    assert (
        load(path, server="http://cli.test", environ={"JINNVERSE_SERVER": "http://env.test"}).server
        == "http://cli.test"
    )


def test_the_badge_says_local_for_loopback_and_the_host_otherwise() -> None:
    assert Config().badge == "Local"
    assert Config(server="http://localhost:8000").badge == "Local"
    assert Config(server="https://lustjinn-staging.onrender.com").badge == (
        "lustjinn-staging.onrender.com"
    )


def test_the_token_store_reads_writes_and_forgets(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "deep" / "token")
    assert store.read() is None
    store.write("abc")
    assert store.read() == "abc"
    if sys.platform != "win32":
        assert (store.path.stat().st_mode & 0o777) == 0o600
    store.forget()
    assert store.read() is None
    store.forget()  # twice is fine


def test_the_former_names_directory_is_moved_once(tmp_path: Path) -> None:
    """The rename of 2026-10-21 (#248): config and token follow the reader to the new name."""
    former = tmp_path / "lustjinn"
    former.mkdir()
    (former / "config.toml").write_text('server = "http://kept.test"\n', encoding="utf-8")
    (former / "token").write_text("abc", encoding="utf-8")
    directory = tmp_path / "jinnverse"

    assert carry_over(directory, former) is True
    assert not former.exists()
    assert load(directory / "config.toml").server == "http://kept.test"
    assert TokenStore(directory / "token").read() == "abc"

    # Twice is nothing: the new directory exists, and a stray old one is left alone.
    former.mkdir()
    (former / "token").write_text("stale", encoding="utf-8")
    assert carry_over(directory, former) is False
    assert TokenStore(directory / "token").read() == "abc"


def test_nothing_to_carry_over_on_a_fresh_machine(tmp_path: Path) -> None:
    assert carry_over(tmp_path / "jinnverse", tmp_path / "lustjinn") is False
    assert not (tmp_path / "jinnverse").exists()
