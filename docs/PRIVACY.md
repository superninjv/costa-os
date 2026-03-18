# Costa OS Privacy Policy

**Last updated:** March 2026

Costa OS does not collect your data. Period. This document explains exactly what happens with your information so you can verify it yourself — the entire codebase is open source.

---

## The Short Version

- We collect **nothing**. No analytics, no telemetry, no crash reports, no usage data.
- There are **no accounts**. No registration, no sign-up, no login.
- There are **no Costa OS servers**. The OS never phones home to us or anyone else.
- You own **100% of your data**, and it never leaves your machine unless you explicitly tell it to.

---

## Data Storage

All data Costa OS generates stays on your local machine:

| Data | Location | Details |
|------|----------|---------|
| AI conversation history | `~/.config/costa/costa-ai.db` | SQLite database, local only |
| API keys | `~/.config/costa/env` | Stored with `chmod 600` (owner-read only) |
| Voice recordings | Temporary files in `/tmp/` | Processed locally by Whisper, deleted immediately after transcription |
| Face authentication | Local howdy data | Stored on-device, never transmitted anywhere |
| Configuration | `~/.config/costa/` and `~/.config/hypr/` | Standard config files on your filesystem |

You can delete any of this data at any time. It's your machine.

---

## AI Processing

### Local AI (Default)

By default, all AI queries are processed locally using Ollama. Your questions, commands, and conversations never leave your computer. The local models (qwen2.5 family) run entirely on your GPU.

### Cloud AI (Only If You Configure It)

If you choose to add API keys for cloud services (Claude by Anthropic or OpenAI), Costa OS will send queries directly to those providers when the local model can't handle the request. Here's what matters:

- **Costa OS never proxies your queries.** Cloud requests go straight from your machine to the provider (api.anthropic.com or api.openai.com). There is no Costa OS server in the middle.
- **Costa OS never logs cloud queries.** We have no server to log them on.
- **You control when cloud is used.** You can disable cloud escalation entirely, or configure exactly which query types get escalated.
- **Your API keys are yours.** They're stored locally in `~/.config/costa/env` with restrictive permissions. Costa OS never reads, transmits, or shares them with anyone other than the provider you configured.

Cloud providers have their own privacy policies. Review them if you use their services:
- [Anthropic (Claude)](https://www.anthropic.com/privacy)
- [OpenAI](https://openai.com/privacy/)

---

## Network Connections

Costa OS makes network calls only for the following purposes, all initiated by the user or standard system operations:

| Connection | Destination | Purpose | When |
|------------|-------------|---------|------|
| Package updates | Arch Linux repos | System and software updates | When you run `pacman -Syu` or yay |
| Weather data | `wttr.in` | Weather queries via voice/text | When you ask about the weather |
| Model downloads | `ollama.com` | Downloading AI models | When you pull a new Ollama model |
| Cloud AI (optional) | `api.anthropic.com` / `api.openai.com` | AI queries that exceed local capability | Only if you configure API keys |
| AUR packages | `aur.archlinux.org` | Community package builds | When you install AUR packages |

That's it. There is no background telemetry, no analytics beacon, no heartbeat ping, no update check phoning home to Costa OS servers. There are no Costa OS servers.

---

## No Connection to Any Company

Costa OS is a community open-source project. It is not operated by, affiliated with, or connected to Synoros, Conduit Software, or any other company. There are no company servers, no corporate data collection, and no business interests in your usage data.

---

## Voice Assistant Privacy

The voice assistant is designed with privacy as a core principle:

1. **Recording**: Audio is captured from your microphone only while you hold the push-to-talk key.
2. **Processing**: The recording is processed locally by DeepFilterNet (noise reduction) and Whisper (speech-to-text) on your own hardware.
3. **Deletion**: The audio file is deleted immediately after transcription. It is never uploaded anywhere.
4. **Transcription**: The text goes to your local Ollama model. If cloud escalation is configured and triggered, only the text (never the audio) is sent to the cloud provider.

No voice data is ever stored permanently, uploaded, or used for training.

---

## Face Authentication

If you enable face authentication (howdy), the facial recognition data is:
- Stored entirely on your local machine
- Never transmitted over any network
- Never shared with any service or server
- Deletable at any time by removing the howdy configuration

---

## Your Rights

You have complete control:

- **Access**: All your data is in plaintext files and a SQLite database on your filesystem. Read it anytime.
- **Delete**: Remove any or all of it whenever you want. `rm -rf ~/.config/costa/` wipes everything.
- **Verify**: The Costa OS intelligence layer is open source under the Apache License 2.0. Audit the code that runs on your system on [GitHub](https://github.com/superninjv/costa-os).
- **Modify**: Fork it, change it, make it yours. That's the point.

---

## Changes to This Policy

If this policy ever changes, it will be reflected in the Git history of this file. Since Costa OS collects no data, there's not much to change — but transparency matters, and Git provides a permanent, auditable record.
