"""Rutas SSM del guardrail — alineadas con infrastructure/terraform/guardrails."""

DEFAULT_PROJECT_NAME = "prode-mundial"


def guardrail_id_parameter(env: str, project_name: str = DEFAULT_PROJECT_NAME) -> str:
    return f"/{project_name}/{env}/guardrail_id"


def guardrail_version_parameter(env: str, project_name: str = DEFAULT_PROJECT_NAME) -> str:
    return f"/{project_name}/{env}/guardrail_version"
