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

from bot_commands import commands_for_user  # noqa: E402

TG_API = "https://api.telegram.org"
SECRET_ID = os.environ.get("TELEGRAM_SECRET_ID", "SCALONIA_TELEGRAM_BOT_TOKEN")


def _token_from_secrets(profile: str | None, region: str) -> str:
    import boto3

    sess = boto3.Session(profile_name=profile, region_name=region) if profile else boto3.Session(
        region_name=region
    )
    return sess.client("secretsmanager").get_secret_value(SecretId=SECRET_ID)["SecretString"]


def _set_commands(token: str, commands: list[dict], scope: dict) -> dict:
    body = json.dumps({"commands": commands, "scope": scope}).encode()
    req = urllib.request.Request(
        f"{TG_API}/bot{token}/setMyCommands",
        data=body,
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
        help="Chat id del admin para menú con trivia_admin y admin_grupos",
    )
    args = p.parse_args()

    token = args.token.strip()
    if not token:
        token = _token_from_secrets(args.profile or None, args.region)

    default_cmds = commands_for_user(is_admin=False)
    data = _set_commands(token, default_cmds, {"type": "all_private_chats"})
    if not data.get("ok"):
        raise SystemExit(f"setMyCommands (default) falló: {data}")

    print(f"OK — menú global ({len(default_cmds)} comandos):")
    for c in default_cmds:
        print(f"  /{c['command']} — {c['description']}")

    if args.admin_chat_id:
        admin_cmds = commands_for_user(is_admin=True)
        data2 = _set_commands(
            token,
            admin_cmds,
            {"type": "chat", "chat_id": int(args.admin_chat_id)},
        )
        if not data2.get("ok"):
            raise SystemExit(f"setMyCommands (admin chat) falló: {data2}")
        admin_only = {x["command"] for x in ADMIN_COMMANDS}
        print(f"\nOK — menú admin chat {args.admin_chat_id} ({len(admin_cmds)} comandos):")
        for c in admin_cmds:
            suffix = " (admin)" if c["command"] in admin_only else ""
            print(f"  /{c['command']} — {c['description']}{suffix}")

    print("\nEn Telegram: cerrá y reabrí el chat con el bot (o /help) para refrescar el menú /.")


if __name__ == "__main__":
    main()
