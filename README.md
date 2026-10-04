# OpenClaw Gadgets

A public development fork of [Meta's Muse Gadgets SDK](https://github.com/facebookincubator/muse-gadget-sdk),
working toward physical interfaces for a user-owned OpenClaw assistant.

The first addition is a **host-side text adapter**. It sends a question to an
explicitly selected OpenClaw agent through the installed Gateway CLI, then emits
JSON Lines for a gadget's screen or controller. It uses no Muse accounts, SDK
tokens, cloud endpoints, or imported Muse modules.

**The inherited ESP32 and Linux Muse software has not been ported.** Running
those original builds still connects to Muse. There is no OpenClaw firmware
image to flash from this fork yet. See [the original Muse README](README.muse.md)
for the inherited software and [the port plan](docs/OPENCLAW_PORT.md) for the new work.

## Try the host adapter

Requirements: Python 3.9+ and an installed, configured OpenClaw CLI with a running
Gateway. The command and response contract was inspected against OpenClaw
2026.9.7. Older CLI versions may lack `--message-file` or use a different envelope.
No Python packages need to be installed for this adapter.

From the repository root, replace `assistant` with an existing agent id:

```sh
python3 -m openclaw_gadgets --agent assistant --device desk < question.txt
```

`question.txt` is your own UTF-8 text file, kept outside the repository. You can
also use `--message 'Hello'` for non-sensitive text. Optional `--profile lab`
selects a configured OpenClaw profile; `--timeout 120` controls the agent timeout.
Agent, device and profile ids use lowercase letters, digits, underscores or
hyphens and are limited to 64 characters.

Running the adapter performs a real agent turn: it uses that agent's configured
model, credentials, tools and permissions. Cloud providers may charge for it.
It does not change Gateway configuration or deliver replies to messaging channels.

Example output (synthetic):

```json
{"type":"state","state":"thinking","device":"desk"}
{"type":"reply","text":"Hello!","runId":"example-run","sessionKey":"agent:assistant:gadget:desk"}
{"type":"state","state":"idle","device":"desk"}
```

The stable device id selects a separate conversation for that gadget, rather
than the agent's main chat. Reusing it resumes that conversation. This does not
isolate the agent's other capabilities or memory. Changing it selects another
conversation.

Prompts are passed to OpenClaw using a temporary file with owner-only permissions,
removed when the call exits. Raw CLI diagnostics and model metadata are not
projected onto the display. The configured OpenClaw agent still retains its own
session history according to its settings.

On failure the adapter emits an error and exits 1. It never retries a turn or
silently falls back to embedded execution: after a timeout, the Gateway may
still finish the request. Inspect the session before sending it again.

## Test without a model or device

```sh
python3 -m unittest discover -s tests/openclaw_gadgets -v
```

Tests use synthetic Gateway replies and a fake CLI. They do not contact Meta,
OpenClaw, model providers or physical hardware. They cover routing, process
execution, prompt-file cleanup, visible-text projection and failure handling.

## Next steps

1. Validate a real text round trip with a deliberately selected test agent.
2. Choose and identify the first physical board and its exact revision.
3. Implement its connection and text display, then test on hardware.
4. Add audio only on hardware with a suitable microphone/speaker path.

For native voice devices, evaluate the existing
[OpenClaw ESP room component](https://github.com/openclaw/esp-openclaw-node)
instead of rebuilding its pairing, Talk and wake behavior. E-paper and LoRa
devices need their own display/transport decisions.

## Upstream and licensing

Starting upstream revision: `693cde9a884ad1edc87251b9f8944815f8de4809`
(October 4, 2026 checkout). Local development keeps `upstream` for Meta's
repository and `origin` for this fork.

The inherited SDK and new adapter use [Apache-2.0](LICENSE), subject to the
upstream dependency exceptions documented in [README.muse.md](README.muse.md#license).
Existing copyright notices remain intact. **The upstream Jollybot avatar is
excluded from Apache-2.0.** Its inherited files are not relicensed by this fork;
new OpenClaw gadget interfaces should use original artwork.

This is an independent experiment, not an official Meta or OpenClaw product.
