"""scripts/setup_telegram.py — .env parsing/upsert, token + chat id
discovery, and the end-to-end flow with the Bot API mocked."""

import importlib.util
import os
import stat

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "setup_telegram",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "setup_telegram.py"),
)
st = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(st)

TOKEN = "8123456789:AAFakeTokenForSetupTestsOnly_abcdefghijk"
OLD_TOKEN = "7000000000:AAOldRevokedTokenValueForTests_zyxwvuts"


@pytest.fixture
def envs(tmp_path, monkeypatch):
    trex = tmp_path / "trex" / ".env"
    hermes = tmp_path / "hermes" / ".env"
    trex.parent.mkdir()
    hermes.parent.mkdir()
    (trex.parent / ".env.example").write_text("# template\nLOG_LEVEL=INFO\nTELEGRAM_BOT_TOKEN=\n")
    monkeypatch.setenv("TRAX_ENV_FILE", str(trex))
    monkeypatch.setenv("HERMES_ENV_FILE", str(hermes))
    return trex, hermes


def _fake_telegram(responses, calls):
    def fake(token, method, payload=None, timeout=15.0):
        calls.append((method, payload))
        return responses[method]
    return fake


GET_ME_OK = (200, {"ok": True, "result": {"username": "MyETRex_bot"}})
SEND_OK = (200, {"ok": True, "result": {"message_id": 1}})


# --- parsing ---------------------------------------------------------------

def test_read_env_handles_quotes_export_comments(tmp_path):
    p = tmp_path / ".env"
    p.write_text(
        "# comment\n"
        "export A=1\n"
        'B="two words"\n'
        "C='x' \n"
        "D=plain # trailing comment\n"
        "E=\n"
        "not an assignment\n"
        "A=override\n"
    )
    env = st.read_env_file(str(p))
    assert env == {"A": "override", "B": "two words", "C": "x", "D": "plain", "E": ""}


def test_read_env_missing_file_is_empty(tmp_path):
    assert st.read_env_file(str(tmp_path / "nope")) == {}


# --- upsert ----------------------------------------------------------------

