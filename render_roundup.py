#!/usr/bin/env python3
"""Render the daily OSINT round-up from one JSON file.

    python3 render_roundup.py                      validate, write archive/<date>.md + roundup_email.html
    python3 render_roundup.py --send               ...and record state (themes.json, seen.json) and send the email
    python3 render_roundup.py --update-state       ...record state, do not send
    python3 render_roundup.py --dry-run --out DIR  render into DIR, touch nothing in the workspace
    python3 render_roundup.py --check-seen URL...  print which URLs were already published (normalised match)

Input: roundup.json (shape in roundup.example.json). The agent fills the JSON and never hand-writes
HTML, markdown or state-update scripts. Stdlib only. Idempotent: re-running the same day appends no
duplicate history and the archive is only overwritten with --force.
"""
import argparse
import copy
import html
import json
import re
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

OSINT = Path(__file__).resolve().parent
GOOGLE_API = Path.home() / ".hermes/skills/productivity/google-workspace/scripts/google_api.py"
TO = "jesjohannesen@gmail.com"

BUCKETS = {"A": "Tech × Geopolitics", "B": "Finance", "C": "Middle East AI"}
CAPS = {"A": 8, "B": 5, "C": 5}
STALE_DAYS = 21
TRACK_WINDOW_DAYS = 7
TRACK_MAX_ROWS = 14
WORD_BUDGET = 1300

# Palette: monochrome, one semantic red. Email-safe inline styles only.
INK, BG, MUTED, LINE, SOFT, RED = "#0a0a0a", "#ffffff", "#7a7a7a", "#e6e6e6", "#f6f6f6", "#d12b2b"
F_LABEL = "'Unbounded',Helvetica,Arial,sans-serif"
F_BODY = "'Newsreader',Georgia,'Times New Roman',serif"
LABEL = (f"font-family:{F_LABEL};font-size:10px;letter-spacing:.14em;text-transform:uppercase;"
         f"color:{MUTED};font-weight:400;line-height:1.6")


# ---------- helpers ----------

def load_json(path, default=None):
    if not path.exists():
        return default
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def norm_url(u):
    """Canonical form for dedupe: https, no www, no fragment, no utm, no trailing slash."""
    p = urlsplit(u.strip())
    netloc = p.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = p.path.rstrip("/")
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
    return urlunsplit(("https", netloc, path, urlencode(q), ""))


def long_date(iso):
    d = date.fromisoformat(iso)
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def short_date(iso):
    d = date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}"


def first_sentence(text):
    m = re.match(r"(.+?[.!?])(\s|$)", text.strip())
    return m.group(1) if m else text.strip()


def words(text):
    return len(re.findall(r"\S+", text or ""))


def clip(text, n=80):
    text = (text or "").strip()
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…"


def inline_html(md):
    """Escape, then allow **bold** and [text](url) only."""
    s = html.escape(md or "", quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
               rf'<a href="\2" style="color:{INK}">\1</a>', s)
    return s


def strip_md(md):
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", md or "")
    s = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", r"\1", s)
    return s


# ---------- validation ----------

