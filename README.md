# OSINT Watcher

A daily OSINT round-up agent powered by [Hermes Agent](https://github.com/NousResearch/hermes-agent) — scans 26 RSS/HTML feeds across three buckets, triages headlines against tracked themes, and delivers a styled email newsletter with WhatsApp notification.

## Buckets

| Bucket | Focus |
|---|---|
| **A. Tech × Geopolitics** | Export controls, chips/semis, sovereign AI, cyber, platform regulation, US–China–EU tech policy |
| **B. Finance** | Fed/rates, macro, markets, tech equities, AI capex, semis, hyperscalers, VC |
| **C. Middle East AI** | Data-center/infra buildout, Gulf sovereign funds, US–Gulf chip deals, Saudi/UAE/Qatar AI strategy, Israel |

## How It Works

```
26 feeds → blogwatcher-cli scan → triage → roundup.json → render_roundup.py → Gmail + WhatsApp
```

1. **Cron** triggers at 07:00 ET daily, spawning a fresh Hermes Agent session
2. Agent scans all feeds via `blogwatcher-cli`, checks Gmail for newsletters
3. Loads tracked themes and seen URLs for dedup
4. Writes `roundup.json` with selected items (max 16: A≤8, B≤5, C≤5)
5. Validates with `render_roundup.py --dry-run`
6. Sends with `render_roundup.py --send` — writes archive, updates state, emails to recipient

## Repo Structure

```
render_roundup.py       # The renderer: validates, writes archive, updates themes/seen, sends email
roundup.example.json   # Reference shape for today's content
skill/
  SKILL.md             # Agent instructions (Hermes Agent skill v1.1.0)
themes.template.json   # Empty themes.json starter
seen.template.json     # Empty seen.json starter
```

## State Files (runtime, not in repo)

```
~/.hermes/osint/
  themes.json           # Tracked storylines with history
  seen.json             # Processed URLs (dedup)
  archive/YYYY-MM-DD.md # Past round-ups
  roundup.json          # Today's content (rewritten each run)
```

## Feeds (26 sources)

- **Techmeme**, **Hacker News**, **Financial Times** (5 section feeds)
- **The Economist** (4), **Reuters** (2, scraped)
- **Import AI**, **Interconnects**, **Epoch AI**, **SemiAnalysis** (Substack)
- **AGBI**, **Al-Monitor**, **Middle East Monitor**, **Gulf News**, **Wamda**, **Zawya** (Middle East)
- **Federal Reserve** press releases + monetary policy

## Technologies

- **Framework**: Hermes Agent (Nous Research)
- **Model**: OpenAI GPT-6 Luna (main), Google Gemini 2.5 Flash (auxiliary)
- **Tools**: blogwatcher-cli, Gmail API, web_extract, Chromium browser (real profile for paywalls), WhatsApp Baileys bridge
- **Deployment**: macOS, launchd gateway service, Hermes cron scheduler

## License

MIT