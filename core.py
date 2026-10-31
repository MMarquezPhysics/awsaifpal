"""Question selection, scoring, and saved-attempt logic for AWS AIF Pal."""

from __future__ import annotations

import json
import random
import time
from pathlib import Path


BANK_PATH = Path(__file__).parent / "data" / "bank.json"
DOMAINS = {
    1: "Fundamentals of AI and ML",
    2: "Fundamentals of GenAI",
    3: "Applications of foundation models",
    4: "Responsible AI",
    5: "Security and governance",
}


def load_bank() -> list[dict]:
    with BANK_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def select_questions(pool: list[dict], count: int, rng: random.Random | None = None) -> list[dict]:
    """Randomly select questions, avoiding repeated concept families when possible."""
    rng = rng or random.SystemRandom()
    count = min(count, len(pool))
    sample = rng.sample(pool, count)
    source_counts: dict[str, int] = {}
    for question in sample:
        source_counts[question["origin"]] = source_counts.get(question["origin"], 0) + 1
    chosen = []
    for origin, needed in source_counts.items():
        candidates = [question for question in pool if question["origin"] == origin]
        rng.shuffle(candidates)
        fresh, repeated, families = [], [], set()
        for question in candidates:
            family = question.get("family", question["id"])
            if family in families:
                repeated.append(question)
            else:
                families.add(family)
                fresh.append(question)
        chosen.extend((fresh + repeated)[:needed])
    rng.shuffle(chosen)
    return [
        {"id": question["id"], "order": rng.sample(range(len(question["options"])), len(question["options"]))}
        for question in chosen
    ]


def new_session(bank: list[dict], source: str, mode: str, count: int, minutes: int, now_ms: int | None = None) -> dict:
    pool = bank if source == "all" else [question for question in bank if question["origin"] == source]
    if not pool or not 1 <= count <= len(bank) or not 1 <= minutes <= 600 or mode not in {"exam", "guide"}:
        raise ValueError("Invalid session settings")
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    return {
        "version": 1,
        "source": source,
        "mode": mode,
        "items": select_questions(pool, count),
        "current": 0,
        "responses": {},
        "checked": {},
        "startedAt": now_ms,
        "endsAt": now_ms + minutes * 60_000,
        "completedAt": None,
        "finishReason": None,
    }


def is_correct(question: dict, response: list[int] | None) -> bool:
    return sorted(response or []) == sorted(question["answer"])


def correct_count(session: dict, by_id: dict[str, dict]) -> int:
    return sum(is_correct(by_id[item["id"]], session["responses"].get(item["id"])) for item in session["items"])


def score(session: dict, by_id: dict[str, dict]) -> float:
    return correct_count(session, by_id) * 1000 / len(session["items"])


def finish_session(session: dict, by_id: dict[str, dict], now_ms: int | None = None) -> dict:
    """Finish once and return a history row; repeat calls return the same row."""
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    if session.get("completedAt") is None:
        session["completedAt"] = now_ms
        session["finishReason"] = "time" if now_ms >= session["endsAt"] else "user"
    completed = session["completedAt"]
    return {
        "id": f"{session['startedAt']}-{completed}-{len(session['items'])}",
        "completedAt": completed,
        "mode": session["mode"],
        "questions": len(session["items"]),
        "elapsedMs": max(0, min(completed, session["endsAt"]) - session["startedAt"]),
        "correct": correct_count(session, by_id),
        "source": session["source"],
        "finishReason": session["finishReason"],
    }


def valid_session(value: object, by_id: dict[str, dict]) -> bool:
    if not isinstance(value, dict):
        return False
    try:
        items = value["items"]
        return (
            value["mode"] in {"exam", "guide"}
            and isinstance(items, list)
            and bool(items)
            and all(item["id"] in by_id and sorted(item["order"]) == list(range(len(by_id[item["id"]]["options"]))) for item in items)
            and isinstance(value["responses"], dict)
            and isinstance(value["startedAt"], int)
            and isinstance(value["endsAt"], int)
            and isinstance(value["current"], int)
            and 0 <= value["current"] < len(items)
        )
    except (KeyError, TypeError, ValueError):
        return False


def valid_attempt(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    try:
        return (
            isinstance(value["id"], str)
            and isinstance(value["completedAt"], (int, float))
            and value["mode"] in {"exam", "guide"}
            and isinstance(value["questions"], int)
            and value["questions"] > 0
            and isinstance(value["correct"], int)
            and 0 <= value["correct"] <= value["questions"]
            and isinstance(value["elapsedMs"], (int, float))
            and value["elapsedMs"] >= 0
        )
    except (KeyError, TypeError):
        return False


def merge_attempts(attempts: list[dict], row: dict) -> list[dict]:
    return list({item["id"]: item for item in [*attempts, row]}.values())