def validate(data, themes, seen_norm, force):
    errors, warns = [], []
    try:
        date.fromisoformat(data.get("date", ""))
    except ValueError:
        errors.append("date must be ISO YYYY-MM-DD")
    items = data.get("items") or []
    if not items:
        errors.append("items is empty")
    ids = {t["id"] for t in themes}
    tops = sorted(i.get("top") for i in items if i.get("top"))
    if tops != [1, 2, 3]:
        errors.append(f"exactly three items need top: 1, 2, 3 (got {tops})")
    counts = {b: 0 for b in BUCKETS}
    seen_in_issue = set()
    for n, it in enumerate(items, 1):
        tag = f"item {n} ({it.get('id') or it.get('headline', '?')[:40]})"
        b = it.get("bucket")
        if b not in BUCKETS:
            errors.append(f"{tag}: bucket must be one of {list(BUCKETS)}")
        else:
            counts[b] += 1
        if it.get("status") not in ("NEW", "UPDATE"):
            errors.append(f"{tag}: status must be NEW or UPDATE")
        for k in ("headline", "summary", "why"):
            if not (it.get(k) or "").strip():
                errors.append(f"{tag}: missing {k}")
        src = it.get("source") or {}
        url = (src.get("url") or "").strip()
        if not src.get("name") or not url.startswith("http"):
            errors.append(f"{tag}: source needs name and http(s) url")
        elif " " in url:
            errors.append(f"{tag}: url contains a space: {url}")
        else:
            nu = norm_url(url)
            if nu in seen_in_issue:
                errors.append(f"{tag}: same url used twice in this issue")
            seen_in_issue.add(nu)
            if nu in seen_norm and not force:
                warns.append(f"{tag}: url already published in an earlier issue")
        theme = it.get("theme")
        nt = it.get("new_theme")
        if it.get("status") == "UPDATE":
            if not theme:
                errors.append(f"{tag}: UPDATE needs a theme id")
            elif theme not in ids:
                errors.append(f"{tag}: theme '{theme}' not in themes.json (use NEW + new_theme, or fix the id)")
        else:
            if theme and theme not in ids:
                errors.append(f"{tag}: theme '{theme}' not in themes.json")
            if theme and theme in ids:
                warns.append(f"{tag}: NEW but attached to existing theme '{theme}'; should it be UPDATE?")
        if nt:
            if not nt.get("id") or not nt.get("title"):
                errors.append(f"{tag}: new_theme needs id and title")
            elif nt["id"] in ids:
                warns.append(f"{tag}: new_theme '{nt['id']}' already exists; will append history instead")
            elif not re.fullmatch(r"[a-z0-9-]+", nt["id"]):
                errors.append(f"{tag}: new_theme id must be kebab-case")
        if words(it.get("headline")) > 14:
            warns.append(f"{tag}: headline over 14 words")
        if words(it.get("summary")) > 80:
            warns.append(f"{tag}: summary over 80 words")
        if words(it.get("why")) > 45:
            warns.append(f"{tag}: why over 45 words")
    for b, c in counts.items():
        if c > CAPS[b]:
            warns.append(f"bucket {b} has {c} items (cap {CAPS[b]})")
    return errors, warns


# ---------- state ----------

def apply_state(data, themes, seen):
    """Return (merged themes, merged seen list, stats). Pure: does not write."""
    today = data["date"]
    themes = copy.deepcopy(themes)
    ids = {t["id"]: t for t in themes}
    stats = {"new": 0, "updated": 0, "touched": [], "created": []}
    for it in data["items"]:
        url = it["source"]["url"].strip()
        note = (it.get("state_note") or strip_md(it["headline"])).strip()
        tid = None
        nt = it.get("new_theme")
        if nt:
            if nt["id"] in ids:
                tid = nt["id"]
            else:
                t = {"id": nt["id"], "title": nt["title"], "bucket": it["bucket"],
                     "first_seen": today, "last_update": today, "status": "active", "history": []}
                themes.append(t)
                ids[t["id"]] = t
                tid = t["id"]
                stats["created"].append(tid)
        elif it.get("theme") in ids:
            tid = it["theme"]
        if tid:
            t = ids[tid]
            if not any(h.get("date") == today and norm_url(h.get("url", "")) == norm_url(url)
                       for h in t["history"]):
                t["history"].append({"date": today, "note": note, "url": url})
            t["last_update"] = max(t.get("last_update", ""), today)
            t["status"] = "active"
            if tid not in stats["touched"]:
                stats["touched"].append(tid)
        stats["new" if it["status"] == "NEW" else "updated"] += 1
    cutoff = (date.fromisoformat(today) - timedelta(days=STALE_DAYS)).isoformat()
    for t in themes:
        if t.get("status") == "active" and t.get("last_update", "") < cutoff:
            t["status"] = "stale"
    merged_seen = sorted({norm_url(u) for u in seen} | {norm_url(it["source"]["url"]) for it in data["items"]})
    return themes, merged_seen, stats


