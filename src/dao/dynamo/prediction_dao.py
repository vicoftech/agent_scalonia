"""
src/dao/dynamo/prediction_dao.py
PK=USER#<userId>  SK=PRED#<matchId>
SPEC: SPEC-2026-002 | TASK: TASK-004 | Modo: IA-Autonomous
"""
import os
from dataclasses import dataclass
from typing import Optional
import boto3
from boto3.dynamodb.conditions import Key, Attr

TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "ProdeTable")


@dataclass
class Prediction:
    user_id: str; match_id: str
    home_goals: int; away_goals: int
    status: str        # ACTIVE | SUPERSEDED | SCORED
    created_at: str; updated_at: str
    points_earned: Optional[int] = None
    scoring_reason: Optional[str] = None


class PredictionDAO:
    def __init__(self):
        self._table = boto3.resource("dynamodb").Table(TABLE_NAME)

    def check_veda_active(self, match_id: str) -> bool:
        """SIEMPRE llamar antes de save_prediction. Fuente de verdad: DynamoDB."""
        raise NotImplementedError("TASK-004")

    def save_prediction(self, user_id: str, match_id: str, home: int, away: int) -> Prediction:
        """PutItem con ConditionExpression=attribute_not_exists. Idempotente."""
        raise NotImplementedError("TASK-004")

    def update_prediction(self, user_id: str, match_id: str, home: int, away: int) -> Prediction:
        """Anterior → SUPERSEDED, nueva → ACTIVE. Solo si veda inactiva."""
        raise NotImplementedError("TASK-004")

    def get_prediction(self, user_id: str, match_id: str) -> Optional[Prediction]:
        """GetItem directo. Sub-5ms."""
        raise NotImplementedError("TASK-004")

    def list_user_predictions(self, user_id: str) -> list[Prediction]:
        """Query PK=USER#<userId> SK begins_with PRED#"""
        raise NotImplementedError("TASK-004")

    def get_predictions_for_match(self, match_id: str) -> list[Prediction]:
        """Query GSI-2-match-predictions. Para sync y notificaciones post-resultado."""
        raise NotImplementedError("TASK-004")
