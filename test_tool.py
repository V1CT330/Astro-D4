"""Basic tests for tools.py. Run with: pytest"""
import pytest

import tools


@pytest.fixture(autouse=True)
def temp_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKSPACE", tmp_path.resolve())


def test_write_then_read_file():
    tools.write_file("notes/hello.txt", "hi there")
    assert tools.read_file("notes/hello.txt") == "hi there"


def test_list_files_shows_written_file():
    tools.write_file("a.txt", "x")
    assert "a.txt" in tools.list_files()


def test_path_escape_is_blocked():
    with pytest.raises(ValueError):
        tools.read_file("../secret.txt")


def test_shell_execution_is_not_exposed_or_available():
    assert "run_command" not in tools.REGISTRY
    assert "disabled" in tools.run_command("echo agent").lower()


def test_redirect_to_private_address_is_blocked(monkeypatch):
    class Redirect:
        status_code = 302
        headers = {"Location": "http://127.0.0.1:8000/admin"}

    checked = []

    def check(url):
        checked.append(url)
        if "127.0.0.1" in url:
            raise ValueError("Non-public address blocked")

    monkeypatch.setattr(tools, "_check_url", check)
    monkeypatch.setattr(tools.requests, "get", lambda *a, **k: Redirect())

    with pytest.raises(ValueError):
        tools._safe_get("https://public.example/")
    assert checked == ["https://public.example/", "http://127.0.0.1:8000/admin"]


def test_non_http_url_is_blocked():
    with pytest.raises(ValueError):
        tools._check_url("ftp://example.com/file")


def test_localhost_is_blocked():
    with pytest.raises(ValueError):
        tools._check_url("http://localhost:8000")


def test_every_tool_has_a_schema():
    assert set(tools.REGISTRY) == {s["name"] for s in tools.SCHEMAS}
