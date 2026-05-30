from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class IntegrationPath(str, Enum):
    MODIFIED_CLIENT = "modified_client"
    HEADLESS_PROTOCOL = "headless_protocol"
    COMMUNITY_RELAY = "community_relay"


@dataclass(frozen=True, slots=True)
class BotInterfaceDecision:
    selected: IntegrationPath
    reason: str
    next_probe: str


def choose_initial_interface() -> BotInterfaceDecision:
    """Document the current control-path decision in executable form.

    The scaffold starts with the headless protocol shape because it is the best
    long-term fit for many bot instances, while keeping the client bridge
    swappable if a modified C++ client proves faster to bootstrap.
    """

    return BotInterfaceDecision(
        selected=IntegrationPath.HEADLESS_PROTOCOL,
        reason=(
            "Best long-term path for running many bots without rendering, but "
            "the first real milestone is only to mirror enough OHOL protocol "
            "messages to observe nearby state and send legal action intents."
        ),
        next_probe=(
            "Trace login, map chunk, player update, movement, pickup, drop, "
            "use, and speech messages from the official client source."
        ),
    )
