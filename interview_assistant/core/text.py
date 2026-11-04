from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from ..config import resource_path
from ..models import AppSettings


DEFAULT_SYSTEM_PROMPT = """你是一个专业的面试助手，正在帮助面试者实时回答面试官提出的问题。

请遵循以下规则：
1. 回答控制在 200 至 400 字，方便面试者理解和复述。
2. 技术问题必须准确，代码示例保持简短。
3. 行为类问题使用 STAR 法则组织内容。
4. 语言自然、直接，像真人在面试中回答。
5. 问题不完整时先指出缺失信息并请求澄清。
6. 优先使用简历中的真实经历，不编造项目或成果。"""


def load_keyword_map(path: Optional[Path] = None) -> dict[str, str]:
    target = Path(path) if path else resource_path("keywords.txt")
    mapping: dict[str, str] = {}
    if not target.exists():
        return mapping
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return mapping
    for line in lines:
        parts = [part.strip() for part in line.strip().split(",") if part.strip()]
        if len(parts) < 2 or parts[0].startswith("#"):
            continue
        correct = parts[0]
        for wrong in parts[1:]:
            mapping[wrong.lower()] = correct
    return mapping


def correct_keywords(text_value: str, mapping: dict[str, str]) -> str:
    result = text_value
    for wrong in sorted(mapping, key=len, reverse=True):
        result = re.sub(re.escape(wrong), mapping[wrong], result, flags=re.IGNORECASE)
    return result


def load_qa_bank(path: Optional[Path] = None) -> list[dict]:
    target = Path(path) if path else resource_path("qa_bank.json")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def match_qa_bank(question: str, bank: list[dict]) -> Optional[str]:
    q_lower = question.lower()
    best_score = 0.0
    best_answer: Optional[str] = None
    for entry in bank:
        keywords = entry.get("keywords", [])
        if not keywords:
            continue
        hits = sum(1 for keyword in keywords if keyword.lower() in q_lower)
        ratio = hits / len(keywords)
        score = hits * 0.4 + ratio * 0.6
        if hits >= 2 and ratio >= 0.25 and score > best_score:
            best_score = score
            best_answer = entry.get("answer", "")
    return best_answer or None


def match_quick_response(question: str, self_intro: str) -> Optional[str]:
    normalized = question.lower().replace(" ", "")
    if self_intro and any(
        keyword in normalized
        for keyword in (
            "自我介绍",
            "介绍自己",
            "介绍下自己",
            "说说你自己",
            "做个自我介绍",
            "先自我介绍一下",
        )
    ):
        return self_intro
    return None


def read_resume(path: Path) -> str:
    path = Path(path)
    if not path.exists():
        return ""
    if path.suffix.lower() == ".pdf":
        try:
            import pdfplumber
            logging.getLogger("pdfminer").setLevel(logging.ERROR)

            with pdfplumber.open(path) as pdf:
                text_value = "\n".join(page.extract_text() or "" for page in pdf.pages)
        except Exception:
            return ""
    elif path.suffix.lower() == ".txt":
        try:
            text_value = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text_value = path.read_text(encoding="gbk", errors="ignore")
        except OSError:
            return ""
    else:
        return ""
    return text_value.strip() if len(text_value.strip()) > 50 else ""


def discover_resume(root: Path) -> Path | None:
    candidates: list[Path] = []
    try:
        for pattern in ("*简历*.pdf", "*简历*.txt", "*resume*.pdf", "*resume*.txt", "*cv*.pdf", "*cv*.txt"):
            candidates.extend(root.glob(pattern))
        if not candidates:
            candidates.extend(root.glob("*.pdf"))
            candidates.extend(
                path
                for path in root.glob("*.txt")
                if path.name.lower() not in {"keywords.txt", "requirements.txt"}
            )
    except OSError:
        return None
    return next((path for path in candidates if path.is_file()), None)


def build_system_prompt(settings: AppSettings, resume_text: str) -> str:
    base = settings.system_prompt.strip() or DEFAULT_SYSTEM_PROMPT
    if resume_text:
        base = (
            f"{base}\n\n"
            "## \u9762\u8bd5\u8005\u7b80\u5386\n"
            f"{resume_text}\n\n"
            "\u56de\u7b54\u65f6\u7d27\u6263\u4ee5\u4e0a\u771f\u5b9e\u7ecf\u5386\uff0c\u4e0d\u7f16\u9020\u9879\u76ee\u6216\u6210\u679c\u3002"
        )
    return (
        base
        + "\n\n\u8bf7\u76f4\u63a5\u8f93\u51fa\u6700\u7ec8\u56de\u7b54\uff0c\u4e0d\u5c55\u793a\u601d\u8003\u8fc7\u7a0b\u3002"
        + "\u5148\u7ed9\u7ed3\u8bba\uff0c\u518d\u7528\u7b80\u77ed\u8981\u70b9\u8bf4\u660e\uff0c\u5c3d\u91cf\u63a7\u5236\u5728 150\u81f3300 \u5b57\u3002"
    )