def tracking_rows(themes, today, touched):
    recent = (date.fromisoformat(today) - timedelta(days=TRACK_WINDOW_DAYS)).isoformat()
    rows = [t for t in themes if t["id"] in touched or (t["status"] == "active" and t["last_update"] >= recent)]
    rows.sort(key=lambda t: (t["id"] not in touched, t["last_update"] != today, t["last_update"][::-1], t["title"]))
    out = []
    for t in rows[:TRACK_MAX_ROWS]:
        last = t["history"][-1]["note"] if t.get("history") else ""
        status = "new" if t.get("first_seen") == today else t["status"]
        out.append({"title": t["title"], "bucket": t["bucket"], "status": status,
                    "last": t["last_update"], "state": clip(last)})
    return out


# ---------- markdown ----------

def render_md(data, themes_by_id, rows, stats):
    today = data["date"]
    items = data["items"]
    L = [f"# OSINT Round-up — {long_date(today)}", "", "## Top 3"]
    for it in sorted((i for i in items if i.get("top")), key=lambda i: i["top"]):
        dek = it.get("dek") or first_sentence(it["summary"])
        L.append(f"{it['top']}. **{strip_md(it['headline'])}** — {strip_md(dek)}")
    for b, name in BUCKETS.items():
        sec = [i for i in items if i["bucket"] == b]
        if not sec:
            continue
        L += ["", "---", "", f"## {b}. {name}", ""]
        for it in sec:
            tag = "[NEW]" if it["status"] == "NEW" else f"[UPDATE: {it['theme']}]"
            flag = "⚑ " if it.get("flag") else ""
            L.append(f"**{tag} {flag}{strip_md(it['headline'])}**  ")
            L.append(f"{it['summary'].strip()} Why it matters: {it['why'].strip()} "
                     f"[{it['source']['name']}]({it['source']['url'].strip()})")
            L.append("")
    L += ["---", "", "## Tracking", "", "| Theme | Bucket | Status | Last change | State |", "|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['title']} | {r['bucket']} | {r['status']} | {short_date(r['last'])} | {r['state']} |")
    srcs = sorted({i["source"]["name"] for i in items})
    L += ["", f"*{stats['new']} new · {stats['updated']} updated · compiled {long_date(today)} from {', '.join(srcs)}*", ""]
    return "\n".join(L)


# ---------- html email ----------

def pill(status):
    base = (f"display:inline-block;padding:3px 8px;border-radius:999px;font-family:{F_LABEL};font-size:9px;"
            f"letter-spacing:.12em;text-transform:uppercase;line-height:1;vertical-align:middle;")
    if status == "NEW":
        st = base + f"background:{INK};color:{BG};border:1px solid {INK};font-weight:500"
    else:
        st = base + f"background:transparent;color:{INK};border:1px solid {INK};font-weight:400"
    return f'<span style="{st}">{status}</span>'


def render_html(data, themes_by_id, rows, stats):
    today = data["date"]
    items = data["items"]
    body_p = f"font-family:{F_BODY};font-size:15px;line-height:1.55;color:{INK};margin:6px 0 0"
    H = []
    H.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>OSINT round-up — {long_date(today)}</title>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&family=Unbounded:wght@400;500&display=swap" rel="stylesheet">
<style>
  body {{ margin:0; padding:0; background:{BG}; -webkit-text-size-adjust:100%; }}
  a {{ color:{INK}; }}
  td, th {{ word-break:break-word; }}
  @media (max-width:520px) {{ .wrap {{ padding:24px 16px !important; }} .hd {{ font-size:26px !important; }} }}
</style>
</head>
<body style="margin:0;padding:0;background:{BG};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{BG};">
<tr><td align="center" class="wrap" style="padding:40px 24px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="width:100%;max-width:640px;">
""")
    # header
    H.append(f"""<tr><td style="padding-bottom:28px;border-bottom:1px solid {INK};">
  <div style="{LABEL}">OSINT round-up</div>
  <div class="hd" style="font-family:{F_BODY};font-size:32px;font-style:italic;font-weight:400;line-height:1.15;color:{INK};margin-top:6px;">{long_date(today)}</div>
  <div style="{LABEL};margin-top:10px;">{stats['new']} new &nbsp;·&nbsp; {stats['updated']} updated &nbsp;·&nbsp; {len(items)} items</div>
