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

~/trex/.env (or the file it symlinks to) is backed up to
.env.bak-<timestamp> with mode 600, then rewritten atomically with mode
600. Lines other than the four Telegram keys are copied byte-for-byte,
using python-dotenv's own parser so multiline values survive.
"""

import argparse
import getpass
import io
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

try:
    from dotenv import dotenv_values
    from dotenv.parser import parse_stream
except ImportError:  # pragma: no cover
    sys.exit("python-dotenv is missing. Run: python3 -m pip install -r requirements.txt")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$")
CHAT_ID_RE = re.compile(r"^-?\d{5,20}$")
TRIGGER_SERVER_LABEL = "com.trex.trigger-server"

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

_run = subprocess.run


def default_trex_env() -> str:
    return os.environ.get("TRAX_ENV_FILE") or os.path.join(REPO_ROOT, ".env")


def default_hermes_env() -> str:
    return os.environ.get("HERMES_ENV_FILE") or os.path.expanduser("~/.hermes/.env")


def read_env_file(path: str) -> dict:
    """Parse with python-dotenv itself, so values match what TRAX loads."""
    if not os.path.exists(path):
        return {}
    return {k: (v or "") for k, v in dotenv_values(path).items()}


def backup_file(path: str) -> str:
    """Copy `path` to <path>.bak-<timestamp>, created 0600 from the first
    byte (copy2 would create it 0644 under the default umask and only then
    narrow it). O_EXCL never overwrites an earlier backup."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for n in range(100):
        candidate = f"{path}.bak-{stamp}" + (f"-{n}" if n else "")
        try:
            fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        with os.fdopen(fd, "wb") as out, open(path, "rb") as src:
            shutil.copyfileobj(src, out)
        return candidate
    raise RuntimeError(f"could not create a backup next to {path}")


def upsert_env(path: str, updates: dict, template: str | None = None) -> list[str]:
    """Set each key in `updates`. Every other entry, comment and blank line
    is written back exactly as read. The first definition of a key is
    replaced, later duplicates are dropped, and absent keys are appended.
    Creates the file from `template` when missing. A symlinked `path` is
    followed, so the link's target is updated and the link survives.
    Returns the keys whose value changed."""
    path = os.path.realpath(path)
    if os.path.exists(path):
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
    elif template and os.path.exists(template):
        with open(template, encoding="utf-8", newline="") as f:
            text = f.read()
    else:
        text = ""

    bindings = list(parse_stream(io.StringIO(text)))
    current = {b.key: (b.value or "") for b in bindings if b.key and not b.error}
    changed = [k for k, v in updates.items() if current.get(k) != v]

    seen: set[str] = set()
    parts: list[str] = []
    for b in bindings:
        raw = b.original.string
        if b.key in updates and not b.error:
            if b.key in seen:
                continue
            seen.add(b.key)
            leading = raw[: len(raw) - len(raw.lstrip())]
            parts.append(f"{leading}{b.key}={updates[b.key]}\n")
        else:
            parts.append(raw)

    missing = [k for k in updates if k not in seen]
    if missing:
        body = "".join(parts)
        if body and not body.endswith("\n"):
            parts.append("\n")
        if body.strip():
            parts.append("\n")
        parts.append("# --- set by scripts/setup_telegram.py ---\n")
        parts.extend(f"{k}={updates[k]}\n" for k in missing)

    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".env.tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write("".join(parts))
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return changed


def redact(text, token: str) -> str:
    return str(text).replace(token, "[redacted]") if token else str(text)


def _ssl_context() -> ssl.SSLContext:
    """python.org macOS builds ship without a CA store until the user runs
    'Install Certificates.command'; certifi (installed with requests) fills
    that gap, which is why the rest of TRAX never hit it."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def telegram_call(token: str, method: str, payload: dict | None = None,
                  timeout: float = 15.0) -> tuple[int, dict]:
    """Call a Bot API method. Returns (http_status, json_body); status 0
    means Telegram was never reached. Never raises with the token in the
    message."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode() or "{}")
        except ValueError:
            body = {}
        return e.code, body
    except Exception as e:  # noqa: BLE001
        return 0, {"description": redact(e, token)}


def explain_unreachable(reason: str) -> None:
    print(f"Could not reach api.telegram.org: {reason}")
    print("This is a network problem, not a bad token; don't rotate it.")
    if "CERTIFICATE_VERIFY_FAILED" in reason:
        v = sys.version_info
        print(f'Fix: double-click "/Applications/Python {v.major}.{v.minor}/Install Certificates.command",')
        print("or run: python3 -m pip install certifi  — then rerun this script.")


def find_token(trex_env: dict, hermes_env: dict) -> tuple[str, str]:
    for source, env in (("~/trex/.env", trex_env), ("~/.hermes/.env", hermes_env)):
        token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
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


def _is_macos() -> bool:
    return sys.platform == "darwin"


def restart_trigger_server() -> str:
    """Kickstart the com.trex.trigger-server LaunchAgent. It is the process
    that auto-sends signals, and it read .env once at startup.
    Returns 'restarted', 'not_loaded', 'skipped' or 'failed: ...'."""
    if not _is_macos():
        return "skipped"
    target = f"gui/{os.getuid()}/{TRIGGER_SERVER_LABEL}"
    if _run(["launchctl", "print", target], capture_output=True, text=True).returncode != 0:
        return "not_loaded"
    res = _run(["launchctl", "kickstart", "-k", target], capture_output=True, text=True)
    return "restarted" if res.returncode == 0 else f"failed: {res.stderr.strip()[:200]}"


