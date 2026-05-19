#!/usr/bin/env python3
"""Registra el menú de comandos del bot en Telegram (setMyCommands).

Útil si el menú no aparece tras deploy: no hace falta esperar a /start en Lambda.

  py scripts/register_telegram_commands.py --profile asap_dev
  py scripts/register_telegram_commands.py --token "123:ABC..."
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

# Raíz del repo en PYTHONPATH para importar bot_commands
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_LAMBDA_DIR = os.path.join(_REPO_ROOT, "infrastructure", "lambdas", "telegram_webhook")
if _LAMBDA_DIR not in sys.path:
    sys.path.insert(0, _LAMBDA_DIR)

from bot_commands import BOT_COMMANDS  # noqa: E402

TG_API = "https://api.telegram.org"
SECRET_ID = os.environ.get("TELEGRAM_SECRET_ID", "SCALONIA_TELEGRAM_BOT_TOKEN")


def _token_from_secrets(profile: str | None, region: str) -> str:
    import boto3

    sess = boto3.Session(profile_name=profile, region_name=region) if profile else boto3.Session(
        region_name=region
    )
    return sess.client("secretsmanager").get_secret_value(SecretId=SECRET_ID)["SecretString"]


def main() -> None:
    p = argparse.ArgumentParser(description="setMyCommands para @scalonia_bot")
    p.add_argument("--token", default=os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    p.add_argument("--profile", default=os.environ.get("AWS_PROFILE", "asap_dev"))
    p.add_argument("--region", default="us-east-1")
    args = p.parse_args()

    token = args.token.strip()
    if not token:
        token = _token_from_secrets(args.profile or None, args.region)

    body = json.dumps(
        {"commands": BOT_COMMANDS, "scope": {"type": "all_private_chats"}},
    ).encode()
    req = urllib.request.Request(
        f"{TG_API}/bot{token}/setMyCommands",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    if not data.get("ok"):
        raise SystemExit(f"setMyCommands falló: {data}")
    print("OK — comandos registrados:")
    for c in BOT_COMMANDS:
        print(f"  /{c['command']} — {c['description']}")
    print("\nEn Telegram: abrí el chat con el bot, salí y volvé a entrar (o reiniciá la app).")
    print("El menú está al lado del campo de mensaje (ícono / o ☰).")


if __name__ == "__main__":
    main()
