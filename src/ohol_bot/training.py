from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class CurriculumStage:
    id: str
    description: str
    metrics: tuple[str, ...]
    scenario: str | None = None


def load_curriculum(path: str | Path) -> tuple[CurriculumStage, ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    stages: list[CurriculumStage] = []
    for raw in data.get("curriculum", []):
        stages.append(
            CurriculumStage(
                id=str(raw["id"]),
                description=str(raw["description"]),
                metrics=tuple(str(metric) for metric in raw.get("metrics", [])),
                scenario=raw.get("scenario"),
            )
        )
    return tuple(stages)


def score_episode(metrics: dict[str, Any], weights: dict[str, float]) -> float:
    score = 0.0
    for name, weight in weights.items():
        value = metrics.get(name, 0.0)
        if isinstance(value, bool):
            value = 1.0 if value else 0.0
        score += float(value) * weight
    return score
