# OpenClaw Gadgets development

This public fork is developing physical interfaces for a user-owned OpenClaw
gateway. The inherited `esp32/` and `linux/` trees still contain upstream Muse
software; they are not an OpenClaw port yet.

- Use Sol / medium for ordinary work. Do not switch to Astra without the owner's
  approval. Do not claim an instruction changed the active model.
- Preserve upstream copyright notices, LICENSE, dependency licenses, and the
  Jollybot artwork exclusion. Use original artwork for new gadget interfaces.
- New OpenClaw code must not require Muse accounts, SDK tokens, or Meta services.
  Inherited requirements for Muse branding and tokens apply only to the legacy
  Muse path, not the new OpenClaw path.
- Keep configuration and credentials outside Git. Never commit real prompts,
  transcripts, device tokens, Wi-Fi credentials, or local OpenClaw configuration.
- Keep agent selection explicit. Do not silently fall back to embedded execution,
  automatically retry ambiguous turns, or enable external-channel delivery.
- Do not change an existing gateway's configuration, restart services, or flash
  hardware as part of software verification. Those are separate deployment steps.
- Follow nested AGENTS.md when changing inherited code. For `openclaw_gadgets/`,
  run `python3 -m unittest discover -s tests/openclaw_gadgets -v` from the root.
- Report host tests, live gateway tests, and physical device tests separately.
