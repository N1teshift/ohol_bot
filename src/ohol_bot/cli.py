from __future__ import annotations

import argparse
import json
from pathlib import Path

from .client import MockBotClient
from .live_behaviors import verify_live_behaviors
from .manual_control import run_manual_control
from .movement_policy import MovementFollowPolicy
from .planner import SurvivalPlanner
from .model import Action, ActionType, Tile
from .protocol_client import OholProtocolClient, OholProtocolProbe, ProtocolCredentials
from .runner import run_episode, run_live_episode, run_live_interactive_episode
from .session_log import finish_play_session, finish_run_live_session
from .scenario import load_scenario
from .server_log import connected_accounts, parse_server_log


def main() -> None:
    parser = argparse.ArgumentParser(prog="ohol-bot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scenario_parser = subparsers.add_parser("run-scenario")
    scenario_parser.add_argument("path", type=Path)
    scenario_parser.add_argument("--max-ticks", type=int, default=20)

    log_parser = subparsers.add_parser("parse-server-log")
    log_parser.add_argument("path", type=Path)

    login_probe_parser = subparsers.add_parser("login-probe")
    login_probe_parser.add_argument("--host", default="localhost")
    login_probe_parser.add_argument("--port", type=int, default=8005)
    login_probe_parser.add_argument("--email", default="bot_001@local")
    login_probe_parser.add_argument("--account-key", default="aaaa")
    login_probe_parser.add_argument("--client-id", default="client_mariusbottest")
    login_probe_parser.add_argument("--server-password", default="testPassword")
    login_probe_parser.add_argument("--tutorial", action="store_true")

    action_probe_parser = subparsers.add_parser("action-probe")
    action_probe_parser.add_argument("action", choices=[item.value for item in ActionType])
    action_probe_parser.add_argument("--host", default="localhost")
    action_probe_parser.add_argument("--port", type=int, default=8005)
    action_probe_parser.add_argument("--text", default="HELLO")
    action_probe_parser.add_argument("--x", type=int, default=0)
    action_probe_parser.add_argument("--y", type=int, default=0)
    action_probe_parser.add_argument("--ticks", type=int, default=1)

    stay_alive_parser = subparsers.add_parser("stay-alive")
    stay_alive_parser.add_argument("--host", default="localhost")
    stay_alive_parser.add_argument("--port", type=int, default=8005)
    stay_alive_parser.add_argument("--email", default="bot_001@local")
    stay_alive_parser.add_argument("--account-key", default="aaaa")
    stay_alive_parser.add_argument("--client-id", default="client_mariusbottest")
    stay_alive_parser.add_argument("--server-password", default="testPassword")
    stay_alive_parser.add_argument("--tutorial", action="store_true")
    stay_alive_parser.add_argument("--seconds", type=float, default=30.0)
    stay_alive_parser.add_argument("--keep-alive-interval", type=float, default=5.0)
    stay_alive_parser.add_argument("--say", default=None)
    stay_alive_parser.add_argument("--move-x", type=int, default=None)
    stay_alive_parser.add_argument("--watch", action="store_true")
    stay_alive_parser.add_argument("--watch-interval", type=float, default=0.5)

    run_live_parser = subparsers.add_parser("run-live")
    run_live_parser.add_argument("--host", default="localhost")
    run_live_parser.add_argument("--port", type=int, default=8005)
    run_live_parser.add_argument("--email", default="bot_001@local")
    run_live_parser.add_argument("--account-key", default="aaaa")
    run_live_parser.add_argument("--client-id", default="client_mariusbottest")
    run_live_parser.add_argument("--server-password", default="testPassword")
    run_live_parser.add_argument("--tutorial", action="store_true")
    run_live_parser.add_argument("--max-ticks", type=int, default=20)
    run_live_parser.add_argument(
        "--forever",
        action="store_true",
        help="Run until Ctrl+C or starvation (ignores --max-ticks)",
    )
    run_live_parser.add_argument("--tick-seconds", type=float, default=1.0)
    run_live_parser.add_argument(
        "--frame-paced",
        action="store_true",
        help="React once per server FM frame instead of --tick-seconds wall-clock polling",
    )
    run_live_parser.add_argument("--keep-alive-interval", type=float, default=5.0)
    run_live_parser.add_argument(
        "--game-data-root",
        default=".ohol_runtime/server",
        help="Sandbox path containing objects/ and transitions/",
    )
    run_live_parser.add_argument("--watch", action="store_true")
    run_live_parser.add_argument(
        "--session-log",
        type=Path,
        default=Path(".ohol_runtime/logs/last_run.json"),
        help="Overwrite this JSON file with the last run summary (default: .ohol_runtime/logs/last_run.json)",
    )
    run_live_parser.add_argument(
        "--session-log-actions",
        type=int,
        default=2000,
        help="Max action records written to the session log (tail of session; 0 = summary only)",
    )

    play_parser = subparsers.add_parser(
        "play",
        help="Unified autopilot + manual one-shot overrides with dashboard",
    )
    _add_connection_args(play_parser)
    play_parser.add_argument("--max-ticks", type=int, default=20)
    play_parser.add_argument(
        "--forever",
        action="store_true",
        default=True,
        help="Run until Ctrl+C or manual quit",
    )
    play_parser.add_argument("--tick-seconds", type=float, default=1.0)
    play_parser.add_argument(
        "--frame-paced",
        action="store_true",
        default=True,
        help="React once per server FM frame",
    )
    play_parser.add_argument("--keep-alive-interval", type=float, default=5.0)
    play_parser.add_argument(
        "--game-data-root",
        default=".ohol_runtime/server",
        help="Sandbox path containing objects/ and transitions/",
    )
    play_parser.add_argument(
        "--session-log",
        type=Path,
        default=Path(".ohol_runtime/logs/last_play.json"),
        help="Overwrite this JSON file with the last play summary",
    )
    play_parser.add_argument(
        "--session-log-actions",
        type=int,
        default=2000,
        help="Max action records written to the play session log (tail of session; 0 = summary only)",
    )

    control_parser = subparsers.add_parser(
        "control",
        help="Interactive manual control (move N tiles east/south/…)",
    )
    _add_connection_args(control_parser)
    control_parser.add_argument(
        "--frame-paced",
        action="store_true",
        help="Wait for one server FM frame before each step",
    )
    control_parser.add_argument(
        "--watch",
        action="store_true",
        help="Show dashboard after each command",
    )
    control_parser.add_argument(
        "--keep-alive-interval", type=float, default=5.0
    )
    control_parser.add_argument(
        "--game-data-root",
        default=".ohol_runtime/server",
        help="Sandbox path containing objects/ and transitions/",
    )
    control_parser.add_argument(
        "manual_command",
        nargs="*",
        metavar="CMD",
        help='Optional one-shot command, e.g. move 10 east (otherwise interactive REPL)',
    )

    verify_live_parser = subparsers.add_parser("verify-live")
    verify_live_parser.add_argument("--host", default="localhost")
    verify_live_parser.add_argument("--port", type=int, default=8005)
    verify_live_parser.add_argument("--email", default="bot_001@local")
    verify_live_parser.add_argument("--account-key", default="aaaa")
    verify_live_parser.add_argument("--client-id", default="client_mariusbottest")
    verify_live_parser.add_argument("--server-password", default="testPassword")
    verify_live_parser.add_argument("--tutorial", action="store_true")
    verify_live_parser.add_argument("--keep-alive-interval", type=float, default=5.0)
    verify_live_parser.add_argument("--settle-seconds", type=float, default=5.0)
    verify_live_parser.add_argument(
        "--game-data-root",
        default=".ohol_runtime/server",
    )

    args = parser.parse_args()

    if args.command == "run-scenario":
        observations = load_scenario(args.path)
        client = MockBotClient(observations)
        result = run_episode(client, SurvivalPlanner(), args.max_ticks)
        print(
            json.dumps(
                {
                    "survived": result.survived,
                    "ticks": result.ticks,
                    "metrics": result.metrics,
                    "actions": [
                        {"type": action.type.value, "payload": action.payload}
                        for action in result.actions
                    ],
                },
                indent=2,
            )
        )
    elif args.command == "parse-server-log":
        events = parse_server_log(args.path)
        print(
            json.dumps(
                {
                    "event_count": len(events),
                    "connected_accounts": connected_accounts(events),
                    "events": [
                        {
                            "type": event.type.value,
                            "line_number": event.line_number,
                            "player_id": event.player_id,
                            "account": event.account,
                            "message": event.message,
                            "x": event.x,
                            "y": event.y,
                        }
                        for event in events
                    ],
                },
                indent=2,
            )
        )
    elif args.command == "login-probe":
        probe = OholProtocolProbe(
            host=args.host,
            port=args.port,
            credentials=ProtocolCredentials(
                email=args.email,
                account_key=args.account_key,
                client_id=args.client_id,
                server_password=args.server_password,
                tutorial=args.tutorial,
            ),
        )
        try:
            probe.login_probe()
            response = probe.try_read()
            print(
                json.dumps(
                    {
                        "connected": True,
                        "sent_messages": probe.sent_messages,
                        "received_hex": response.hex(),
                        "received_text": response.decode("utf-8", errors="replace"),
                        "parsed_messages": [
                            {"type": message.type.value, "raw": message.raw}
                            for message in probe.parsed_messages
                        ],
                    },
                    indent=2,
                )
            )
        finally:
            probe.close()
    elif args.command == "action-probe":
        probe = OholProtocolClient(host=args.host, port=args.port)
        try:
            probe.login()
            action = _build_probe_action(args.action, args)
            probe.send(action)
            probe.try_read()
            print(
                json.dumps(
                    {
                        "connected": True,
                        "logged_in": probe.logged_in,
                        "self_player_id": probe.self_player_id,
                        "sent_messages": probe.sent_messages,
                        "parsed_messages": [
                            {"type": message.type.value, "raw": message.raw[:200]}
                            for message in probe.parsed_messages[-10:]
                        ],
                    },
                    indent=2,
                )
            )
        finally:
            probe.close()
    elif args.command == "stay-alive":
        client = OholProtocolClient(
            host=args.host,
            port=args.port,
            credentials=ProtocolCredentials(
                email=args.email,
                account_key=args.account_key,
                client_id=args.client_id,
                server_password=args.server_password,
                tutorial=args.tutorial,
            ),
            keep_alive_interval_seconds=args.keep_alive_interval,
        )
        move_target = None
        if args.move_x is not None and args.move_y is not None:
            move_target = Tile(args.move_x, args.move_y)
        result = client.stay_alive(
            duration_seconds=args.seconds,
            say_once=args.say,
            move_to=move_target,
            watch=args.watch,
            watch_interval_seconds=args.watch_interval,
        )
        if args.watch:
            from .dashboard import _clear_screen

            _clear_screen()
        print(
            json.dumps(
                {
                    "connected_seconds": round(result.connected_seconds, 2),
                    "self_player_id": result.self_player_id,
                    "final_tile": {"x": result.final_tile.x, "y": result.final_tile.y},
                    "message_counts": result.message_counts,
                    "sent_keep_alives": result.sent_keep_alives,
                    "actions_sent": result.actions_sent,
                },
                indent=2,
            )
        )
    elif args.command == "run-live":
        client = OholProtocolClient(
            host=args.host,
            port=args.port,
            credentials=ProtocolCredentials(
                email=args.email,
                account_key=args.account_key,
                client_id=args.client_id,
                server_password=args.server_password,
                tutorial=args.tutorial,
            ),
            keep_alive_interval_seconds=args.keep_alive_interval,
            game_data_root=args.game_data_root,
        )
        result = run_live_episode(
            client,
            _build_run_live_policy(),
            args.max_ticks,
            tick_seconds=args.tick_seconds,
            frame_paced=args.frame_paced,
            watch=args.watch,
            forever=args.forever,
        )
        max_actions = max(0, args.session_log_actions)
        finish_run_live_session(
            result,
            watch=args.watch,
            log_path=args.session_log,
            max_actions=max_actions,
        )
    elif args.command == "control":
        client = _build_protocol_client(args)
        initial_commands = (" ".join(args.manual_command),) if args.manual_command else ()
        run_manual_control(
            client,
            frame_paced=args.frame_paced,
            watch=args.watch,
            initial_commands=initial_commands,
        )
    elif args.command == "play":
        client = _build_protocol_client(args)
        result = run_live_interactive_episode(
            client,
            _build_run_live_policy(),
            args.max_ticks,
            tick_seconds=args.tick_seconds,
            frame_paced=args.frame_paced,
            watch=True,
            forever=args.forever,
        )
        max_actions = max(0, args.session_log_actions)
        finish_play_session(
            result,
            watch=True,
            log_path=args.session_log,
            max_actions=max_actions,
        )
    elif args.command == "verify-live":
        client = OholProtocolClient(
            host=args.host,
            port=args.port,
            credentials=ProtocolCredentials(
                email=args.email,
                account_key=args.account_key,
                client_id=args.client_id,
                server_password=args.server_password,
                tutorial=args.tutorial,
            ),
            keep_alive_interval_seconds=args.keep_alive_interval,
            game_data_root=args.game_data_root,
        )
        try:
            report = verify_live_behaviors(
                client,
                settle_seconds=args.settle_seconds,
            )
            print(
                json.dumps(
                    {
                        "self_player_id": report.self_player_id,
                        "initial_tile": {
                            "x": report.initial_tile.x,
                            "y": report.initial_tile.y,
                        },
                        "final_tile": {"x": report.final_tile.x, "y": report.final_tile.y},
                        "say_sent": report.say_sent,
                        "move_sent": report.move_sent,
                        "eat_attempted": report.eat_attempted,
                        "hunger_ratio": report.hunger_ratio,
                        "tracked_objects": report.tracked_objects,
                        "nearby_food": report.nearby_food,
                        "checks": report.checks,
                        "actions": report.actions,
                        "all_checks_passed": all(report.checks.values()),
                    },
                    indent=2,
                )
            )
        finally:
            client.close()


def _add_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8005)
    parser.add_argument("--email", default="bot_001@local")
    parser.add_argument("--account-key", default="aaaa")
    parser.add_argument("--client-id", default="client_mariusbottest")
    parser.add_argument("--server-password", default="testPassword")
    parser.add_argument("--tutorial", action="store_true")