</td></tr>""")
    # top 3
    tops = sorted((i for i in items if i.get("top")), key=lambda i: i["top"])
    H.append(f"""<tr><td style="padding:28px 0 0;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{SOFT};border:1px solid {LINE};border-radius:10px;">
<tr><td style="padding:16px 20px 6px;{LABEL};color:{INK};font-weight:500;">Top 3</td></tr>""")
    for it in tops:
        dek = it.get("dek") or first_sentence(it["summary"])
        H.append(f"""<tr><td style="padding:6px 20px 12px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
  <td style="width:30px;vertical-align:top;padding-top:5px;{LABEL};font-size:11px;">0{it['top']}</td>
  <td style="font-family:{F_BODY};font-size:16px;line-height:1.45;color:{INK};">
    <a href="{html.escape(it['source']['url'].strip())}" style="color:{INK};text-decoration:none;font-weight:500;">{inline_html(strip_md(it['headline']))}</a>
    <span style="color:{MUTED};"> — {inline_html(strip_md(dek))}</span>
  </td>
</tr></table></td></tr>""")
    H.append("<tr><td style=\"height:6px;\"></td></tr></table></td></tr>")
    # sections
    for b, name in BUCKETS.items():
        sec = [i for i in items if i["bucket"] == b]
        if not sec:
            continue
        H.append(f"""<tr><td style="padding:40px 0 8px;{LABEL};color:{INK};font-weight:500;">{b} &nbsp;·&nbsp; {html.escape(name)}</td></tr>
<tr><td style="height:1px;background:{INK};font-size:0;line-height:0;">&nbsp;</td></tr>""")
        for k, it in enumerate(sec):
            theme_t = themes_by_id.get(it.get("theme") or (it.get("new_theme") or {}).get("id"), {}).get("title", "")
            top_border = f"border-top:1px solid {LINE};" if k else ""
            flag = f'<span style="color:{RED};">&#9679;</span>&nbsp; ' if it.get("flag") else ""
            theme_lbl = f'&nbsp;&nbsp;<span style="{LABEL}">{html.escape(theme_t)}</span>' if theme_t else ""
            H.append(f"""<tr><td style="padding:18px 0 20px;{top_border}">
  <div>{pill(it['status'])}{theme_lbl}</div>
  <div style="font-family:{F_BODY};font-size:18px;font-weight:500;line-height:1.3;color:{INK};margin-top:9px;">{flag}{inline_html(it['headline'])}</div>
  <div style="{body_p}">{inline_html(it['summary'])}</div>
  <div style="{body_p};color:#555555;"><em>Why it matters.</em> {inline_html(it['why'])}</div>
  <div style="margin-top:9px;{LABEL}"><a href="{html.escape(it['source']['url'].strip())}" style="color:{INK};text-decoration:none;border-bottom:1px solid {LINE};">{html.escape(it['source']['name'])}</a></div>
</td></tr>""")
    # tracking
    th = f"{LABEL};padding:0 12px 8px 0;text-align:left;border-bottom:1px solid {INK};white-space:nowrap"
    td = f"font-family:{F_BODY};font-size:13px;line-height:1.4;color:{INK};padding:8px 12px 8px 0;border-bottom:1px solid {LINE};vertical-align:top"
    H.append(f"""<tr><td style="padding:40px 0 8px;{LABEL};color:{INK};font-weight:500;">Tracking</td></tr>
<tr><td>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><th style="{th}">Theme</th><th style="{th}">B</th><th style="{th}">Status</th><th style="{th}">Last</th><th style="{th};padding-right:0;">State</th></tr>""")
    for r in rows:
        st = r["status"]
        st_style = f"color:{MUTED};" if st == "stale" else (f"color:{INK};font-weight:500;" if st == "new" else "")
        H.append(f"""<tr><td style="{td}">{html.escape(r['title'])}</td><td style="{td}">{r['bucket']}</td>
