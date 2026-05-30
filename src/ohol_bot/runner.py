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
    engine = LiveSessionEngine(
        client,
        policy,
        max_ticks=max_ticks,
        tick_seconds=tick_seconds,
        frame_paced=frame_paced,
        watch=watch,
        forever=forever,
    )
    return engine.run()


class LiveSessionEngine:
    """Orchestrates the live observe -> decide -> act loop."""

    def __init__(
        self,
        client: OholProtocolClient,
        policy: Policy,
        *,
        max_ticks: int,
        tick_seconds: float = 1.0,
        frame_paced: bool = False,
        watch: bool = False,
        forever: bool = False,
    ) -> None:
        self.client = client
        self.policy = policy
        self.max_ticks = max_ticks
        self.tick_seconds = tick_seconds
        self.frame_paced = frame_paced
        self.watch = watch
        self.forever = forever
        self.actions: list[Action] = []
        self.min_food_ratio = 1.0
        self.final_tile = client.current_tile
        self.interrupted = False
        self.connection_lost = False
        self.last_dashboard: str | None = None
        self.mode = "run-live (frame-paced)" if frame_paced else "run-live"

    def run(self) -> EpisodeResult:
        if not self.client.logged_in:
            self.client.login()

        self.client.frame_paced = self.frame_paced
        if self.watch:
            from .dashboard import format_dashboard, print_dashboard

            self._format_dashboard = format_dashboard
            self._print_dashboard = print_dashboard

        try:
            tick = 0
            while self.forever or tick < self.max_ticks:
                if not self._wait_for_tick():
                    continue

                observation = self.client.observe()
                self.min_food_ratio = min(self.min_food_ratio, observation.self.hunger_ratio)
                self.final_tile = observation.self.tile

                if self._is_starving(observation):
                    return self._starvation_result(tick, observation)

                action = self.policy.decide(observation)
                self._render_dashboard(observation, action, tick=tick, mode=self.mode)

                self.client.send(action)
                self.actions.append(action)

                if not self.frame_paced and action.type is not ActionType.WAIT:
                    self.client.poll_until(self.tick_seconds)

                tick += 1
        except KeyboardInterrupt:
            self.interrupted = True
        except ConnectionError:
            self.connection_lost = True
        finally:
            self.client.close()

        return self._final_result()

    def _wait_for_tick(self) -> bool:
        if self.frame_paced:
            return self.client.wait_for_frame()
        self.client.poll_until(self.tick_seconds)
        return True

    def _is_starving(self, observation) -> bool:
        return (
            observation.self.max_food_store > 0
            and observation.self.food_store <= 0
        )

    def _render_dashboard(self, observation, action: Action | None, *, tick: int, mode: str) -> None:
        if not self.watch:
            return
        frame = self._format_dashboard(
            self.client,
            observation,
            last_action=action,
            tick=tick,
            mode=mode,
        )
        self._print_dashboard(frame)
        self.last_dashboard = frame.text

    def _starvation_result(self, tick: int, observation) -> EpisodeResult:
        self._render_dashboard(
            observation,
            self.actions[-1] if self.actions else None,
            tick=tick,
            mode=f"{self.mode} (starving)",
        )
        return EpisodeResult(
            ticks=tick,
            actions=tuple(self.actions),
            survived=False,
            metrics={
                "min_food_ratio": self.min_food_ratio,
                "final_x": float(self.final_tile.x),
                "final_y": float(self.final_tile.y),
                "server_frames": float(self.client.server_frames),
            },
            stop_reason="starvation",
            last_dashboard=self.last_dashboard,
        )

    def _final_result(self) -> EpisodeResult:
        stop_reason = (
            "keyboard_interrupt"
            if self.interrupted
            else "connection_lost"
            if self.connection_lost
            else "normal"
        )
        if self.connection_lost and self.watch:
            print("\nConnection closed by server.")
        return EpisodeResult(
            ticks=len(self.actions),
            actions=tuple(self.actions),
            survived=not self.connection_lost,
            metrics={
                "min_food_ratio": self.min_food_ratio,
                "final_x": float(self.final_tile.x),
                "final_y": float(self.final_tile.y),
                "server_frames": float(self.client.server_frames),
            },
            stop_reason=stop_reason,
            last_dashboard=self.last_dashboard,
        )
