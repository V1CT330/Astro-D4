"""Command-line AI agent: coder + scraper + web interaction.

Usage:
    python agent.py                 # interactive; asks before risky actions
    python agent.py --yes           # auto-approve risky actions (use with care)
    python agent.py "your task"     # run one task and exit
"""
import argparse
import json
import os

import anthropic
from dotenv import load_dotenv

import tools

load_dotenv()
MODEL = os.getenv("AGENT_MODEL", "claude-sonnet-5-5")
MAX_STEPS = 25

SYSTEM = (
    "You are an autonomous agent that can write and run code, scrape websites, and "
    "interact with web pages. All files live in a workspace folder. Work step by step, "
    "use tools to verify results instead of guessing, and never invent data you did not "
    "retrieve. Prefer scrape_page for static pages and the browser tools only when "
    "JavaScript or interaction is required. Respect robots.txt and site terms; never "
    "attempt to bypass logins, paywalls or access controls. When finished, give a short "
    "summary of what you did and where the output files are."
)


def approve(name: str, args: dict, auto: bool) -> bool:
    if auto or name not in tools.RISKY:
        return True
    print(f"\n  ⚠ Agent wants to run {name}: {json.dumps(args)[:300]}")
    return input("  Allow? [y/N] ").strip().lower() == "y"


def run_task(client, task: str, auto: bool) -> None:
    messages = [{"role": "user", "content": task}]
    for step in range(1, MAX_STEPS + 1):
        resp = client.messages.create(
            model=MODEL, max_tokens=4096, system=SYSTEM,
            tools=tools.SCHEMAS, messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        for block in resp.content:
            if block.type == "text" and block.text.strip():
                print(f"\n{block.text}")

        if resp.stop_reason != "tool_use":
            return

        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            print(f"\n[{step}] {block.name} {json.dumps(block.input)[:200]}")
            if not approve(block.name, block.input, auto):
                out, is_err = "User denied this action.", True
            else:
                try:
                    out, is_err = tools.REGISTRY[block.name](**block.input), False
                except Exception as e:  # report errors to the model so it can adapt
                    out, is_err = f"Error: {e}", True
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": out, "is_error": is_err})
        messages.append({"role": "user", "content": results})
    print(f"\nStopped: reached the {MAX_STEPS}-step limit.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", nargs="?", help="Task to run (omit for interactive mode)")
    ap.add_argument("--yes", action="store_true", help="auto-approve risky actions")
    args = ap.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY in your .env file.")
    client = anthropic.Anthropic()

    try:
        if args.task:
            run_task(client, args.task, args.yes)
        else:
            print("Agent ready. Type a task, or 'exit' to quit.")
            while True:
                task = input("\n> ").strip()
                if task.lower() in ("exit", "quit"):
                    break
                if task:
                    run_task(client, task, args.yes)
    finally:
        tools.close_browser()


if __name__ == "__main__":
    main()
  
