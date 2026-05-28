#!/usr/bin/env python3
"""Registra el menú de comandos del bot en Telegram (setMyCommands).

Útil tras deploy o cuando el menú no se actualizó solo:

  py scripts/register_telegram_commands.py --profile asap_dev
  py scripts/register_telegram_commands.py --token "123:ABC..." --admin-chat-id 123456789
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_LAMBDA_DIR = os.path.join(_REPO_ROOT, "infrastructure", "lambdas", "telegram_webhook")
if _LAMBDA_DIR not in sys.path:
    sys.path.insert(0, _LAMBDA_DIR)

from bot_commands import (  # noqa: E402
    ADMIN_MENU_EXTRA,
    USER_MENU_COMMANDS,
    commands_for_user,
    sync_commands_for_chat,
)

TG_API = "https://api.telegram.org"
SECRET_ID = os.environ.get("TELEGRAM_SECRET_ID", "SCALONIA_TELEGRAM_BOT_TOKEN")


def _token_from_secrets(profile: str | None, region: str) -> str:
    import boto3

    sess = boto3.Session(profile_name=profile, region_name=region) if profile else boto3.Session(
        region_name=region
    )
    return sess.client("secretsmanager").get_secret_value(SecretId=SECRET_ID)["SecretString"]


def _api(token: str, method: str, body: dict) -> dict:
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{TG_API}/bot{token}/{method}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    p = argparse.ArgumentParser(description="setMyCommands para @scalonia_bot")
    p.add_argument("--token", default=os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    p.add_argument("--profile", default=os.environ.get("AWS_PROFILE", "asap_dev"))
    p.add_argument("--region", default="us-east-1")
    p.add_argument(
        "--admin-chat-id",
        type=int,
        default=0,
        help="Chat id del admin para menú extendido (scope chat)",
    )
    p.add_argument(
        "--user-chat-id",
        type=int,
        default=0,
        help="Chat id de un usuario común para borrar menú admin viejo (deleteMyCommands)",
    )
    args = p.parse_args()

    token = args.token.strip()
    if not token:
        token = _token_from_secrets(args.profile or None, args.region)

    public_cmds = commands_for_user(is_admin=False)
    data = _api(
        token,
        "setMyCommands",
        {"commands": public_cmds, "scope": {"type": "all_private_chats"}},
    )
    if not data.get("ok"):
        raise SystemExit(f"setMyCommands (global) falló: {data}")

    print(f"OK — menú global usuario ({len(public_cmds)} comandos):")
    for c in public_cmds:
        print(f"  /{c['command']} — {c['description']}")

    if args.admin_chat_id:
        sync_commands_for_chat(token, int(args.admin_chat_id), is_admin=True)
        admin_cmds = commands_for_user(is_admin=True)
        admin_only = {x["command"] for x in ADMIN_MENU_EXTRA}
        print(f"\nOK — menú admin chat {args.admin_chat_id} ({len(admin_cmds)} comandos):")
        for c in admin_cmds:
            suffix = " [ADMIN]" if c["command"] in admin_only else ""
            print(f"  /{c['command']} — {c['description']}{suffix}")

    if args.user_chat_id:
        sync_commands_for_chat(token, int(args.user_chat_id), is_admin=False)
        print(f"\nOK — menú usuario chat {args.user_chat_id} (scope chat borrado → menú global)")

    print("\nEn Telegram: cerrá y reabrí el chat con el bot para ver el menú / actualizado.")
    print(f"Versión menú: v{os.environ.get('BOT_COMMANDS_VERSION', '8')}")
    print(f"Comandos usuario: {len(USER_MENU_COMMANDS)} | extra admin: {len(ADMIN_MENU_EXTRA)}")


if __name__ == "__main__":
    main()
