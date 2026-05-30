from __future__ import annotations

import time
from dataclasses import dataclass

from .client import BotClient
from .model import Action, ActionType
from .policy import Policy
from .protocol_client import OholProtocolClient


@dataclass(frozen=True, slots=True)
class EpisodeResult:
    ticks: int
    actions: tuple[Action, ...]
    survived: bool
    metrics: dict[str, float]
    stop_reason: str = "normal"
    last_dashboard: str | None = None


def run_episode(client: BotClient, policy: Policy, max_ticks: int) -> EpisodeResult:
    actions: list[Action] = []
    min_food_ratio = 1.0

    for tick in range(max_ticks):
        observation = client.observe()
        min_food_ratio = min(min_food_ratio, observation.self.hunger_ratio)
        if observation.self.food_store <= 0:
            return EpisodeResult(
                ticks=tick,
                actions=tuple(actions),
                survived=False,
                metrics={"min_food_ratio": min_food_ratio},
            )

        action = policy.decide(observation)
        client.send(action)
        actions.append(action)

    return EpisodeResult(
        ticks=max_ticks,
        actions=tuple(actions),
        survived=True,
        metrics={"min_food_ratio": min_food_ratio},
    )


def run_live_episode(
    client: OholProtocolClient,
    policy: Policy,
    max_ticks: int,
    *,
    tick_seconds: float = 1.0,
    frame_paced: bool = False,
    watch: bool = False,
    forever: bool = False,
) -> EpisodeResult:
    if not client.logged_in:
        client.login()

    client.frame_paced = frame_paced
    actions: list[Action] = []
    min_food_ratio = 1.0
    final_tile = client.current_tile
    if watch:
        from .dashboard import format_dashboard, print_dashboard

    mode = "run-live (frame-paced)" if frame_paced else "run-live"
    interrupted = False
    connection_lost = False
    last_dashboard: str | None = None

    try:
        tick = 0
        while forever or tick < max_ticks:
            if frame_paced:
                if not client.wait_for_frame():
                    continue
            else:
                client.poll_until(tick_seconds)

            observation = client.observe()
            min_food_ratio = min(min_food_ratio, observation.self.hunger_ratio)
            final_tile = observation.self.tile

            if observation.self.max_food_store > 0 and observation.self.food_store <= 0:
                if watch:
                    frame = format_dashboard(
                        client,
                        observation,
                        last_action=actions[-1] if actions else None,
                        tick=tick,
                        mode=f"{mode} (starving)",
                    )
                    print_dashboard(frame)
                    last_dashboard = frame.text
                return EpisodeResult(
                    ticks=tick,
                    actions=tuple(actions),
                    survived=False,
                    metrics={
                        "min_food_ratio": min_food_ratio,
                        "final_x": float(final_tile.x),
                        "final_y": float(final_tile.y),
                        "server_frames": float(client.server_frames),
                    },
                    stop_reason="starvation",
                    last_dashboard=last_dashboard,
                )

            action = policy.decide(observation)
            if watch:
                frame = format_dashboard(
                    client,
                    observation,
                    last_action=action,
                    tick=tick,
                    mode=mode,
                )
                print_dashboard(frame)
                last_dashboard = frame.text

            client.send(action)
            actions.append(action)

            if not frame_paced and action.type is not ActionType.WAIT:
                client.poll_until(tick_seconds)

            tick += 1
    except KeyboardInterrupt:
        interrupted = True
    except ConnectionError:
        interrupted = False
        connection_lost = True
    else:
        interrupted = False
        connection_lost = False
    finally:
        client.close()

    stop_reason = (
        "keyboard_interrupt"
        if interrupted
        else "connection_lost"
        if connection_lost
        else "normal"
    )
    if connection_lost and watch:
        print("\nConnection closed by server.")
    return EpisodeResult(
        ticks=len(actions),
        actions=tuple(actions),
        survived=not connection_lost,
        metrics={
            "min_food_ratio": min_food_ratio,
            "final_x": float(final_tile.x),
            "final_y": float(final_tile.y),
            "server_frames": float(client.server_frames),
        },
        stop_reason=stop_reason,
        last_dashboard=last_dashboard,
    )
