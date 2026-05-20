"""SPEC-2026-027 — entrypoint sin importar trivia_service (cadena src.jobs)."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]


def test_main_py_does_not_import_trivia_service():
    """Regresión RC-1: agent/main.py no debe importar trivia_service al cargar."""
    source = (_REPO / "agent" / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.services.trivia_service":
            pytest.fail("agent/main.py importa src.services.trivia_service — usar agent.prompt_sections")


def test_main_imports_trivia_section_from_prompt_sections():
    source = (_REPO / "agent" / "main.py").read_text(encoding="utf-8")
    assert "from agent.prompt_sections import TRIVIA_SECTION" in source


def test_prompt_sections_loads_without_heavy_deps():
    if str(_REPO) not in sys.path:
        sys.path.insert(0, str(_REPO))
    import importlib

    mod = importlib.import_module("agent.prompt_sections")
    assert "Trivias" in mod.TRIVIA_SECTION


def test_trivia_service_imports_jobs_when_present():
    """Defensa A2: trivia_service requiere src.jobs (debe estar en build-agent-zip)."""
    jobs_init = _REPO / "src" / "jobs" / "__init__.py"
    assert jobs_init.is_file()
    if str(_REPO) not in sys.path:
        sys.path.insert(0, str(_REPO))
    import importlib

    mod = importlib.import_module("src.services.trivia_service")
    assert hasattr(mod, "TriviaService")
