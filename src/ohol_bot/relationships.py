from __future__ import annotations

from .game_data import OholGameData
from .model import PlayerState

_ORDINALS: dict[int, str] = {
    1: "1st",
    2: "2nd",
    3: "3rd",
    4: "4th",
    5: "5th",
    6: "6th",
    7: "7th",
    8: "8th",
    9: "9th",
    10: "10th",
    11: "11th",
    12: "12th",
    13: "13th",
    14: "14th",
    15: "15th",
    16: "16th",
    17: "17th",
    18: "18th",
    19: "19th",
    20: "20th",
}


def _they_male(game_data: OholGameData | None, display_id: int | None) -> bool:
    if game_data is None or display_id is None:
        return True
    obj = game_data.objects.get(display_id)
    if obj is None:
        return True
    return obj.male


def relation_name(
    self_player: PlayerState,
    other: PlayerState,
    *,
    game_data: OholGameData | None,
) -> str | None:
    our_lin = self_player.ancestor_ids
    their_lin = other.ancestor_ids
    our_id = self_player.player_id
    their_id = other.player_id
    our_display_id = self_player.display_id
    their_display_id = other.display_id
    our_age = self_player.age
    their_age = other.age
    our_eve_id = self_player.lineage_id if self_player.lineage_id is not None else -1
    their_eve_id = other.lineage_id if other.lineage_id is not None else -1

    they_male = _they_male(game_data, their_display_id)

    if len(our_lin) == 0 and len(their_lin) == 0:
        return None

    main = ""
    grand = False
    num_greats = 0
    cousin_num = 0
    cousin_removed_num = 0
    found = False

    for index, ancestor_id in enumerate(their_lin):
        if ancestor_id == our_id:
            found = True
            main = "son" if they_male else "daughter"
            if index > 0:
                grand = True
            num_greats = index - 1
            break

    if not found:
        for index, ancestor_id in enumerate(our_lin):
            if ancestor_id == their_id:
                found = True
                main = "mother"
                if index > 0:
                    grand = True
                num_greats = index - 1
                break

    big = False
    little = False
    twin = False
    identical = False

    if not found:
        our_match_index = -1
        their_match_index = -1
        for i, our_ancestor in enumerate(our_lin):
            for j, their_ancestor in enumerate(their_lin):
                if our_ancestor == their_ancestor:
                    our_match_index = i
                    their_match_index = j
                    break
            if our_match_index != -1:
                break

        if our_match_index == -1:
            if our_eve_id != -1 and their_eve_id != -1 and our_eve_id == their_eve_id:
                return "your distant relative"
            return None

        found = True
        if their_match_index == 0 and our_match_index == 0:
            main = "brother" if they_male else "sister"
            if our_age < their_age - 0.1:
                big = True
            elif our_age > their_age + 0.1:
                little = True
            else:
                twin = True
                if our_display_id is not None and our_display_id == their_display_id:
                    identical = True
        elif their_match_index == 0:
            main = "uncle" if they_male else "aunt"
            num_greats = our_match_index - 1
        elif our_match_index == 0:
            main = "nephew" if they_male else "niece"
            num_greats = their_match_index - 1
        else:
            main = "cousin"
            if our_match_index <= their_match_index:
                cousin_num = our_match_index
                cousin_removed_num = their_match_index - our_match_index
            else:
                cousin_num = their_match_index
                cousin_removed_num = our_match_index - their_match_index

    if not found:
        return None

    prefix_parts: list[str] = ["your"]

    if num_greats <= 4:
        prefix_parts.extend(["great"] * num_greats)
    elif num_greats > 0:
        prefix_parts.append(f"{num_greats}X great")

    if cousin_num > 0:
        remaining_cousin_num = cousin_num
        if cousin_num >= 30:
            prefix_parts.append("distant")
            remaining_cousin_num = 0
        if cousin_num > 20 and cousin_num < 30:
            prefix_parts.append("twenty-")
            remaining_cousin_num = cousin_num - 20
        if remaining_cousin_num > 0:
            ordinal = _ORDINALS.get(remaining_cousin_num, f"{remaining_cousin_num}th")
            prefix_parts.append(ordinal)

    if little:
        prefix_parts.append("little")
    elif big:
        prefix_parts.append("big")
    elif twin:
        if identical:
            prefix_parts.append("identical")
        prefix_parts.append("twin")

    main_label = main
    if grand:
        main_label = f"grand{main}"

    suffix_parts: list[str] = []
    if cousin_removed_num > 0:
        if cousin_removed_num > 9:
            suffix_parts.append("many times removed")
        else:
            suffix_parts.append(f"{cousin_removed_num} times removed")

    body = " ".join(prefix_parts[1:] + ([main_label] if main_label else []))
    if suffix_parts:
        body = f"{body} {' '.join(suffix_parts)}"
    return f"{prefix_parts[0]} {body}".strip()
