# SPDX-License-Identifier: Apache-2.0
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from openclaw_gadgets.__main__ import main
from openclaw_gadgets.connection import ConnectionError, GatewayConnection, parse_reply


def response(payloads=None, **extra):
    value = {"runId": "synthetic-run-1", "status": "ok", "result": {"payloads": payloads if payloads is not None else [{"text": "Hello gadget"}]}}
    value.update(extra)
    return json.dumps(value)


class ConnectionTests(unittest.TestCase):
    def test_real_process_receives_prompt_and_returns_gateway_envelope(self):
        # Exercise actual argv, file I/O and subprocess parsing without dispatching
        # an agent turn or inheriting any real configuration into a provider call.
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "fake-openclaw"
            executable.write_text(
                "#!/usr/bin/env python3\n"
                "import json,sys\n"
                "from pathlib import Path\n"
                "a=sys.argv[1:]\n"
                "assert a[0]=='agent' and '--local' not in a and '--deliver' not in a\n"
                "assert a[a.index('--session-key')+1]=='agent:assistant:gadget:desk'\n"
                "text=Path(a[a.index('--message-file')+1]).read_text(encoding='utf-8')\n"
                "print(json.dumps({'status':'ok','runId':'fake-process','result':{'payloads':[{'text':text}]}}))\n"
            )
            executable.chmod(0o700)
            reply = GatewayConnection("assistant", "desk", executable=str(executable)).send("A café question\nSecond line")
        self.assertEqual(reply.text, "A café question\nSecond line")
        self.assertEqual(reply.run_id, "fake-process")

    def test_gateway_command_uses_private_file_and_separate_session(self):
        observed = []

        def runner(command, **options):
            path = Path(command[command.index("--message-file") + 1])
            observed.append(path)
            self.assertEqual(path.read_text(), "A private multiline prompt\nwith unicode: café")
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertNotIn("A private", " ".join(command))
            self.assertNotIn("--local", command)
            self.assertNotIn("--deliver", command)
            self.assertEqual(command[:4], ["openclaw", "--profile", "lab", "agent"])
            self.assertEqual(command[command.index("--session-key") + 1], "agent:assistant:gadget:desk")
            self.assertEqual(options["stdin"], subprocess.DEVNULL)
            self.assertEqual(options["timeout"], 45)
            return subprocess.CompletedProcess(command, 0, response(), "unrelated private diagnostic")

        with patch("openclaw_gadgets.connection.subprocess.run", side_effect=runner):
            reply = GatewayConnection("assistant", "desk", profile="lab", timeout=30).send("A private multiline prompt\nwith unicode: café")
        self.assertEqual(reply.text, "Hello gadget")
        self.assertFalse(observed[0].exists())

    def test_timeout_is_not_retried_and_removes_prompt_file(self):
        paths = []

        def runner(command, **options):
            paths.append(Path(command[command.index("--message-file") + 1]))
            raise subprocess.TimeoutExpired(command, options["timeout"])

        with patch("openclaw_gadgets.connection.subprocess.run", side_effect=runner) as run:
            with self.assertRaises(ConnectionError) as raised:
                GatewayConnection("assistant", "desk").send("hello")
        self.assertEqual(raised.exception.code, "timeout")
        self.assertEqual(run.call_count, 1)
        self.assertFalse(paths[0].exists())

    def test_devices_do_not_share_main_or_each_others_conversation(self):
        a = GatewayConnection("assistant", "desk")
        b = GatewayConnection("assistant", "kitchen")
        self.assertNotEqual(a.session_key, b.session_key)
        self.assertNotEqual(a.session_key, "agent:assistant:main")
        self.assertEqual(a.session_key, GatewayConnection("assistant", "desk").session_key)

    def test_invalid_routing_and_prompt_fail_before_dispatch(self):
        with patch("openclaw_gadgets.connection.subprocess.run") as run:
            for agent, device in [("", "desk"), ("other:main", "desk"), ("assistant", "../desk"), ("assistant", "--local")]:
                with self.subTest(agent=agent, device=device), self.assertRaises(ValueError):
                    GatewayConnection(agent, device)
            for text in [" ", "a\0b", "é" * 8193, "\ud800"]:
                with self.subTest(size=len(text)), self.assertRaises(ValueError):
                    GatewayConnection("assistant", "desk").send(text)
            run.assert_not_called()

    def test_only_visible_text_is_projected(self):
        reply = parse_reply(response([{"text": "hidden", "isReasoning": True}, {"text": "First"}, {"mediaUrl": "https://example.invalid/image"}, {"text": "Second"}]), 0, "session")
        self.assertEqual(reply.text, "First\n\nSecond")

    def test_incomplete_failed_and_malformed_turns_cannot_look_successful(self):
        cases = [
            (response(status="in_flight"), 0), (response(status="timeout"), 0),
            (response(ok=False), 0), (response(), 1), ("[]", 0), ("not json", 0),
            (response(result=None), 0), (response(result={"payloads": ["bad"]}), 0),
            (response([{"text": "Secret diagnostic", "isError": True}]), 0),
            (response(result={"payloads": [{"text": "Partial"}], "meta": {"error": {"message": "secret"}}}), 0),
            (response(result={"payloads": [{"text": "Partial"}], "meta": {"aborted": True}}), 0),
            (response([{"mediaUrl": "https://example.invalid/image"}]), 0),
            (response([{"text": "x" * 65537}]), 0), (response([{"text": "\ud800"}]), 0),
        ]
        for stdout, exitcode in cases:
            with self.subTest(stdout=stdout[:60], exitcode=exitcode), self.assertRaises(ConnectionError):
                parse_reply(stdout, exitcode, "session")

    def test_missing_cli_is_a_displayable_error(self):
        with patch("openclaw_gadgets.connection.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaises(ConnectionError) as raised:
                GatewayConnection("assistant", "desk").send("hello")
        self.assertEqual(raised.exception.code, "cli_missing")

    def test_cli_success_events(self):
        out = io.StringIO()
        with patch("openclaw_gadgets.connection.subprocess.run", return_value=subprocess.CompletedProcess([], 0, response(), "private")), redirect_stdout(out):
            code = main(["--agent", "assistant", "--device", "desk", "--message", "hello"])
        events = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual(code, 0)
        self.assertEqual([e["type"] for e in events], ["state", "reply", "state"])
        self.assertEqual(events[0]["state"], "thinking")
        self.assertEqual(events[-1]["state"], "idle")

    def test_cli_failure_never_exposes_raw_output_or_retries(self):
        out = io.StringIO()
        with patch("openclaw_gadgets.connection.subprocess.run", return_value=subprocess.CompletedProcess([], 1, response(status="error", summary="SYNTHETIC_SECRET"), "SYNTHETIC_SECRET")) as run, redirect_stdout(out):
            code = main(["--agent", "assistant", "--device", "desk", "--message", "hello"])
        events = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual(code, 1)
        self.assertEqual(events[-1]["type"], "error")
        self.assertFalse(events[-1]["retrySafe"])
        self.assertEqual(events[-1]["runId"], "synthetic-run-1")
        self.assertNotIn("SYNTHETIC_SECRET", out.getvalue())
        self.assertEqual(run.call_count, 1)

    def test_stdin_input(self):
        out = io.StringIO()
        with patch("sys.stdin", io.StringIO("hello from stdin")), patch("openclaw_gadgets.connection.subprocess.run", return_value=subprocess.CompletedProcess([], 0, response(), "")), redirect_stdout(out):
            self.assertEqual(main(["--agent", "assistant", "--device", "desk"]), 0)


if __name__ == "__main__":
    unittest.main()