BOTFATHER_HINT = (
    "Get the current token: in Telegram open @BotFather -> /mybots -> your bot\n"
    "(@MyETRex_bot) -> API Token, and copy it. Don't press 'Revoke current token';\n"
    "that issues yet another token and invalidates the one you just copied."
)
MAX_TOKEN_ATTEMPTS = 3


def check_token(token: str) -> tuple[str, str]:
    """Returns ('ok', username), ('rejected', reason), ('unreachable', reason)
    or ('malformed', '')."""
    if not TOKEN_RE.match(token):
        return "malformed", ""
    status, body = telegram_call(token, "getMe")
    if status == 0:
        return "unreachable", redact(body.get("description", ""), token)
    if status == 200 and body.get("ok"):
        return "ok", body["result"].get("username", "?")
    return "rejected", redact(body.get("description") or f"HTTP {status}", token)


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
    rejected_sources: list[str] = []
    if not token:
        print("No bot token found in ~/trex/.env or ~/.hermes/.env.")
        print(BOTFATHER_HINT)
        token, token_source = secret_fn("Paste the bot token (input hidden): ").strip(), "prompt"

    username = ""
    for attempt in range(1, MAX_TOKEN_ATTEMPTS + 1):
        state, detail = check_token(token)
        if state == "ok":
            username = detail
            break
        if state == "unreachable":
            explain_unreachable(detail)
            return 1
        if state == "malformed":
            print("That doesn't look like a bot token (expected <digits>:<35+ chars>).")
        else:
            print(f"Telegram rejected the token from {token_source}: {detail}")
            print("That token is revoked or wrong.")
            if token_source != "prompt":
                rejected_sources.append(token_source)
        if attempt == MAX_TOKEN_ATTEMPTS:
            print("Giving up; nothing was written.")
            return 1
        print(BOTFATHER_HINT)
        token = secret_fn("Paste the current token (input hidden, Enter to quit): ").strip()
        token_source = "prompt"
        if not token:
            print("No token entered; nothing was written.")
            return 1
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

    real_path = os.path.realpath(trex_path)
    if args.dry_run:
        pending = [k for k, v in updates.items() if trex_env.get(k) != v]
        print(f"[dry run] would update {real_path}: {', '.join(pending) or 'nothing'}")
        print("[dry run] no file written, no message sent.")
        _warn_stale_sources(rejected_sources)
        return 0

    if real_path != os.path.abspath(trex_path):
        print(f"    {trex_path} is a symlink; updating its target {real_path}")
    if os.path.exists(real_path):
        backup = backup_file(real_path)
        print(f"    backed up existing .env to {os.path.basename(backup)}")
    template = os.path.join(os.path.dirname(os.path.abspath(trex_path)), ".env.example")
    changed = upsert_env(trex_path, updates, template=template)
    print(f"    wrote {real_path} ({', '.join(changed) or 'already up to date'})")

    status, body = telegram_call(token, "sendMessage", {
        "chat_id": chat_id,
        "text": "TRAX is connected to Telegram. Signals will arrive in this chat.",
        "disable_web_page_preview": True,
    })
    if status == 0:
        explain_unreachable(redact(body.get("description", ""), token))
        return 1
    if status != 200 or not body.get("ok"):
        reason = redact(body.get("description") or f"HTTP {status}", token)
        print(f"3/3 .env is written, but the test send failed: {reason}")
        if "chat not found" in reason.lower():
            print("    Open @MyETRex_bot in Telegram, press Start, then rerun this script.")
        return 1
    print("3/3 Test message sent. Check Telegram.")

    print()
    if _is_macos():
        try:
            answer = input_fn(f"Restart {TRIGGER_SERVER_LABEL} now so autosend takes effect? [Y/n] ")
        except EOFError:
            answer = ""
        if answer.strip().lower() in ("", "y", "yes"):
            result = restart_trigger_server()
            if result == "restarted":
                print(f"    {TRIGGER_SERVER_LABEL} restarted; it now reads the new .env.")
            elif result == "not_loaded":
                print(f"    {TRIGGER_SERVER_LABEL} isn't loaded; nothing to restart.")
            else:
                print(f"    restart {result}")
        else:
            print(f"    Later, run: launchctl kickstart -k gui/$(id -u)/{TRIGGER_SERVER_LABEL}")

    print("Restart the dashboard backend too (uvicorn --reload watches .py")
    print("files, not .env): press Ctrl-C in its terminal, then")
    print("  python3 -m uvicorn api.main:app --port 8788 --reload")
    _warn_stale_sources(rejected_sources)
    return 0


def _warn_stale_sources(sources: list[str]) -> None:
    """This script only edits ~/trex/.env. If it found a revoked token in
    Hermes's config, Hermes's Telegram gateway is broken too; say so rather
    than edit another app's config."""
    if "~/.hermes/.env" in sources:
        print()
        print("Note: ~/.hermes/.env still holds the revoked token, so Hermes can't")
        print("use Telegram either. If you use Hermes on Telegram, put the new token")
        print("in TELEGRAM_BOT_TOKEN there and restart the Hermes gateway.")


if __name__ == "__main__":
    sys.exit(main())
