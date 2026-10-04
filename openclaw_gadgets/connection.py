# SPDX-License-Identifier: Apache-2.0
"""Adapt one gadget text turn to the OpenClaw Gateway CLI.

This is a host-side prototype, not an ESP32 node implementation. Authentication
stays in the installed OpenClaw CLI. No Muse modules or endpoints are used.
"""

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional

MAX_PROMPT_BYTES = 16 * 1024
MAX_REPLY_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


class ConnectionError(Exception):
    """A safe display error; raw CLI diagnostics never become gadget captions."""

    def __init__(self, code: str, message: str, *, run_id: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.run_id = run_id


@dataclass(frozen=True)
class Reply:
    text: str
    run_id: Optional[str]
    session_key: str


def validate_identifier(value: str, name: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError(name + " must be 1-64 lowercase letters, digits, '_' or '-', starting with a letter or digit")
    return value


def validate_prompt(text: str) -> str:
    if not isinstance(text, str) or not text.strip() or "\0" in text:
        raise ValueError("Message must contain non-empty text without NUL characters")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ValueError("Message must be valid UTF-8 text") from exc
    if size > MAX_PROMPT_BYTES:
        raise ValueError("Message exceeds the 16 KiB UTF-8 limit")
    return text


def _run_id(response: dict) -> Optional[str]:
    value = response.get("runId")
    if isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", value):
        return value
    return None


def parse_reply(stdout: str, returncode: int, session_key: str) -> Reply:
    """Read the Gateway envelope used by OpenClaw 2026.9.7.

    Do not accept embedded `agent exec` output as a Gateway success. A terminal
    successful status and visible, non-error text payload are required.
    """
    if len(stdout.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ConnectionError("invalid_response", "OpenClaw response exceeded the adapter limit; inspect the session before retrying")
    try:
        response = json.loads(stdout)
    except (ValueError, TypeError) as exc:
        raise ConnectionError("invalid_response", "OpenClaw returned unreadable output; inspect the session before retrying") from exc
    if not isinstance(response, dict):
        raise ConnectionError("invalid_response", "OpenClaw returned an unexpected response; inspect the session before retrying")
    run_id = _run_id(response)
    if returncode != 0 or response.get("status") not in ("ok", "completed") or response.get("ok") is False:
        raise ConnectionError("gateway_failed", "OpenClaw did not confirm a completed turn; inspect the session before retrying", run_id=run_id)
    result = response.get("result")
    if not isinstance(result, dict):
        raise ConnectionError("invalid_response", "OpenClaw returned no Gateway result", run_id=run_id)
    meta = result.get("meta")
    if isinstance(meta, dict) and (meta.get("error") or meta.get("aborted") is True):
        raise ConnectionError("agent_failed", "The agent did not complete the turn", run_id=run_id)
    payloads = result.get("payloads")
    if not isinstance(payloads, list) or any(not isinstance(p, dict) for p in payloads):
        raise ConnectionError("invalid_response", "OpenClaw returned malformed reply payloads", run_id=run_id)
    if any(p.get("isError") is True for p in payloads):
        raise ConnectionError("agent_failed", "The agent reported a failed turn", run_id=run_id)
    texts = [p["text"] for p in payloads if p.get("isReasoning") is not True and isinstance(p.get("text"), str) and p["text"].strip()]
    if not texts:
        raise ConnectionError("no_text_reply", "The turn completed without a displayable text reply", run_id=run_id)
    text = "\n\n".join(texts)
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ConnectionError("invalid_response", "The reply was not valid UTF-8", run_id=run_id) from exc
    if size > MAX_REPLY_BYTES:
        raise ConnectionError("reply_too_large", "The reply exceeded the 64 KiB display limit", run_id=run_id)
    return Reply(text, run_id, session_key)


class GatewayConnection:
    def __init__(self, agent: str, device: str, *, profile: Optional[str] = None,
                 timeout: int = 120, executable: str = "openclaw"):
        self.agent = validate_identifier(agent, "Agent")
        self.device = validate_identifier(device, "Device")
        self.profile = validate_identifier(profile, "Profile") if profile is not None else None
        if type(timeout) is not int or not 1 <= timeout <= 600:
            raise ValueError("Timeout must be an integer from 1 to 600 seconds")
        self.timeout = timeout
        self.executable = executable
        # Each gadget has a stable conversation, separate from the agent's main chat.
        self.session_key = "agent:{}:gadget:{}".format(self.agent, self.device)

    def send(self, message: str) -> Reply:
        message = validate_prompt(message)
        command = [self.executable]
        if self.profile is not None:
            command += ["--profile", self.profile]
        # Top-level `agent --message-file` expects a file, not stdin. A private
        # temporary file also keeps prompts out of the process argument list.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix="clawgadget-", suffix=".txt") as prompt_file:
            prompt_file.write(message)
            prompt_file.flush()
            command += ["agent", "--agent", self.agent, "--session-key", self.session_key,
                        "--message-file", prompt_file.name, "--timeout", str(self.timeout), "--json"]
            try:
                completed = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                                           text=True, encoding="utf-8", timeout=self.timeout + 15,
                                           check=False)
            except FileNotFoundError as exc:
                raise ConnectionError("cli_missing", "Install OpenClaw and make its CLI available on PATH") from exc
            except subprocess.TimeoutExpired as exc:
                raise ConnectionError("timeout", "The adapter timed out; the Gateway may still finish the turn. Inspect the session before retrying") from exc
            except (OSError, UnicodeError) as exc:
                raise ConnectionError("cli_failed", "The OpenClaw CLI could not complete; inspect the session before retrying") from exc
        # Never include stderr or raw failed stdout in display output. Diagnostics
        # can contain local configuration, credentials or unrelated transcripts.
        return parse_reply(completed.stdout, completed.returncode, self.session_key)
