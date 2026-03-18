# Costa OS Terms of Use

**Last updated:** March 2026

These terms are straightforward because Costa OS is simple: it's free, open-source software that you can do whatever you want with.

---

## License

Costa OS is released under the **Apache License 2.0**. This means you can:

- Use it for anything — personal, commercial, educational, whatever
- Modify it however you want
- Redistribute it, with or without changes
- Include it in proprietary projects
- Sell products built on it

The main requirements are that you include the copyright notice, license text, and state any changes when you redistribute the source code. The Apache License 2.0 also provides an express grant of patent rights from contributors. See the full [LICENSE](../LICENSE) file for the exact legal text.

---

## No Warranty

Costa OS is provided **"as is"**, without warranty of any kind. This includes but is not limited to:

- No guarantee that it will work on your hardware
- No guarantee that it will be free of bugs
- No guarantee of fitness for any particular purpose
- No guarantee of uninterrupted availability

You use it at your own risk. The contributors are not liable for any damages arising from its use.

---

## AI Features

Costa OS includes AI-powered features (voice assistant, smart commands, code generation, system management). Important things to understand:

- **AI can be wrong.** Language models produce incorrect, incomplete, or misleading output. Always verify AI-generated commands before running them, especially anything involving `sudo`, file deletion, or system configuration.
- **You are responsible for what you execute.** If the AI suggests a command and you run it, the outcome is your responsibility.
- **Local models have limitations.** Smaller local models (3B-14B parameters) are less capable than cloud models. They may misunderstand complex queries or produce lower-quality responses.

---

## Third-Party Services

Costa OS integrates with third-party services that have their own terms and policies. Costa OS is not responsible for:

- **Anthropic (Claude API)** — If you configure a Claude API key, your usage is governed by [Anthropic's terms](https://www.anthropic.com/terms). You are responsible for your own API costs.
- **OpenAI** — If you configure an OpenAI API key, your usage is governed by [OpenAI's terms](https://openai.com/terms/). You are responsible for your own API costs.
- **Ollama** — Local model downloads come from ollama.com, governed by Ollama's terms and the individual model licenses (e.g., Qwen models are Apache 2.0).
- **Arch Linux** — System packages come from Arch Linux repositories, governed by their respective open-source licenses.
- **wttr.in** — Weather data is fetched from this free service. No API key required.

Your API keys are your responsibility. Costa OS stores them locally and sends them only to the provider you configured. Guard them like passwords.

---

## Contributions

If you contribute to Costa OS (pull requests, issues, documentation), your contributions are licensed under the same Apache License 2.0 as the rest of the project.

---

## Changes

These terms may be updated over time. Changes are tracked in the Git history of this file. Since Costa OS has no accounts or email list, it's worth checking this document occasionally if you care about the terms — though given how permissive they are, changes are unlikely to affect you.
