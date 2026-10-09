#!/usr/bin/env python3
"""One-command Telegram setup for TRAX.

    python3 scripts/setup_telegram.py            # configure + send a test message
    python3 scripts/setup_telegram.py --dry-run  # show what would change, write nothing
    python3 scripts/setup_telegram.py --chat-id 123456789

Token source, first match wins: ~/trex/.env, ~/.hermes/.env (the Hermes
agent already holds the working @MyETRex_bot token), then a hidden prompt.
The token is never printed and never accepted as a CLI argument, so it
stays out of shell history.

The chat id is read from config, never discovered via getUpdates: Hermes
long-polls the same bot, and a second getUpdates consumer makes Telegram
return 409 Conflict and can steal Hermes's messages. sendMessage does not
conflict with polling, so the test send is safe.

~/trex/.env is backed up to .env.bak-<timestamp> before any edit, then
rewritten atomically with mode 600.
"""

import argparse
import getpass
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$")
CHAT_ID_RE = re.compile(r"^-?\d{5,20}$")

# Keys that hold a chat id in TRAX's own .env or in Hermes's. List-valued
# keys (comma-separated user ids) contribute their first entry; for a
# private chat with the bot, the chat id equals the user's Telegram id.
CHAT_ID_KEYS = (
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_HOME_CHANNEL",
    "TELEGRAM_OPERATOR_CHAT_ID",
    "TELEGRAM_ALLOWED_USERS",
    "TELEGRAM_ALLOWED_CHAT_IDS",
)


def default_trex_env() -> str:
    return os.environ.get("TRAX_ENV_FILE") or os.path.join(REPO_ROOT, ".env")


def default_hermes_env() -> str:
    return os.environ.get("HERMES_ENV_FILE") or os.path.expanduser("~/.hermes/.env")


def _parse_line(line: str):
    """Returns (key, value) for an assignment line, else None."""
    s = line.strip()
    if s.startswith("export "):
        s = s[len("export "):].lstrip()
    if not s or s.startswith("#") or "=" not in s:
        return None
    key, value = s.split("=", 1)
    key, value = key.strip(), value.strip()
    if value[:1] in ("'", '"'):
        quote = value[0]
        end = value.find(quote, 1)
        value = value[1:end] if end != -1 else value[1:]
    elif " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    return key, value


def read_env_file(path: str) -> dict:
    """Parse KEY=VALUE lines. Later duplicates win, matching python-dotenv."""
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            parsed = _parse_line(line)
            if parsed:
                out[parsed[0]] = parsed[1]
    return out


def upsert_env(path: str, updates: dict, template: str | None = None) -> list[str]:
    """Set each key in `updates`, preserving every other line and comment.
    Replaces the first definition of a key, drops later duplicates, and
    appends keys that were absent. Creates the file from `template` when
    missing. Returns the keys that changed."""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    elif template and os.path.exists(template):
        with open(template, encoding="utf-8") as f:
            lines = f.read().splitlines()
    else:
        lines = []

    current = {}
    for line in lines:
        parsed = _parse_line(line)
        if parsed:
            current[parsed[0]] = parsed[1]
    changed = [k for k, v in updates.items() if current.get(k) != v]

    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        parsed = _parse_line(line)
        key = parsed[0] if parsed else None
        if key in updates:
            if key in seen:
                continue
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)

    missing = [k for k in updates if k not in seen]
    if missing:
        if out and out[-1].strip():
            out.append("")
        out.append("# --- set by scripts/setup_telegram.py ---")
        out.extend(f"{k}={updates[k]}" for k in missing)

    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".env.tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return changed


def redact(text: str, token: str) -> str:
    return str(text).replace(token, "[redacted]") if token else str(text)


