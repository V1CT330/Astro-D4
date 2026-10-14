"""Tools the agent can call: code/files, scraping, and browser interaction."""
import ipaddress
import socket
import subprocess
import urllib.robotparser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

WORKSPACE = Path("workspace").resolve()
WORKSPACE.mkdir(exist_ok=True)
MAX_OUT = 8000  # characters returned to the model per tool call
UA = "AgentBot/0.1 (+personal project)"


def _clip(text: str) -> str:
    return text if len(text) <= MAX_OUT else text[:MAX_OUT] + "\n...[truncated]"


def _safe_path(p: str) -> Path:
    path = (WORKSPACE / p).resolve()
    if WORKSPACE != path and WORKSPACE not in path.parents:
        raise ValueError("Path is outside the workspace folder.")
    return path


def _check_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Only http(s) URLs are allowed.")
    for info in socket.getaddrinfo(parsed.hostname, None):
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise ValueError("Local/private addresses are blocked.")


# ---------- code / files ----------
def list_files(path: str = ".") -> str:
    base = _safe_path(path)
    items = sorted(str(p.relative_to(WORKSPACE)) for p in base.rglob("*") if p.is_file())
    return _clip("\n".join(items) or "(empty)")


def read_file(path: str) -> str:
    return _clip(_safe_path(path).read_text(encoding="utf-8", errors="replace"))


def write_file(path: str, content: str) -> str:
    p = _safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} chars to {path}"


def run_command(command: str) -> str:
    try:
        r = subprocess.run(command, shell=True, cwd=WORKSPACE, capture_output=True,
                           text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return "Command timed out after 60s."
    return _clip(f"exit code {r.returncode}\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}")


# ---------- scraping ----------
def scrape_page(url: str, selector: str = "") -> str:
    _check_url(url)
    robots = urllib.robotparser.RobotFileParser()
    try:
        robots.set_url(urljoin(url, "/robots.txt"))
        robots.read()
        if not robots.can_fetch(UA, url):
            return "Blocked by robots.txt. Not fetching."
    except Exception:
        pass  # robots.txt unreachable; continue politely
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    if selector:
        text = "\n".join(el.get_text(" ", strip=True) for el in soup.select(selector))
    else:
        text = soup.get_text("\n", strip=True)
    links = [urljoin(url, a["href"]) for a in soup.find_all("a", href=True)][:30]
    return _clip(f"TEXT:\n{text}\n\nLINKS:\n" + "\n".join(links))


# ---------- browser (Playwright, started on first use) ----------
_pw = _browser = _page = None


def _get_page():
    global _pw, _browser, _page
    if _page is None:
        from playwright.sync_api import sync_playwright
        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch(headless=True)
        _page = _browser.new_page()
    return _page


def browser_goto(url: str) -> str:
    _check_url(url)
    page = _get_page()
    page.goto(url, timeout=30000)
    return f"Opened {page.url} — title: {page.title()}"


def browser_text(selector: str = "body") -> str:
    return _clip(_get_page().inner_text(selector))


def browser_click(selector: str) -> str:
    page = _get_page()
    page.click(selector, timeout=10000)
    return f"Clicked. Now at {page.url}"


def browser_type(selector: str, text: str) -> str:
    _get_page().fill(selector, text, timeout=10000)
    return "Typed text."


def browser_screenshot(path: str = "screenshot.png") -> str:
    _get_page().screenshot(path=str(_safe_path(path)))
    return f"Saved screenshot to {path}"


def close_browser() -> None:
    global _pw, _browser, _page
    if _browser:
        _browser.close()
        _pw.stop()
    _pw = _browser = _page = None


def _schema(props: dict, required: list) -> dict:
    return {"type": "object", "properties": props, "required": required}


_S = {"type": "string"}

TOOLS = [
    ("list_files", list_files, "List files in the workspace.", _schema({"path": _S}, [])),
    ("read_file", read_file, "Read a text file from the workspace.", _schema({"path": _S}, ["path"])),
    ("write_file", write_file, "Create or overwrite a file in the workspace.",
     _schema({"path": _S, "content": _S}, ["path", "content"])),
    ("run_command", run_command, "Run a shell command inside the workspace (60s limit).",
     _schema({"command": _S}, ["command"])),
    ("scrape_page", scrape_page, "Fetch a static page; returns text and links. Optional CSS selector.",
     _schema({"url": _S, "selector": _S}, ["url"])),
    ("browser_goto", browser_goto, "Open a URL in a real browser (for JavaScript-heavy sites).",
     _schema({"url": _S}, ["url"])),
    ("browser_text", browser_text, "Get visible text of the current browser page (optional selector).",
     _schema({"selector": _S}, [])),
    ("browser_click", browser_click, "Click an element in the browser by CSS selector.",
     _schema({"selector": _S}, ["selector"])),
    ("browser_type", browser_type, "Type text into an input in the browser by CSS selector.",
     _schema({"selector": _S, "text": _S}, ["selector", "text"])),
    ("browser_screenshot", browser_screenshot, "Save a screenshot of the browser page into the workspace.",
     _schema({"path": _S}, [])),
]

REGISTRY = {name: fn for name, fn, _, _ in TOOLS}
SCHEMAS = [{"name": n, "description": d, "input_schema": s} for n, _, d, s in TOOLS]
RISKY = {"run_command", "browser_click", "browser_type"}
      
