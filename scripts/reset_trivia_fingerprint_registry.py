#!/usr/bin/env python3
"""Reset CONFIG#TRIVIA/USED_QUESTION_FPS — solo dev/QA (SPEC-049)."""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.dao.dynamo.trivia_dao import REGISTRY_PK, REGISTRY_SK, TriviaDAO  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--table",
        default=os.environ.get("PRODE_TABLE_NAME", "ProdeTable-dev"),
        help="Nombre tabla DynamoDB",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirmar borrado del registry global de fingerprints",
    )
    args = parser.parse_args()
    if not args.yes:
        print("Usá --yes para vaciar el registry de trivias (solo dev).")
        return 1

    dao = TriviaDAO(table_name=args.table)
    dao._table.put_item(
        Item={
            "partition_key": REGISTRY_PK,
            "sort_key": REGISTRY_SK,
            "fingerprints": [],
            "updated_at": "reset",
        }
    )
    print(f"Registry vaciado en tabla {args.table}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