def test_upsert_replaces_in_place_and_keeps_other_lines(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# header\nLOG_LEVEL=INFO\nTELEGRAM_BOT_TOKEN=\nOTHER=keep\n")
    changed = st.upsert_env(str(p), {"TELEGRAM_BOT_TOKEN": TOKEN})
    text = p.read_text()
    assert changed == ["TELEGRAM_BOT_TOKEN"]
    assert text.splitlines() == ["# header", "LOG_LEVEL=INFO",
                                 f"TELEGRAM_BOT_TOKEN={TOKEN}", "OTHER=keep"]


def test_upsert_drops_duplicate_definitions(tmp_path):
    p = tmp_path / ".env"
    p.write_text(f"TELEGRAM_BOT_TOKEN={OLD_TOKEN}\nX=1\nexport TELEGRAM_BOT_TOKEN={OLD_TOKEN}\n")
    st.upsert_env(str(p), {"TELEGRAM_BOT_TOKEN": TOKEN})
    text = p.read_text()
    assert text.count("TELEGRAM_BOT_TOKEN=") == 1
    assert OLD_TOKEN not in text
    assert st.read_env_file(str(p))["TELEGRAM_BOT_TOKEN"] == TOKEN


def test_upsert_appends_missing_keys(tmp_path):
    p = tmp_path / ".env"
    p.write_text("LOG_LEVEL=INFO\n")
    st.upsert_env(str(p), {"TELEGRAM_CHAT_ID": "123456789"})
    assert st.read_env_file(str(p)) == {"LOG_LEVEL": "INFO", "TELEGRAM_CHAT_ID": "123456789"}


def test_upsert_creates_from_template_with_mode_600(tmp_path):
    template = tmp_path / ".env.example"
    template.write_text("LOG_LEVEL=INFO\nTELEGRAM_BOT_TOKEN=\n")
    p = tmp_path / ".env"
    st.upsert_env(str(p), {"TELEGRAM_BOT_TOKEN": TOKEN}, template=str(template))
    assert st.read_env_file(str(p)) == {"LOG_LEVEL": "INFO", "TELEGRAM_BOT_TOKEN": TOKEN}
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600


def test_upsert_reports_no_change_when_identical(tmp_path):
    p = tmp_path / ".env"
    p.write_text("TELEGRAM_CHAT_ID=123456789\n")
    assert st.upsert_env(str(p), {"TELEGRAM_CHAT_ID": "123456789"}) == []


# --- discovery -------------------------------------------------------------

def test_find_token_prefers_trex_then_hermes():
    assert st.find_token({"TELEGRAM_BOT_TOKEN": TOKEN}, {"TELEGRAM_BOT_TOKEN": OLD_TOKEN}) == (TOKEN, "~/trex/.env")
    assert st.find_token({}, {"TELEGRAM_BOT_TOKEN": TOKEN}) == (TOKEN, "~/.hermes/.env")
    assert st.find_token({"TELEGRAM_BOT_TOKEN": "garbage"}, {}) == ("", "")


def test_find_chat_id_from_hermes_allowed_users_takes_first():
    chat, source = st.find_chat_id({}, {"TELEGRAM_ALLOWED_USERS": "987654321, 111111111"})
    assert chat == "987654321"
    assert "TELEGRAM_ALLOWED_USERS" in source


def test_find_chat_id_accepts_negative_group_ids():
    chat, _ = st.find_chat_id({"TELEGRAM_CHAT_ID": "-1001234567890"}, {})
    assert chat == "-1001234567890"


def test_redact_strips_token():
    assert st.redact(f"error at /bot{TOKEN}/getMe", TOKEN) == "error at /bot[redacted]/getMe"


# --- end-to-end ------------------------------------------------------------

def test_main_copies_hermes_token_writes_env_and_sends(envs, monkeypatch, capsys):
    trex, hermes = envs
    hermes.write_text(f"TELEGRAM_BOT_TOKEN={TOKEN}\nTELEGRAM_ALLOWED_USERS=987654321\n")
    calls = []
    monkeypatch.setattr(st, "telegram_call", _fake_telegram(
        {"getMe": GET_ME_OK, "sendMessage": SEND_OK}, calls))

    assert st.main([]) == 0

    env = st.read_env_file(str(trex))
    assert env["TELEGRAM_BOT_TOKEN"] == TOKEN
    assert env["TELEGRAM_CHAT_ID"] == "987654321"
    assert env["TRAX_ALLOW_SETTINGS_WRITE"] == "true"
    assert env["TELEGRAM_AUTOSEND"] == "true"
    assert env["LOG_LEVEL"] == "INFO"  # template contents carried over
    assert [m for m, _ in calls] == ["getMe", "sendMessage"]
    assert calls[1][1]["chat_id"] == "987654321"
    assert TOKEN not in capsys.readouterr().out


def test_main_never_calls_get_updates(envs, monkeypatch):
    """getUpdates would conflict with Hermes's long polling."""
    _, hermes = envs
    hermes.write_text(f"TELEGRAM_BOT_TOKEN={TOKEN}\nTELEGRAM_ALLOWED_USERS=987654321\n")
    calls = []
    monkeypatch.setattr(st, "telegram_call", _fake_telegram(
        {"getMe": GET_ME_OK, "sendMessage": SEND_OK}, calls))
    st.main([])
    assert "getUpdates" not in [m for m, _ in calls]


def test_main_backs_up_existing_env(envs, monkeypatch):
    trex, hermes = envs
    trex.write_text("KEEP_ME=1\n")
    hermes.write_text(f"TELEGRAM_BOT_TOKEN={TOKEN}\n")
    monkeypatch.setattr(st, "telegram_call", _fake_telegram(
        {"getMe": GET_ME_OK, "sendMessage": SEND_OK}, []))
    assert st.main(["--chat-id", "123456789"]) == 0
    backups = [f for f in os.listdir(trex.parent) if f.startswith(".env.bak-")]
    assert len(backups) == 1
    assert (trex.parent / backups[0]).read_text() == "KEEP_ME=1\n"
    assert st.read_env_file(str(trex))["KEEP_ME"] == "1"


def test_main_dry_run_writes_nothing_and_sends_nothing(envs, monkeypatch):
    trex, hermes = envs
    hermes.write_text(f"TELEGRAM_BOT_TOKEN={TOKEN}\nTELEGRAM_ALLOWED_USERS=987654321\n")
    calls = []
    monkeypatch.setattr(st, "telegram_call", _fake_telegram({"getMe": GET_ME_OK}, calls))
    assert st.main(["--dry-run"]) == 0
    assert not trex.exists()
    assert [m for m, _ in calls] == ["getMe"]


def test_main_rejected_token_stops_before_writing(envs, monkeypatch, capsys):
    trex, hermes = envs
    hermes.write_text(f"TELEGRAM_BOT_TOKEN={OLD_TOKEN}\n")
    monkeypatch.setattr(st, "telegram_call", _fake_telegram(
        {"getMe": (401, {"ok": False, "description": "Unauthorized"})}, []))
    assert st.main(["--chat-id", "123456789"]) == 1
    assert not trex.exists()
    assert "revoked" in capsys.readouterr().out


def test_main_prompts_for_token_and_chat_when_absent(envs, monkeypatch):
    trex, _ = envs
    monkeypatch.setattr(st, "telegram_call", _fake_telegram(
        {"getMe": GET_ME_OK, "sendMessage": SEND_OK}, []))
    rc = st.main([], input_fn=lambda _: "555555555", secret_fn=lambda _: TOKEN)
    assert rc == 0
    env = st.read_env_file(str(trex))
    assert env["TELEGRAM_BOT_TOKEN"] == TOKEN
    assert env["TELEGRAM_CHAT_ID"] == "555555555"


def test_main_chat_not_found_explains_start(envs, monkeypatch, capsys):
    _, hermes = envs
    hermes.write_text(f"TELEGRAM_BOT_TOKEN={TOKEN}\n")
    monkeypatch.setattr(st, "telegram_call", _fake_telegram({
        "getMe": GET_ME_OK,
        "sendMessage": (400, {"ok": False, "description": "Bad Request: chat not found"}),
    }, []))
    assert st.main(["--chat-id", "123456789"]) == 1
    assert "press Start" in capsys.readouterr().out


def test_main_no_autosend_flag(envs, monkeypatch):
    trex, hermes = envs
    hermes.write_text(f"TELEGRAM_BOT_TOKEN={TOKEN}\n")
    monkeypatch.setattr(st, "telegram_call", _fake_telegram(
        {"getMe": GET_ME_OK, "sendMessage": SEND_OK}, []))
    st.main(["--chat-id", "123456789", "--no-autosend"])
    assert st.read_env_file(str(trex))["TELEGRAM_AUTOSEND"] == "false"
