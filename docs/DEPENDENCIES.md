# Components and reuse decisions

- Companion: Python3.10+ standard library only at runtime. No install-time program, telemetry SDK or third-party font. SQLite comes through Python.
- Vexa: external service pinned to6b26f7b921756d6db128d42cd70b4b7046381407. Apache2.0 source licence verified. No upstream source copied into companion archive. The separate native ARM probe clones the pinned upstream source and preserves its licences/lockfiles. Stock release bot ARM support is not claimed.
- Speech: reuse Vexa's transcription client. Groq hosts whisper-large-v3-turbo. No local duplicate faster-whisper/WhisperX pipeline added. Whisper code/models are MIT in the source project; Groq service terms, quota and privacy still apply. Real language accuracy unverified.
- Text AI: Groq hosts openai/gpt-oss-20b, model source licence Apache2.0. Service is not self-hosted/free merely because weights are open. Current docs list20b below120b in token price, but no quality benchmark on these meetings has been run. No automatic Claude paid fallback. NVIDIA catalog's free use is for prototyping, not a grounded always-free production promise.
- Resend: selected hosted email service, not an open-source mail server. Stable idempotency keys and explicit provider IDs. Domain143.lat selected by user; live account/domain/quota check must pass before use.
- OpenWA: external existing WhatsApp gateway. Contract verified from installed0.23.3 by the existing operator, no code copied and no production credentials transferred. Keep unofficial WhatsApp ban/compliance risk and isolation in mind.
- Impeccable: used for project-local design guidance after inspection. No design skill or binary ships in the runtime package. No global/hook changes.
- SlopMonster: local read-only copy checker used after code inspection. Optional external-model rewrite script not run. Score is a pattern check, not proof of quality or human authorship.

Not combined: Attendee (Elastic2.0 hosted-service limits and duplicate capture), nojoin/OpenMinutes (AGPL choices need separate licence planning, duplicate pipeline), desktop-only Meetily, and unlicensed ScribeFlow. Prior research was the selection basis; the build reuses the smallest fitting stack rather than accumulating every repository.

No public redistribution licence has been selected for new companion code. Keep the archive private until the owner chooses its repository/licence. Do not include chat databases, keys or transcripts in version control.