<td style="{td};{st_style}white-space:nowrap;">{st}</td><td style="{td};white-space:nowrap;color:{MUTED};">{short_date(r['last'])}</td>
<td style="{td};padding-right:0;color:#555555;">{html.escape(r['state'])}</td></tr>""")
    H.append("</table></td></tr>")
    # footer
    srcs = sorted({i["source"]["name"] for i in items})
    H.append(f"""<tr><td style="padding:36px 0 0;{LABEL}">Compiled {long_date(today)} from {html.escape(', '.join(srcs))}</td></tr>
</table></td></tr></table>
</body></html>
""")
    return "\n".join(H)


# ---------- send ----------

def send_email(subject, body_html):
    py = shutil.which("python") or sys.executable
    cmd = [py, str(GOOGLE_API), "gmail", "send", "--to", TO, "--subject", subject, "--body", body_html, "--html"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[-800:])
    return (r.stdout or "").strip()


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", default=str(OSINT / "roundup.json"))
    ap.add_argument("--update-state", action="store_true", help="append to themes.json / seen.json")
    ap.add_argument("--send", action="store_true", help="send the email (implies --update-state)")
    ap.add_argument("--dry-run", action="store_true", help="render only; never write state or send")
    ap.add_argument("--out", help="output directory (default: the osint workspace)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing archive for the date")
    ap.add_argument("--check-seen", nargs="+", metavar="URL", help="report which URLs were already published")
    a = ap.parse_args()

    themes = load_json(OSINT / "themes.json", [])
    seen = load_json(OSINT / "seen.json", [])
    seen_norm = {norm_url(u) for u in seen}

    if a.check_seen:
        for u in a.check_seen:
            print(("SEEN  " if norm_url(u) in seen_norm else "new   ") + u)
        return 0

    data = load_json(Path(a.json))
    if data is None:
        print(f"ERROR: {a.json} not found", file=sys.stderr)
        return 1
    data["items"] = [i for i in data.get("items", []) if not str(i.get("id", "")).startswith("_")]

    errors, warns = validate(data, themes, seen_norm, a.force)
    for w in warns:
        print("WARN  " + w)
    for e in errors:
        print("ERROR " + e)
    if errors:
        print(f"\n{len(errors)} error(s). Nothing written.")
        return 1

    themes_m, seen_m, stats = apply_state(data, themes, seen)
    by_id = {t["id"]: t for t in themes_m}
    rows = tracking_rows(themes_m, data["date"], stats["touched"])
    md = render_md(data, by_id, rows, stats)
    page = render_html(data, by_id, rows, stats)

    out = Path(a.out) if a.out else OSINT
    out.mkdir(parents=True, exist_ok=True)
    if a.dry_run:
        md_path, html_path = out / f"{data['date']}.md", out / f"{data['date']}.html"
    else:
        (OSINT / "archive").mkdir(exist_ok=True)
        md_path, html_path = OSINT / "archive" / f"{data['date']}.md", OSINT / "roundup_email.html"
        if md_path.exists() and not a.force:
            print(f"ERROR {md_path} already exists for today. Re-running? Add --force to overwrite.")
            return 1
    md_path.write_text(md)
    html_path.write_text(page)
    wc = words(strip_md(md.split("## Tracking")[0]))
    print(f"wrote {md_path}\nwrote {html_path}")
    print(f"{stats['new']} new · {stats['updated']} updated · {len(data['items'])} items · {wc} words"
          + (f"  (over the ~{WORD_BUDGET} budget, trim)" if wc > WORD_BUDGET else ""))
    if stats["created"]:
        print("new themes: " + ", ".join(stats["created"]))

    if a.dry_run:
        print("dry run: state untouched, nothing sent")
        return 0

    if a.update_state or a.send:
        save_json(OSINT / "themes.json", themes_m)
        save_json(OSINT / "seen.json", seen_m)
        print(f"state recorded: {len(themes_m)} themes, {len(seen_m)} seen urls")

    if a.send:
        subject = f"OSINT round-up — {long_date(data['date'])}"
        try:
            msg = send_email(subject, page)
            print(f"sent to {TO}: {subject}" + (f"\n{msg}" if msg else ""))
        except Exception as e:  # noqa: BLE001
            print(f"SEND FAILED (state and files are saved; re-run with --send --force later): {e}")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
