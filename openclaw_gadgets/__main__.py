# SPDX-License-Identifier: Apache-2.0
"""One text turn, projected as JSON Lines for a future gadget display."""

import argparse
import json
import sys

from .connection import ConnectionError, GatewayConnection, MAX_PROMPT_BYTES, validate_prompt


def emit(event: dict) -> None:
    print(json.dumps(event, ensure_ascii=True), flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Send one gadget text turn through your OpenClaw Gateway")
    parser.add_argument("--agent", required=True, help="Existing OpenClaw agent id")
    parser.add_argument("--device", required=True, help="Stable gadget id; selects a separate gadget conversation")
    parser.add_argument("--profile", help="Optional OpenClaw CLI profile")
    parser.add_argument("--timeout", type=int, default=120, help="Agent timeout in seconds (1-600)")
    parser.add_argument("--message", help="Message text; omit to read UTF-8 from stdin")
    args = parser.parse_args(argv)
    try:
        connection = GatewayConnection(args.agent, args.device, profile=args.profile, timeout=args.timeout)
        # Reading is bounded even when the input stream is supplied by another process.
        message = args.message if args.message is not None else sys.stdin.read(MAX_PROMPT_BYTES + 1)
        validate_prompt(message)
    except (ValueError, UnicodeError) as exc:
        parser.error(str(exc))
    emit({"type": "state", "state": "thinking", "device": args.device})
    try:
        reply = connection.send(message)
    except ConnectionError as exc:
        event = {"type": "error", "state": "error", "code": exc.code, "message": str(exc), "retrySafe": False}
        if exc.run_id is not None:
            event["runId"] = exc.run_id
        emit(event)
        return 1
    emit({"type": "reply", "text": reply.text, "runId": reply.run_id, "sessionKey": reply.session_key})
    emit({"type": "state", "state": "idle", "device": args.device})
    return 0


if __name__ == "__main__":
    sys.exit(main())
