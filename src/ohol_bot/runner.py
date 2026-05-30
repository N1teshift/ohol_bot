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
                    print_dashboard(
                        format_dashboard(
                            client,
                            observation,
                            last_action=actions[-1] if actions else None,
                            tick=tick,
                            mode=f"{mode} (starving)",
                        )
                    )
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
                )

            action = policy.decide(observation)
            if watch:
                print_dashboard(
                    format_dashboard(
                        client,
                        observation,
                        last_action=action,
                        tick=tick,
                        mode=mode,
                    )
                )

            client.send(action)
            actions.append(action)

            if not frame_paced and action.type is not ActionType.WAIT:
                client.poll_until(tick_seconds)

            tick += 1
    except KeyboardInterrupt:
        pass
    except ConnectionError:
        if watch:
            _clear_screen_on_exit()
            print("Connection closed by server.")
    finally:
        client.close()

    return EpisodeResult(
        ticks=len(actions),
        actions=tuple(actions),
        survived=True,
        metrics={
            "min_food_ratio": min_food_ratio,
            "final_x": float(final_tile.x),
            "final_y": float(final_tile.y),
            "server_frames": float(client.server_frames),
        },
    )


def _clear_screen_on_exit() -> None:
    from .dashboard import _clear_screen

    _clear_screen()
