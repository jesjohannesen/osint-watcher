---
name: osint-watcher
description: "Use when the user asks for the daily OSINT round-up, or for ad-hoc research via WhatsApp. Daily newsletter covering Tech × Geopolitics, Finance, and Middle East AI."
version: 1.1.0
author: Hermes Agent
created_by: agent
metadata:
  hermes:
    tags: [osint, newsletter, research, daily-roundup]
---

# OSINT Watcher

Daily round-up analyst for Jesper. Concise, source-linked, no filler. Three buckets:
A. Tech × geopolitics, B. Finance, C. Middle East AI.

Workspace `~/.hermes/osint/`:
- `themes.json`: tracked storylines
- `seen.json`: published URLs (normalised)
- `archive/YYYY-MM-DD.md`: past round-ups
- `roundup.json`: today's content. You write this file; shape in `roundup.example.json`
- `render_roundup.py`: turns roundup.json into the archive, the HTML email, the state updates and the send
- `HANDOFF.md`: pipeline change notes from 2026-10-07. Read it once if this is your first run since then.

You never hand-write HTML, markdown or state-update scripts. One JSON in, everything out.

## Round-up Method

### 1. Gather
Run `blogwatcher-cli scan` then `blogwatcher-cli articles` for unread items.
Search Gmail: `python ~/.hermes/skills/productivity/google-workspace/scripts/google_api.py gmail search "from:substack.com newer_than:1d" --max 20`

### 2. Triage
Load `themes.json`. Check candidates before reading anything:
`python3 ~/.hermes/osint/render_roundup.py --check-seen URL [URL ...]`
(normalises Techmeme anchors, utm tags, http/https, www). Drop everything marked SEEN.

Bucket tests. An item must pass its bucket's test or it is skipped:
- **A Tech × Geopolitics**: a tech, AI, compute, semiconductor, data or cyber angle AND a state actor, regulator or cross-border angle. Pure diplomacy or battlefield news with no tech, chip or capital angle does not belong in A.
- **B Finance**: capital moving at scale (rounds and deals from roughly $100M, IPOs, M&A, sovereign or central-bank moves, market-structure rulings) or regulation of markets that touches tech. Seed rounds are not news unless they extend a tracked MENA theme.
- **C Middle East AI**: MENA AI, data centres, sovereign capital into tech, regional tech regulation and talent. Regional security only where it moves a tracked theme (Hormuz, Yemen, Mecca pact), and at most two such items per issue.

Relevance rules:
- Developments over commentary. A profile, op-ed, podcast or interview qualifies only if it establishes a new fact or a new official position.
- Caps: A ≤ 8, B ≤ 5, C ≤ 5, 16 items total. When over, cut the items with the weakest "why it matters", not the shortest ones.
- UPDATE only when the item advances the same storyline as an existing theme id. Same region, same company or same week is not the same storyline. An Iran story is never an update to `us-ai-governance`.
- A theme is a storyline, not a story. Add `new_theme` only when you expect a follow-up within two weeks. One-off funding rounds, launches and verdicts get `"theme": null`.
- Sources: link the original outlet (FT, Reuters, Bloomberg, The Information, an official statement) when you have its URL; otherwise the aggregator. Name the outlet in `source.name` ("FT via Techmeme" is fine). One story, one item: dedupe across outlets.
- Top 3 by material impact on the three buckets, not by drama. `flag: true` only for something that needs attention today.

### 3. Fetch full text ONLY for selected items
For FT/Economist/Substack: use browser with real profile (already configured). Otherwise: `web_extract`. Never open more than 25 pages per run.

### 4. Write roundup.json
Per item: `id`, `bucket`, `status`, `theme`, `headline` (≤ 12 words, the development), `summary` (2–3 sentences, facts and numbers only), `why` (one sentence, the so-what), `source` {`name`, `url`}. Optional: `top` (1–3, exactly three items), `dek` (one line for the Top 3 slot; defaults to the first sentence of the summary), `flag`, `state_note` (one line for themes.json; defaults to the headline), `new_theme` {`id`, `title`}.
Write it with `write_file`, then validate:
`python3 ~/.hermes/osint/render_roundup.py --dry-run --out /tmp/osint-check`
Fix every ERROR line; read the WARN lines and fix the ones that are real.

### 5. Render, record, send
`python3 ~/.hermes/osint/render_roundup.py --send`
This writes `archive/{date}.md` and `roundup_email.html`, appends dated history to touched themes, creates `new_theme`s, marks themes quiet > 21 days as stale, adds the URLs to `seen.json`, and sends the email to jesjohannesen@gmail.com with subject `OSINT round-up — {Month D, YYYY}`.
If the send fails, the state and files are already saved: report the blocker, never fabricate a send. Re-send later with `--send --force`.

### 6. Final reply
"Round-up {date} landed: N new, M updated" plus two most important headlines.
Deliver to WhatsApp (home channel).

### Cost rules
- Never re-read a URL marked SEEN
- Summarise headlines before opening pages
- Use cheapest auxiliary model for summarisation/compression

## Unattended (cron) Mode Pitfalls
- `execute_code` is BLOCKED in cron sessions (no user present to approve) — use normal tools instead.
- Heredoc stdin execution (`python3 << 'EOF'`) is BLOCKED as a dangerous command. Write `roundup.json` with `write_file`; do not write ad-hoc Python.
- If the renderer says the archive for today already exists, an earlier run got that far. Check whether it sent (look for "sent to" in that run's output); only then use `--force`.
- If auth breaks mid-run (`RefreshError: invalid_grant`), the renderer has already saved the archive and `roundup_email.html`. Report the blocker. Never fabricate a send.
- Do not rely on shell `$VAR` holding `~` — the tilde is not re-expanded after variable substitution. Use absolute paths.

## Ad-hoc Mode
When a WhatsApp message arrives from Jesper (not a cron trigger):
1. Read themes.json and the latest archive
2. If answer is there, respond immediately
3. Otherwise research (same source priority, max 10 pages), reply concisely with links
4. Add anything durable to themes.json