def _build_protocol_client(args: argparse.Namespace) -> OholProtocolClient:
    return OholProtocolClient(
        host=args.host,
        port=args.port,
        credentials=ProtocolCredentials(
            email=args.email,
            account_key=args.account_key,
            client_id=args.client_id,
            server_password=args.server_password,
            tutorial=args.tutorial,
        ),
        keep_alive_interval_seconds=getattr(args, "keep_alive_interval", 5.0),
        game_data_root=getattr(args, "game_data_root", ".ohol_runtime/server"),
    )


def _build_run_live_policy() -> MovementFollowPolicy:
    return MovementFollowPolicy()


def _build_probe_action(action_type: str, args: argparse.Namespace) -> Action:
    parsed = ActionType(action_type)
    if parsed is ActionType.SAY:
        return Action(parsed, {"text": args.text})
    if parsed in {ActionType.MOVE_TO, ActionType.PICK_UP, ActionType.DROP, ActionType.FORCE}:
        return Action(parsed, {"x": args.x, "y": args.y})
    if parsed is ActionType.USE:
        return Action(parsed, {"held_item": None, "target_x": args.x, "target_y": args.y})
    if parsed is ActionType.WAIT:
        return Action(parsed, {"ticks": args.ticks})
    raise ValueError(f"Unsupported probe action: {action_type}")


if __name__ == "__main__":
    main()