def telegram_call(token: str, method: str, payload: dict | None = None,
                  timeout: float = 15.0) -> tuple[int, dict]:
    """POST/GET a Bot API method. Returns (http_status, json_body). Never raises
    with the token in the message."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode() or "{}")
        except ValueError:
            body = {}
        return e.code, body
    except Exception as e:  # noqa: BLE001
        return 0, {"description": redact(e, token)}


def find_token(trex_env: dict, hermes_env: dict) -> tuple[str, str]:
    for source, env in (("~/trex/.env", trex_env), ("~/.hermes/.env", hermes_env)):
        token = env.get("TELEGRAM_BOT_TOKEN", "")
        if TOKEN_RE.match(token):
            return token, source
    return "", ""


def find_chat_id(trex_env: dict, hermes_env: dict) -> tuple[str, str]:
    for source, env in (("~/trex/.env", trex_env), ("~/.hermes/.env", hermes_env)):
        for key in CHAT_ID_KEYS:
            raw = env.get(key, "")
            candidate = raw.split(",")[0].strip() if raw else ""
            if CHAT_ID_RE.match(candidate):
                return candidate, f"{source} {key}"
    return "", ""


def main(argv: list[str] | None = None, input_fn=input, secret_fn=getpass.getpass) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chat-id", help="Telegram chat id to send to (numeric)")
    parser.add_argument("--dry-run", action="store_true",
                        help="verify and report, but do not write .env or send")
    parser.add_argument("--no-autosend", action="store_true",
                        help="leave TELEGRAM_AUTOSEND=false")
    args = parser.parse_args(argv)

    trex_path = default_trex_env()
    trex_env = read_env_file(trex_path)
    hermes_env = read_env_file(default_hermes_env())

    token, token_source = find_token(trex_env, hermes_env)
    if not token:
        print("No bot token found in ~/trex/.env or ~/.hermes/.env.")
        print("Get it from @BotFather: /mybots -> @MyETRex_bot -> API Token.")
        token = secret_fn("Paste the bot token (input hidden): ").strip()
        token_source = "prompt"
    if not TOKEN_RE.match(token):
        print("That doesn't look like a bot token (expected <digits>:<35+ chars>).")
        return 1

    status, body = telegram_call(token, "getMe")
    if status != 200 or not body.get("ok"):
        reason = redact(body.get("description") or f"HTTP {status}", token)
        print(f"Telegram rejected the token from {token_source}: {reason}")
        if status == 401:
            print("It was probably revoked. Get the current one from @BotFather.")
        return 1
    username = body["result"].get("username", "?")
    print(f"1/3 Token from {token_source} is valid for @{username}")

    chat_id, chat_source = (args.chat_id or "").strip(), "--chat-id"
    if not chat_id:
        chat_id, chat_source = find_chat_id(trex_env, hermes_env)
    if not chat_id:
        print("No chat id found in config. Message @userinfobot in Telegram;")
        print("it replies with your numeric id, which is your chat id with the bot.")
        chat_id = input_fn("Enter your Telegram chat id: ").strip()
        chat_source = "prompt"
    if not CHAT_ID_RE.match(chat_id):
        print(f"'{chat_id}' is not a numeric Telegram chat id.")
        return 1
    print(f"2/3 Chat id {chat_id} (from {chat_source})")

    updates = {
        "TELEGRAM_BOT_TOKEN": token,
        "TELEGRAM_CHAT_ID": chat_id,
        "TRAX_ALLOW_SETTINGS_WRITE": "true",
        "TELEGRAM_AUTOSEND": "false" if args.no_autosend else "true",
    }

    if args.dry_run:
        pending = [k for k, v in updates.items() if trex_env.get(k) != v]
        print(f"[dry run] would update {trex_path}: {', '.join(pending) or 'nothing'}")
        print("[dry run] no file written, no message sent.")
        return 0

    if os.path.exists(trex_path):
        backup = f"{trex_path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(trex_path, backup)
        os.chmod(backup, 0o600)
        print(f"    backed up existing .env to {os.path.basename(backup)}")
    template = os.path.join(os.path.dirname(os.path.abspath(trex_path)), ".env.example")
    changed = upsert_env(trex_path, updates, template=template)
    print(f"    wrote {trex_path} ({', '.join(changed) or 'already up to date'})")

    status, body = telegram_call(token, "sendMessage", {
        "chat_id": chat_id,
        "text": "TRAX is connected to Telegram. Signals will arrive in this chat.",
        "disable_web_page_preview": True,
    })
    if status == 200 and body.get("ok"):
        print("3/3 Test message sent. Check Telegram.")
    else:
        reason = redact(body.get("description") or f"HTTP {status}", token)
        print(f"3/3 .env is written, but the test send failed: {reason}")
        if "chat not found" in reason.lower():
            print("    Open @MyETRex_bot in Telegram, press Start, then rerun this script.")
        return 1

    print()
    print("Restart the backend so it reads the new .env (uvicorn --reload")
    print("watches .py files, not .env): press Ctrl-C in its terminal, then")
    print("  python3 -m uvicorn api.main:app --port 8788 --reload")
    return 0


if __name__ == "__main__":
    sys.exit(main())
