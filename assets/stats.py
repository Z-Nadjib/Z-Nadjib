"""Fetch public GitHub activity and draw the stats cards of the profile README.

    python3 assets/stats.py            # fetch, cache and draw
    python3 assets/stats.py --cached   # redraw from the last fetch, no network

Uses GITHUB_TOKEN when it is set (the daily workflow does), and works without
it for a local run. Shares fonts and styling with build.py.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

import build as b

USER = "Z-Nadjib"
TZ = ZoneInfo("Europe/Paris")
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
CACHE = Path(__file__).resolve().parent / ".stats-cache.json"


# --------------------------------------------------------------------------- data
def get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "profile-stats"})
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode()


def api(path):
    return json.loads(get("https://api.github.com" + path))


def contributions():
    """Daily contribution counts for the last year, from the public profile calendar."""
    html = get(f"https://github.com/users/{USER}/contributions")
    counts = {}
    for m in re.finditer(r'<tool-tip[^>]*for="([^"]+)"[^>]*>([^<]*)</tool-tip>', html):
        n = re.match(r"(\d+)", m.group(2))
        counts[m.group(1)] = int(n.group(1)) if n else 0
    days = []
    for td in re.findall(r"<td[^>]*ContributionCalendar-day[^>]*>", html):
        date = re.search(r'data-date="([\d-]+)"', td)
        ident = re.search(r'id="([^"]+)"', td)
        if date and ident:
            days.append((dt.date.fromisoformat(date.group(1)), counts.get(ident.group(1), 0)))
    return sorted(days)


def streaks(days):
    longest = run = 0
    for _, n in days:
        run = run + 1 if n else 0
        longest = max(longest, run)
    current = 0
    tail = days[:-1] if days and days[-1][1] == 0 else days  # today may still be empty
    for _, n in reversed(tail):
        if not n:
            break
        current += 1
    return current, longest


def collect():
    user = api(f"/users/{USER}")
    repos = [r for r in api(f"/users/{USER}/repos?per_page=100&type=owner") if not r["fork"] and r["name"] != USER]
    langs = Counter()
    for r in repos:
        for lang in api(f"/repos/{USER}/{r['name']}/languages"):
            langs[lang] += 1
    stamps = []
    for r in repos:
        page = 1
        while True:
            try:
                batch = api(f"/repos/{USER}/{r['name']}/commits?author={USER}&per_page=100&page={page}")
            except urllib.error.HTTPError as err:
                if err.code == 409:  # empty repository
                    break
                raise
            stamps += [dt.datetime.fromisoformat(c["commit"]["author"]["date"].replace("Z", "+00:00")).astimezone(TZ) for c in batch]
            if len(batch) < 100:
                break
            page += 1
    commits = api(f"/search/commits?q=author:{USER}&per_page=1")["total_count"]
    days = contributions()
    current, longest = streaks(days)
    return {
        "days": days, "current": current, "longest": longest,
        "contrib": sum(n for _, n in days), "commits": commits,
        "repos": user["public_repos"], "stars": sum(r["stargazers_count"] for r in repos),
        "since": dt.date.fromisoformat(user["created_at"][:10]).year,
        "langs": langs.most_common(6), "repo_count": len(repos),
        "hours": Counter(s.hour for s in stamps), "sampled": len(stamps),
    }


# --------------------------------------------------------------------------- drawing
def days_label(n):
    return f"{n} day" if n == 1 else f"{n} days"


def frame(d, accent):
    b.set_accent(accent)
    shape = b.rounded(0.5, 0.5, d.w - 1, d.h - 1, 20, 20, 20, 20)
    sheen = b.metal(d, shape, d.w, d.h)
    d.defs.append(b.glow("gl", 4))
    d.css.append(b.COMMON_CSS)
    return shape, sheen


def close(d, shape, sheen):
    d.add(sheen, f'<path d="{shape}" fill="none" stroke="url(#rim)" stroke-width="1.5"/>')


def rise(begin, dy=12):
    """One-shot entrance: fade in while sliding up."""
    return (f'<animate attributeName="opacity" from="0" to="1" begin="{begin:.2f}s" dur="0.5s" fill="freeze"/>'
            f'<animateTransform attributeName="transform" type="translate" from="0 {dy}" to="0 0" begin="{begin:.2f}s" '
            f'dur="0.5s" fill="freeze"/>')


def overview(s):
    W, H = 1200, 170
    tiles = [
        (f"{s['contrib']}", "contributions (1 year)", "teal"),
        (f"{s['commits']}", "commits", "sky"),
        (f"{s['repos']}", "public repositories", "indigo"),
        (f"{s['stars']}", "stars earned", "amber"),
        (f"{s['longest']}", "longest streak (days)", "rose"),
        (f"{s['since']}", "on GitHub since", "green"),
    ]
    d = b.Doc(W, H, "GitHub at a glance: " + ", ".join(f"{v} {l}" for v, l, _ in tiles))
    shape, sheen = frame(d, b.ACCENTS["indigo"])
    tw = (W - 40) / len(tiles)
    for k, (value, label, acc) in enumerate(tiles):
        col = b.ACCENTS[acc]
        x = 20 + k * tw
        cx = x + tw / 2
        if k:
            d.add(f'<path d="M{x:.1f},34 V{H - 34}" stroke="{b.LINE}"/>')
        d.use(value, "sans", 600)
        d.use(label, "mono", 400)
        d.add(f'<g opacity="0">'
              f'<text x="{cx:.1f}" y="86" text-anchor="middle" font-family="{b.FAMILY["sans"]}" font-weight="600" font-size="44" fill="{col}">{b.e(value)}</text>'
              f'<text x="{cx:.1f}" y="116" text-anchor="middle" font-family="{b.FAMILY["mono"]}" font-size="13" fill="{b.BODY}">{b.e(label)}</text>'
              f'<rect x="{cx - 18:.1f}" y="132" width="36" height="3" rx="1.5" fill="{col}" opacity="0.8"/>'
              f'{rise(0.2 + 0.15 * k)}</g>')
    close(d, shape, sheen)
    d.write("stats-overview.svg")


def calendar(s):
    W, H = 1200, 320
    days = s["days"]
    d = b.Doc(W, H, f"Contribution calendar: {s['contrib']} contributions in the last year")
    shape, sheen = frame(d, b.ACCENTS["teal"])
    acc = b.HOT
    d.text(40, 52, "Contribution calendar", "sans", 600, 22, "#fff")
    d.text(W - 40, 52, f"{s['contrib']} contributions in the last year", "mono", 400, 14, acc, "end")
    cell, gap, x0, y0 = 16, 4, 92, 86
    first = days[0][0]
    offset = (first.weekday() + 1) % 7  # GitHub weeks start on Sunday
    top = max(n for _, n in days) or 1
    cols = {}
    months = {}
    for date, n in days:
        i = (date - first).days + offset
        c, r = divmod(i, 7)
        if n == 0:
            fill, op = b.TILE, 1
        else:
            fill, op = acc, 0.3 + 0.7 * (n / top) ** 0.5
        cols.setdefault(c, []).append(f'<rect x="{x0 + c * (cell + gap)}" y="{y0 + r * (cell + gap)}" width="{cell}" height="{cell}" '
                                      f'rx="4" fill="{fill}" opacity="{op:.2f}"/>')
        if date.day <= 7 and r == 0 or (date.day == 1):
            months.setdefault(date.strftime("%b"), c)
    for c, rects in sorted(cols.items()):
        d.add(f'<g opacity="0">{"".join(rects)}'
              f'<animate attributeName="opacity" from="0" to="1" begin="{0.2 + c * 0.03:.2f}s" dur="0.3s" fill="freeze"/></g>')
    for name, c in months.items():
        d.text(x0 + c * (cell + gap), y0 - 10, name, "mono", 400, 12, b.MUTED)
    for r, name in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
        d.text(x0 - 14, y0 + r * (cell + gap) + 12, name, "mono", 400, 12, b.MUTED, "end")
    # a light that keeps sweeping across the year
    gw = 53 * (cell + gap)
    d.defs.append(f'<linearGradient id="scan" x1="0" x2="1"><stop offset="0" stop-color="{acc}" stop-opacity="0"/>'
                  f'<stop offset="0.5" stop-color="{acc}" stop-opacity="0.22"/><stop offset="1" stop-color="{acc}" stop-opacity="0"/></linearGradient>')
    d.add(f'<rect y="{y0 - 4}" width="80" height="{7 * (cell + gap) + 4}" fill="url(#scan)">'
          f'<animate attributeName="x" values="{x0 - 80};{x0 + gw}" dur="6s" begin="2s" repeatCount="indefinite"/></rect>')
    best_date, best = max(days, key=lambda t: t[1])
    active = sum(1 for _, n in days if n)
    wd = Counter()
    for date, n in days:
        wd[date.weekday()] += n
    facts = [("best day", f"{best} on {best_date.strftime('%b %d')}"), ("active days", f"{active}"),
             ("current streak", days_label(s["current"])), ("longest streak", days_label(s["longest"])),
             ("busiest weekday", WEEKDAYS[wd.most_common(1)[0][0]] if wd else "-")]
    fx, fy = 40, 262
    fw = (W - 80) / len(facts)
    for k, (label, value) in enumerate(facts):
        x = fx + k * fw
        d.text(x, fy, label, "mono", 400, 12, b.MUTED)
        d.text(x, fy + 26, value, "sans", 600, 19, "#fff")
    close(d, shape, sheen)
    d.write("stats-calendar.svg")


def languages(s):
    W, H = 600, 360
    d = b.Doc(W, H, "Languages across my repositories: " + ", ".join(f"{l} ({n})" for l, n in s["langs"]))
    shape, sheen = frame(d, b.ACCENTS["orange"])
    d.text(34, 52, "Languages", "sans", 600, 22, "#fff")
    d.text(W - 34, 52, f"across {s['repo_count']} repositories", "mono", 400, 13, b.HOT, "end")
    palette = ["orange", "amber", "rose", "sky", "teal", "lavender"]
    top = s["langs"][0][1] if s["langs"] else 1
    for k, (lang, n) in enumerate(s["langs"]):
        col = b.ACCENTS[palette[k % len(palette)]]
        y = 96 + k * 40
        full = 300 * n / top
        d.text(34, y + 15, lang, "sans", 600, 16, b.V200)
        d.add(f'<rect x="200" y="{y}" width="300" height="20" rx="10" fill="{b.TILE}"/>',
              f'<rect x="200" y="{y}" width="0" height="20" rx="10" fill="{col}" opacity="0.85">'
              f'<animate attributeName="width" from="0" to="{full:.1f}" begin="{0.3 + 0.12 * k:.2f}s" dur="1s" fill="freeze" '
              f'calcMode="spline" keySplines=".2 .8 .2 1" keyTimes="0;1"/></rect>')
        d.text(W - 34, y + 15, f"{n} repo{'s' if n > 1 else ''}", "mono", 400, 13, b.BODY, "end")
    close(d, shape, sheen)
    d.write("stats-languages.svg")


def hours(s):
    W, H = 600, 360
    counts = [s["hours"].get(h, 0) for h in range(24)]
    peak = max(range(24), key=lambda h: counts[h])
    kind = "night owl" if peak >= 20 or peak < 5 else "early bird" if peak < 10 else "daytime coder"
    d = b.Doc(W, H, f"When I commit, Paris time: busiest hour {peak:02d}:00, {kind}")
    shape, sheen = frame(d, b.ACCENTS["lavender"])
    d.text(34, 52, "When I commit", "sans", 600, 22, "#fff")
    d.text(W - 34, 52, f"{kind} · peak {peak:02d}:00", "mono", 400, 13, b.HOT, "end")
    top = max(counts) or 1
    x0, base, bw, gap, hmax = 40, 290, 18, 4, 190
    for h, n in enumerate(counts):
        x = x0 + h * (bw + gap)
        bh = max(hmax * n / top, 3)
        col = b.HOT if h == peak else b.V400
        t0 = f'begin="{0.3 + 0.04 * h:.2f}s" dur="0.6s" fill="freeze"'
        d.add(f'<rect x="{x}" y="{base}" width="{bw}" height="0" rx="4" fill="{col}" opacity="{1 if h == peak else 0.55}">'
              f'<animate attributeName="y" from="{base}" to="{base - bh:.1f}" {t0}/>'
              f'<animate attributeName="height" from="0" to="{bh:.1f}" {t0}/></rect>')
    for h in (0, 6, 12, 18, 23):
        d.text(x0 + h * (bw + gap) + bw / 2, base + 24, f"{h:02d}h", "mono", 400, 12, b.MUTED, "middle")
    d.text(34, H - 22, f"{s['sampled']} commits, Paris time", "mono", 400, 12, b.BODY)
    close(d, shape, sheen)
    d.write("stats-hours.svg")


def save(data):
    raw = dict(data, days=[[d.isoformat(), n] for d, n in data["days"]], hours={str(h): n for h, n in data["hours"].items()})
    CACHE.write_text(json.dumps(raw))


def load():
    raw = json.loads(CACHE.read_text())
    return dict(raw, days=[(dt.date.fromisoformat(d), n) for d, n in raw["days"]],
                hours=Counter({int(h): n for h, n in raw["hours"].items()}), langs=[tuple(x) for x in raw["langs"]])


if __name__ == "__main__":
    if "--cached" in sys.argv:
        data = load()
    else:
        data = collect()
        save(data)
    overview(data)
    calendar(data)
    languages(data)
    hours(data)
