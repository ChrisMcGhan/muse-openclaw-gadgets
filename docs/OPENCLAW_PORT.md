# Port plan and current boundary

## What “connection” means

A gadget needs to send a user's question, receive the assistant's answer, and
show progress or an error. The screen, buttons, microphone and radio are
board-specific. The assistant conversation can use a common interface.

Today the prototype runs on a computer:

```text
Text input → host adapter → installed OpenClaw CLI → OpenClaw Gateway → agent
                ↓
          screen-friendly JSON Lines
```

This is an integration probe, not firmware and not a native OpenClaw node.
It does not yet read a physical gadget, expose a network endpoint, stream
tokens, handle audio, or send pixels to a display. The agent performs the work
using its existing model and tools; the microcontroller does not run the model.

The adapter selects `agent:<agent-id>:gadget:<device-id>` explicitly. It never
uses `--local`, `agent exec`, `--deliver`, or an automatic fallback. It relies
on OpenClaw for provider credentials and Gateway authentication. New adapter
code has no Muse service dependency; the original `esp32/` and `linux/` trees do.

## Connection contract

One invocation processes one UTF-8 question (maximum 16 KiB):

- Emit `state/thinking` immediately before starting the CLI.
- Require a terminal successful Gateway status and a `result.payloads` list.
- Project visible text only, excluding reasoning and rejecting failed payloads.
- Emit `reply` (maximum 64 KiB) followed by `state/idle`, or one terminal `error`.
- Keep the run id when available so an ambiguous result can be investigated.
- Never replay on a timeout or `in_flight` response. A missing caption does not
  establish that the agent did not execute the question.

This first contract is text-only. Images, tool results, voice and native Canvas
commands will need distinct paths rather than being mistaken for text replies.
The adapter is intended for trusted local use. A future LAN/LoRa listener must
add explicit device authorization before allowing radio/network inputs to cause
agent turns; physical device identity cannot be established by a text device id.

## Hardware routes to evaluate

| Route | Reuse | Work still needed |
|---|---|---|
| OpenClaw-supported Waveshare 2.06 or Tab5 | Existing ESP room component and board adapter | Validate compatible Gateway, hardware revision, pairing, audio and screen |
| Other ESP32 display board | Muse's licensed board code and vendor libraries where compatible | Port board interfaces, reconcile SDK/dependency versions, implement connection and physical tests |
| LILYGO T5 E-Paper S3 Pro | Vendor display/touch examples; ESP32-S3 with 16 MB flash and 8 MB PSRAM | E-paper-oriented text UI, power policy, connection and exact-revision qualification |
| LILYGO T3 S3 E-paper | Vendor small-display/radio examples; ESP32-S3 with 4 MB flash and 2 MB PSRAM | Small text/status UI and tighter firmware memory budget |

Hardware sources:
[T5 vendor repository](https://github.com/Xinyuan-LilyGO/T5S3-4.7-e-paper-PRO),
[T3 vendor repository](https://github.com/Xinyuan-LilyGO/Lilygo-LoRa-Epaper-series),
[OpenClaw ESP examples](https://github.com/openclaw/esp-openclaw-node/tree/main/examples).
These are candidates, not supported targets in this fork.

For a LoRa device already running Meshtastic or MeshCore, investigate a host-side
messaging bridge before replacing its firmware. Existing mesh operation and
custom gadget firmware are separate routes; combining them requires an explicit
integration and cannot be assumed from having two radios. No device has been
flashed or its current firmware inspected for this project.

## Evidence so far

- Upstream Muse source cloned at `693cde9a884ad1edc87251b9f8944815f8de4809`.
- CLI flags and Gateway JSON projection inspected in installed OpenClaw 2026.9.7
  (`c074824`), using its CLI help, agent docs and implementation.
- Host tests exercise synthetic terminal, failed, incomplete and malformed turns,
  routing isolation, temporary-file cleanup and a fake CLI process.
- No live agent turn, model call, voice test, firmware build or physical-device
  qualification has been performed by this bootstrap change.

The next useful proof is a real text round trip with a selected test agent,
followed by one specific board. Audio and additional board ports follow that
first working device rather than expanding the hardware matrix immediately.
