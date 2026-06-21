from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class HarvestRule:
    query: str
    display_name: str
    plant_object_ids: tuple[int, ...] = ()
    plant_names: tuple[str, ...] = ()
    dug_object_id: int | None = None
    dug_names: tuple[str, ...] = ()
    product_object_id: int | None = None
    product_names: tuple[str, ...] = ()
    tool_object_ids: tuple[int, ...] = ()
    tool_names: tuple[str, ...] = ()
    query_aliases: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "display_name": self.display_name,
            "plant_object_ids": self.plant_object_ids,
            "plant_names": self.plant_names,
            "dug_object_id": self.dug_object_id,
            "dug_names": self.dug_names,
            "product_object_id": self.product_object_id,
            "product_names": self.product_names,
            "tool_object_ids": self.tool_object_ids,
            "tool_names": self.tool_names,
            "query_aliases": self.query_aliases,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> HarvestRule:
        return cls(
            query=str(raw.get("query", "")),
            display_name=str(raw.get("display_name", "item")),
            plant_object_ids=tuple(int(v) for v in raw.get("plant_object_ids", ())),
            plant_names=tuple(str(v) for v in raw.get("plant_names", ())),
            dug_object_id=_optional_int(raw.get("dug_object_id")),
            dug_names=tuple(str(v) for v in raw.get("dug_names", ())),
            product_object_id=_optional_int(raw.get("product_object_id")),
            product_names=tuple(str(v) for v in raw.get("product_names", ())),
            tool_object_ids=tuple(int(v) for v in raw.get("tool_object_ids", ())),
            tool_names=tuple(str(v) for v in raw.get("tool_names", ())),
            query_aliases=tuple(str(v) for v in raw.get("query_aliases", ())),
        )


@dataclass(frozen=True, slots=True)
class StackCollectRule:
    display_name: str
    loose_names: frozenset[str] = field(default_factory=frozenset)
    pile_names: frozenset[str] = field(default_factory=frozenset)
    loose_object_id: int | None = None
    pile_object_id: int | None = None
    depot_target_ids: tuple[int, ...] = ()
    source_target_ids: tuple[int, ...] = ()
    query_aliases: frozenset[str] = field(default_factory=frozenset)
    drop_only: bool = False
    harvest: HarvestRule | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "display_name": self.display_name,
            "loose_names": tuple(sorted(self.loose_names)),
            "pile_names": tuple(sorted(self.pile_names)),
            "loose_object_id": self.loose_object_id,
            "pile_object_id": self.pile_object_id,
            "depot_target_ids": self.depot_target_ids,
            "source_target_ids": self.source_target_ids,
            "query_aliases": tuple(sorted(self.query_aliases)),
            "drop_only": self.drop_only,
        }
        if self.harvest is not None:
            payload["harvest"] = self.harvest.to_dict()
        return payload

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> StackCollectRule:
        harvest_raw = raw.get("harvest")
        harvest = (
            HarvestRule.from_dict(harvest_raw)
            if isinstance(harvest_raw, Mapping)
            else None
        )
        return cls(
            display_name=str(raw.get("display_name", "item")),
            loose_names=frozenset(str(v) for v in raw.get("loose_names", ())),
            pile_names=frozenset(str(v) for v in raw.get("pile_names", ())),
            loose_object_id=_optional_int(raw.get("loose_object_id")),
            pile_object_id=_optional_int(raw.get("pile_object_id")),
            depot_target_ids=tuple(int(v) for v in raw.get("depot_target_ids", ())),
            source_target_ids=tuple(int(v) for v in raw.get("source_target_ids", ())),
            query_aliases=frozenset(str(v) for v in raw.get("query_aliases", ())),
            drop_only=bool(raw.get("drop_only", False)),
            harvest=harvest,
        )


def _optional_int(raw: Any) -> int | None:
    if isinstance(raw, int):
        return raw
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
