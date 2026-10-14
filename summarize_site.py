"""Small standalone helper: scrape one page and summarize it with Claude.

Usage:
    python summarize_site.py https://example.com
    python summarize_site.py https://example.com "List every product and its price"
"""
import os
import sys

import anthropic
from dotenv import load_dotenv

import tools

load_dotenv()


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python summarize_site.py URL [question]")
    url = sys.argv[1]
    question = sys.argv[2] if len(sys.argv) > 2 else "Summarize the key points of this page."

    page = tools.scrape_page(url)
    if page.startswith("Blocked"):
        raise SystemExit(page)

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=os.getenv("AGENT_MODEL", "claude-sonnet-5-5"),
        max_tokens=1500,
        messages=[{"role": "user", "content":
                   f"{question}\n\nOnly use the page content below.\n\n{page}"}],
    )
    print(resp.content[0].text)


if __name__ == "__main__":
    main()
