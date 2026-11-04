from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def workspace_tmp() -> Path:
    base = Path.cwd() / ".pytest-tmp"
    path = base / uuid4().hex
    path.mkdir(parents=True)
    return path
