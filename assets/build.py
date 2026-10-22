"""Build the animated SVGs of the profile README.

    pip install fonttools brotli pillow
    python3 assets/build.py

Sources live in assets/src/: fonts (SIL OFL), brand icons (Simple Icons, CC0;
Skill Icons, MIT) and the avatar. Each SVG embeds a subset of the fonts it
uses, so it renders the same everywhere. The stats cards come from stats.py.
"""
import base64
import io
import math
from pathlib import Path
from xml.sax.saxutils import escape

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from PIL import Image

OUT = Path(__file__).resolve().parent
SRC = OUT / "src"

# Dark charcoal grey, lighter than GitHub's dark page so cards stand out; one pastel accent per card.
BG0 = "#121417"
BG1 = "#1C1F24"
BG2 = "#24282E"
TILE = "#282C32"
LINE = "#363B43"
V100 = "#F5F6F8"   # white metal
V200 = "#DADEE3"   # silver
V300 = "#C3C8D0"   # silver, for the "normal" parts of an illustration
V400 = "#9BA2AD"   # steel
TEXT = "#F5F6F8"
BODY = "#C4C9D0"
MUTED = "#8E95A0"
# Accent slots, rebound per card by set_accent().
V500 = V600 = HOT = "#A5B4FC"
V700 = "#3B3F5C"
GREEN = "#4ADE80"  # live status: open source, published

ACCENTS = {
    "indigo": "#A5B4FC", "teal": "#5EEAD4", "sky": "#7DD3FC", "rose": "#FDA4AF", "amber": "#FCD34D",
    "green": "#86EFAC", "orange": "#FDBA74", "blue": "#93C5FD", "pink": "#F9A8D4", "lime": "#BEF264",
    "cyan": "#67E8F9", "lavender": "#C4B5FD", "red": "#FCA5A5",
}


def mix(a, b, t):
    """Blend hex colour a towards b by t."""
    pa, pb = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(pa, pb))


def set_accent(color):
    global V500, V600, V700, HOT
    V500 = V600 = HOT = color
    V700 = mix(color, BG0, 0.6)


FAMILY = {
    "mono": "'Nadjib Mono','JetBrains Mono','Fira Code',Menlo,Consolas,monospace",
    "sans": "'Nadjib Sans','Instrument Sans','Segoe UI',Helvetica,Arial,sans-serif",
}
FACE_NAME = {"mono": "Nadjib Mono", "sans": "Nadjib Sans"}


# --------------------------------------------------------------------------- fonts
def _load_fonts():
    specs = {
        ("mono", 400): ("JetBrainsMono.ttf", {"wght": 400}),
        ("mono", 700): ("JetBrainsMono.ttf", {"wght": 700}),
        ("sans", 400): ("InstrumentSans.ttf", {"wght": 400, "wdth": 100}),
        ("sans", 600): ("InstrumentSans.ttf", {"wght": 600, "wdth": 100}),
    }
    fonts = {}
    for key, (file, axes) in specs.items():
        static = instancer.instantiateVariableFont(TTFont(SRC / "fonts" / file), axes)
        buf = io.BytesIO()
        static.save(buf)
        fonts[key] = buf.getvalue()
    return fonts


FONTS = _load_fonts()
METRICS = {}
for _key, _data in FONTS.items():
    _f = TTFont(io.BytesIO(_data))
    METRICS[_key] = (_f.getBestCmap(), _f["hmtx"].metrics, _f["head"].unitsPerEm)


def width(s, fam="sans", wt=400, size=20):
    cmap, hmtx, upm = METRICS[(fam, wt)]
    return sum(hmtx[cmap.get(ord(c), ".notdef")][0] for c in s) * size / upm


def fit(s, max_w, fam="sans", wt=400, size=20):
    """Largest font size <= size that keeps s within max_w."""
    while width(s, fam, wt, size) > max_w and size > 8:
        size -= 0.5
    return size


def wrap(s, max_w, fam="sans", wt=400, size=20):
    lines, cur = [], ""
    for word in s.split():
        test = f"{cur} {word}".strip()
        if width(test, fam, wt, size) <= max_w:
            cur = test
        else:
            lines.append(cur)
            cur = word
    return lines + [cur] if cur else lines


def font_face(fam, wt, chars):
    font = TTFont(io.BytesIO(FONTS[(fam, wt)]))
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.hinting = False
    opts.layout_features = ["kern"]
    sub = subset.Subsetter(opts)
    sub.populate(text="".join(sorted(chars | {" "})))
    sub.subset(font)
    font.flavor = "woff2"
    buf = io.BytesIO()
    font.save(buf)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return (f"@font-face{{font-family:'{FACE_NAME[fam]}';font-weight:{wt};"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")


# --------------------------------------------------------------------------- icons
def icon_uri(name, color=None):
    svg = (SRC / "icons" / f"{name}.svg").read_text()
    if name.startswith("si-"):
        svg = svg.replace("<svg ", f'<svg fill="{color or V200}" ', 1)
    else:
        svg = svg.replace("#242938", TILE)  # Skill Icons tile, recoloured to the palette
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


# --------------------------------------------------------------------------- document helper
def e(s):
    return escape(str(s), {'"': "&quot;"})


class Doc:
    def __init__(self, w, h, label, pad=(0, 0, 0, 0)):
        """pad is transparent space (top, right, bottom, left) around the w x h drawing."""
        self.w, self.h, self.label, self.pad = w, h, label, pad
        self.parts, self.defs, self.css = [], [], []
        self.chars = {}

    def add(self, *s):
        self.parts.extend(s)

    def use(self, s, fam, wt):
        self.chars.setdefault((fam, wt), set()).update(s)

    def text(self, x, y, s, fam="sans", wt=400, size=18, fill=TEXT, anchor="start", attrs="", inner=""):
        self.use(s, fam, wt)
        a = f' text-anchor="{anchor}"' if anchor != "start" else ""
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FAMILY[fam]}" font-weight="{wt}" '
                 f'font-size="{size}" fill="{fill}"{a}{attrs}>{e(s)}{inner}</text>')

    def write(self, name):
        faces = "".join(font_face(f, w, c) for (f, w), c in sorted(self.chars.items()))
        t, r, bt, l = self.pad
        W, H = self.w + l + r, self.h + t + bt
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
               f'viewBox="{-l} {-t} {W} {H}" role="img" aria-label="{e(self.label)}">\n'
               f"<title>{e(self.label)}</title>\n<style>{faces}{''.join(self.css)}</style>\n"
               f"<defs>{''.join(self.defs)}</defs>\n" + "\n".join(self.parts) + "\n</svg>\n")
        (OUT / name).write_text(svg, encoding="utf-8")
        print(f"wrote {name:28s} {len(svg) / 1024:6.1f} KB")


def glow(id_, std=6):
    return (f'<filter id="{id_}" x="-50%" y="-50%" width="200%" height="200%">'
            f'<feGaussianBlur stdDeviation="{std}" result="b"/>'
            f'<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')


def rounded(x, y, w, h, tl=0, tr=0, br=0, bl=0):
    """Rectangle path with an individual radius per corner."""
    return (f"M{x + tl},{y}H{x + w - tr}" + (f"A{tr},{tr} 0 0 1 {x + w},{y + tr}" if tr else "")
            + f"V{y + h - br}" + (f"A{br},{br} 0 0 1 {x + w - br},{y + h}" if br else "")
            + f"H{x + bl}" + (f"A{bl},{bl} 0 0 1 {x},{y + h - bl}" if bl else "")
            + f"V{y + tl}" + (f"A{tl},{tl} 0 0 1 {x + tl},{y}" if tl else "") + "Z")


def discrete(points, total):
    """keyTimes and values for a discrete SMIL animation from (time, value) pairs."""
    pts = sorted(points)
    if pts[0][0] > 0:
        pts.insert(0, (0, pts[0][1]))
    return (";".join(f"{min(t / total, 1):.4f}" for t, _ in pts),
            ";".join(str(v) for _, v in pts))


def blink(t_on, t_off, dur, lo=0.0, hi=1.0, attr="opacity"):
    """SMIL animate that sits at lo, rises to hi between t_on and t_off (seconds) in a dur loop."""
    a, b = t_on / dur, t_off / dur
    return (f'<animate attributeName="{attr}" dur="{dur}s" repeatCount="indefinite" '
            f'keyTimes="0;{a:.4f};{min(a + 0.03, 1):.4f};{b:.4f};{min(b + 0.05, 1):.4f};1" '
            f'values="{lo};{lo};{hi};{hi};{lo};{lo}"/>')


COMMON_CSS = (".bob{animation:bob 3.2s ease-in-out infinite}@keyframes bob{50%{transform:translateY(-8px)}}"
              ".pulse{animation:pulse 2s ease-in-out infinite}@keyframes pulse{50%{opacity:.3}}"
              ".flow{stroke-dasharray:5 9;animation:flow 1.4s linear infinite}@keyframes flow{to{stroke-dashoffset:-28}}")


def metal(d, shape, w, h, sheen_delay=0.0):
    """Brushed-metal fill, a light sheen sweeping across, and a slowly turning metallic rim."""
    d.defs.append(
        f'<clipPath id="mclip"><path d="{shape}"/></clipPath>'
        f'<linearGradient id="mbg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BG2}"/>'
        f'<stop offset="0.5" stop-color="{BG1}"/><stop offset="1" stop-color="#1F2227"/></linearGradient>'
        f'<pattern id="brush" width="{w}" height="3" patternUnits="userSpaceOnUse">'
        f'<rect width="{w}" height="1" fill="#FFFFFF" opacity="0.022"/></pattern>'
        f'<linearGradient id="sheen" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        f'<stop offset="0.5" stop-color="#fff" stop-opacity="0.07"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        f'<linearGradient id="rim" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{w}" y2="{h}">'
        f'<stop offset="0" stop-color="#4A5059"/><stop offset="0.3" stop-color="#A9B0BA"/>'
        f'<stop offset="0.55" stop-color="#3A3F47"/><stop offset="0.8" stop-color="#7D848E"/><stop offset="1" stop-color="#434951"/>'
        f'<animateTransform attributeName="gradientTransform" type="rotate" values="0 {w / 2} {h / 2};360 {w / 2} {h / 2}" '
        f'dur="14s" repeatCount="indefinite"/></linearGradient>')
    d.add(f'<path d="{shape}" fill="url(#mbg)"/>', f'<path d="{shape}" fill="url(#brush)"/>')
    return (f'<g clip-path="url(#mclip)"><rect x="{-w * 0.5}" y="{-h * 0.2}" width="{w * 0.35}" height="{h * 1.4}" '
            f'fill="url(#sheen)" transform="skewX(-18)">'
            f'<animate attributeName="x" values="{-w * 0.5};{-w * 0.5};{w * 1.3}" keyTimes="0;0.55;1" dur="7s" '
            f'begin="{sheen_delay:.1f}s" repeatCount="indefinite"/></rect></g>')


# --------------------------------------------------------------------------- section titles
def title(key, label):
    """Orange title that reads on GitHub light and dark, with a moving glint."""
    W, H = 1200, 76
    d = Doc(W, H, label)
    tw = width(label, "sans", 600, 34)
    left, right = W / 2 - tw / 2 - 28, W / 2 + tw / 2 + 28
    d.defs.append(f'<linearGradient id="ll" x1="0" x2="1"><stop offset="0" stop-color="#EA580C" stop-opacity="0"/>'
                  f'<stop offset="1" stop-color="#EA580C"/></linearGradient>'
                  f'<linearGradient id="lr" x1="0" x2="1"><stop offset="0" stop-color="#EA580C"/>'
                  f'<stop offset="1" stop-color="#EA580C" stop-opacity="0"/></linearGradient>'
                  f'<linearGradient id="chrome" gradientUnits="userSpaceOnUse" x1="{W / 2 - tw / 2}" x2="{W / 2 + tw / 2}" y1="0" y2="0">'
                  f'<stop offset="0" stop-color="#EA580C"/><stop offset="0.45" stop-color="#EA580C"/>'
                  f'<stop offset="0.5" stop-color="#FDBA74"/><stop offset="0.55" stop-color="#EA580C"/><stop offset="1" stop-color="#EA580C"/>'
                  f'<animateTransform attributeName="gradientTransform" type="translate" values="{-tw} 0;{-tw} 0;{tw} 0" '
                  f'keyTimes="0;0.5;1" dur="6s" repeatCount="indefinite"/></linearGradient>')
    d.add(f'<rect x="{left - 300:.0f}" y="37" width="300" height="2" fill="url(#ll)"/>',
          f'<rect x="{right:.0f}" y="37" width="300" height="2" fill="url(#lr)"/>',
          f'<rect x="{left - 10:.0f}" y="33" width="10" height="10" fill="#EA580C" transform="rotate(45 {left - 5:.0f} 38)"/>',
          f'<rect x="{right:.0f}" y="33" width="10" height="10" fill="#EA580C" transform="rotate(45 {right + 5:.0f} 38)"/>')
    d.text(W / 2, 50, label, "sans", 600, 34, "url(#chrome)", "middle")
    d.write(f"title-{key}.svg")


# --------------------------------------------------------------------------- whoami banner and contact tiles
def whoami():
    set_accent(ACCENTS["indigo"])
    W, H, T = 1200, 250, 13.0
    d = Doc(W, H, "whoami: Zahaf Boualem Nadjib, AI Engineer and Researcher in Nancy, France. "
                  "Skills: RAG, GraphRAG, agentic AI, LLMs, knowledge graphs.", pad=(0, GUTTER, 0, GUTTER))
    shape = rounded(0.5, 0.5, W - 1, H, 18, 18, 0, 0)
    sheen = metal(d, shape, W, H)
    d.defs.append(glow("soft", 4))
    d.add(sheen, f'<path d="M0.5,{H} V18.5 A18,18 0 0 1 18.5,0.5 H{W - 18.5} A18,18 0 0 1 {W - 0.5},18.5 V{H}" fill="none" stroke="url(#rim)" stroke-width="1.5"/>',
          f'<path d="M0 38 H{W}" stroke="{LINE}"/>')
    for i, c in enumerate([HOT, V300, V400]):
        d.add(f'<circle cx="{24 + i * 20}" cy="19" r="6" fill="{c}"/>')
    d.text(W / 2, 24, "nadjib@nancy: ~", "mono", 400, 13, MUTED, "middle")

    # avatar with rotating rings
    cx, cy, r = 128, 145, 72
    img = Image.open(SRC / "avatar.jpg").convert("RGB").resize((2 * r, 2 * r), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    b64 = base64.b64encode(buf.getvalue()).decode()
    d.defs.append(f'<clipPath id="av"><circle cx="{cx}" cy="{cy}" r="{r}"/></clipPath>'
                  f'<radialGradient id="halo"><stop offset="0" stop-color="{HOT}" stop-opacity="0.3"/>'
                  f'<stop offset="1" stop-color="{HOT}" stop-opacity="0"/></radialGradient>')
    d.css.append(COMMON_CSS + "@keyframes spin{to{transform:rotate(360deg)}}"
                 f".r1{{transform-origin:{cx}px {cy}px;animation:spin 14s linear infinite}}"
                 f".r2{{transform-origin:{cx}px {cy}px;animation:spin 22s linear infinite reverse}}"
                 ".blink{animation:bl 1s steps(1) infinite}@keyframes bl{50%{opacity:0}}")
    d.add(f'<circle cx="{cx}" cy="{cy}" r="{r + 40}" fill="url(#halo)"/>',
          f'<image href="data:image/jpeg;base64,{b64}" x="{cx - r}" y="{cy - r}" width="{2 * r}" height="{2 * r}" clip-path="url(#av)"/>',
          f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{V200}" stroke-width="2"/>',
          f'<g class="r1"><circle cx="{cx}" cy="{cy}" r="{r + 11}" fill="none" stroke="{HOT}" stroke-width="3" stroke-dasharray="60 26 10 26" stroke-linecap="round"/>'
          + "".join(f'<circle cx="{cx + (r + 11) * math.cos(a):.1f}" cy="{cy + (r + 11) * math.sin(a):.1f}" r="4" fill="{V100}" filter="url(#soft)"/>'
                    for a in (0.3, 2.4, 4.5)) + "</g>",
          f'<g class="r2"><circle cx="{cx}" cy="{cy}" r="{r + 21}" fill="none" stroke="{V300}" stroke-opacity="0.4" stroke-dasharray="3 8"/></g>')

    # typed session
    x0, y0, step, fs = 268, 80, 34, 18
    cw = width("M", "mono", 400, fs)
    prompt = [("nadjib@nancy", HOT), (":~$ ", MUTED)]
    plen = sum(len(t) for t, _ in prompt)
    lines = [
        ("cmd", prompt + [("whoami", TEXT)], 0.3, 0.5, 1.2),
        ("out", [("Zahaf Boualem Nadjib", V100, 700), ("  AI Engineer & Researcher", V300, 400),
                 (" · Nancy, France", MUTED, 400)], 1.5, None, None),
        ("cmd", prompt + [("ls skills/", TEXT)], 2.3, 2.5, 3.3),
        ("out", [("rag/  graphrag/  agentic-ai/  llm/  knowledge-graphs/", HOT, 400)], 3.6, None, None),
    ]
    final = 4.4
    body = []
    for i, (kind, segs, appear, ts, te) in enumerate(lines):
        segs = [s if len(s) == 3 else (s[0], s[1], 400) for s in segs]
        y = y0 + i * step
        for t, _, wt in segs:
            d.use(t, "mono", wt)
        spans = "".join(f'<tspan fill="{c}" font-weight="{wt}">{e(t)}</tspan>' for t, c, wt in segs)
        text = f'<text x="{x0}" y="{y}" font-family="{FAMILY["mono"]}" font-size="{fs}" xml:space="preserve">{spans}</text>'
        if ts is None:
            body.append(f'<g opacity="0">{text}<animate attributeName="opacity" dur="{T}s" repeatCount="indefinite" '
                        f'calcMode="discrete" keyTimes="0;{appear / T:.4f}" values="0;1"/></g>')
            continue
        full = sum(len(t) for t, _, _ in segs)
        n = full - plen
        pts = [(0, 0), (appear, plen * cw)] + [(ts + (te - ts) * k / n, (plen + k) * cw) for k in range(1, n + 1)]
        kt, vals = discrete([(t, f"{v:.1f}") for t, v in pts], T)
        body.append(f'<clipPath id="c{i}"><rect x="{x0 - 2}" y="{y - fs}" height="{fs + 10}" width="0">'
                    f'<animate attributeName="width" dur="{T}s" repeatCount="indefinite" calcMode="discrete" '
                    f'keyTimes="{kt}" values="{vals}"/></rect></clipPath><g clip-path="url(#c{i})">{text}</g>')
        nxt = lines[i + 1][2]
        kt2, vals2 = discrete([(t, f"{x0 + v + 2:.1f}") for t, v in pts], T)
        body.append(f'<rect y="{y - fs + 3}" width="10" height="{fs + 2}" fill="{HOT}" opacity="0">'
                    f'<animate attributeName="x" dur="{T}s" repeatCount="indefinite" calcMode="discrete" keyTimes="{kt2}" values="{vals2}"/>'
                    f'<animate attributeName="opacity" dur="{T}s" repeatCount="indefinite" calcMode="discrete" '
                    f'keyTimes="0;{appear / T:.4f};{nxt / T:.4f}" values="0;1;0"/></rect>')
    yl = y0 + len(lines) * step
    spans = "".join(f'<tspan fill="{c}">{e(t)}</tspan>' for t, c in prompt)
    body.append(f'<g opacity="0"><text x="{x0}" y="{yl}" font-family="{FAMILY["mono"]}" font-size="{fs}" xml:space="preserve">{spans}</text>'
                f'<rect class="blink" x="{x0 + plen * cw + 2:.1f}" y="{yl - fs + 3}" width="10" height="{fs + 2}" fill="{HOT}"/>'
                f'<animate attributeName="opacity" dur="{T}s" repeatCount="indefinite" calcMode="discrete" '
                f'keyTimes="0;{final / T:.4f}" values="0;1"/></g>')
    d.add(f'<g>{"".join(body)}<animate attributeName="opacity" dur="{T}s" repeatCount="indefinite" '
          f'keyTimes="0;0.95;0.98;1" values="1;1;0;0"/></g>')

    # orbiting mini graph on the right
    ox, oy = 1085, 145
    d.css.append(f".o1{{transform-origin:{ox}px {oy}px;animation:spin 18s linear infinite}}"
                 f".o2{{transform-origin:{ox}px {oy}px;animation:spin 26s linear infinite reverse}}")
    d.add(f'<circle cx="{ox}" cy="{oy}" r="80" fill="url(#halo)"/>')
    for cls, rr, n, col, off in [("o1", 38, 4, V200, 0), ("o2", 68, 6, HOT, 0.4)]:
        pts = [(ox + rr * math.cos(2 * math.pi * k / n + off), oy + rr * math.sin(2 * math.pi * k / n + off)) for k in range(n)]
        g = [f'<circle cx="{ox}" cy="{oy}" r="{rr}" fill="none" stroke="{col}" stroke-opacity="0.2" stroke-dasharray="3 6"/>']
        g += [f'<line x1="{ox}" y1="{oy}" x2="{px:.1f}" y2="{py:.1f}" stroke="{col}" stroke-opacity="0.18"/>' for px, py in pts]
        g += [f'<line x1="{pts[k][0]:.1f}" y1="{pts[k][1]:.1f}" x2="{pts[(k + 1) % n][0]:.1f}" y2="{pts[(k + 1) % n][1]:.1f}" stroke="{col}" stroke-opacity="0.4"/>' for k in range(n)]
        g += [f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="{BG1}" stroke="{col}" stroke-width="2"/>' for px, py in pts]
        d.add(f'<g class="{cls}">{"".join(g)}</g>')
    d.add(f'<circle cx="{ox}" cy="{oy}" r="12" fill="{HOT}" filter="url(#soft)"><animate attributeName="r" values="10;14;10" dur="3s" repeatCount="indefinite"/></circle>')
    d.write("whoami.svg")

    # contact tiles: the bottom row of the same banner, one clickable image each
    tiles = [("linkedin", "si-linkedin", "LinkedIn", "in/zahaf-nadjib", "blue"),
             ("email", "si-gmail", "Email", "zahafndjib@gmail.com", "red"),
             ("orcid", "si-orcid", "ORCID", "0009-0009-9004-9580", "lime"),
             ("researchgate", "si-researchgate", "ResearchGate", "Zahaf-Boualem-Nadjib", "teal")]
    TW, TH = W // len(tiles), 84
    for i, (key, ic, label, handle, acc) in enumerate(tiles):
        col = ACCENTS[acc]
        first, last = i == 0, i == len(tiles) - 1
        # side gutters on the outer tiles only, so the row lines up with the banner and the cards
        t = Doc(TW, TH, f"{label}: {handle}", pad=(0, GUTTER if last else 0, 0, GUTTER if first else 0))
        shape = rounded(0.5 if first else 0, 0, TW - (1 if last else 0) - (0.5 if first else 0), TH - 0.5,
                        0, 0, 18 if last else 0, 18 if first else 0)
        sheen = metal(t, shape, TW, TH, sheen_delay=0.4 * i)
        t.add(sheen, f'<path d="M0 0.5 H{TW}" stroke="{LINE}"/>')
        if first:
            t.add(f'<path d="M0.5,0 V{TH - 18.5} A18,18 0 0 0 18.5,{TH - 0.5} H{TW}" fill="none" stroke="#5A6069" stroke-width="1.5"/>')
        elif last:
            t.add(f'<path d="M0,{TH - 0.5} H{TW - 18.5} A18,18 0 0 0 {TW - 0.5},{TH - 18.5} V0" fill="none" stroke="#5A6069" stroke-width="1.5"/>')
        else:
            t.add(f'<path d="M0,{TH - 0.5} H{TW}" stroke="#5A6069" stroke-width="1.5"/>')
        if not last:
            t.add(f'<path d="M{TW - 0.5},16 V{TH - 16}" stroke="{LINE}"/>')
        t.add(f'<circle cx="48" cy="{TH / 2}" r="23" fill="{col}" fill-opacity="0.12" stroke="{col}" stroke-opacity="0.5"/>',
              f'<image href="{icon_uri(ic, col)}" x="37" y="{TH / 2 - 11}" width="22" height="22"/>')
        t.text(84, TH / 2 - 3, label, "sans", 600, 18, "#fff")
        t.text(84, TH / 2 + 18, handle, "mono", 400, fit(handle, TW - 96, "mono", 400, 12.5), MUTED)
        t.write(f"contact-{key}.svg")


# --------------------------------------------------------------------------- card template
CW = 600
GUTTER = 12  # transparent margin on each side; two cards side by side get 2 * GUTTER between them


def card(name, H, label, illus, title_, meta=None, desc=None, tags=(), status=None, items=None, design_h=216):
    top = round(H * 0.4)
    d = Doc(CW, H, label, pad=(GUTTER,) * 4)
    shape = rounded(0.5, 0.5, CW - 1, H - 1, 22, 22, 22, 22)
    sheen = metal(d, shape, CW, H)
    d.defs.append(
        f'<linearGradient id="tg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#17191D"/>'
        f'<stop offset="0.5" stop-color="#212429"/><stop offset="1" stop-color="#16181C"/></linearGradient>'
        f'<pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="{V300}" opacity="0.12"/></pattern>'
        f'<linearGradient id="seam" x1="0" x2="1"><stop offset="0" stop-color="{HOT}" stop-opacity="0"/>'
        f'<stop offset="0.5" stop-color="{HOT}"/><stop offset="1" stop-color="{HOT}" stop-opacity="0"/></linearGradient>'
        f'<radialGradient id="spot" cx="0.5" cy="0.55" r="0.6"><stop offset="0" stop-color="{HOT}" stop-opacity="0.16"/>'
        f'<stop offset="1" stop-color="{HOT}" stop-opacity="0"/></radialGradient>'
        + glow("gl", 4) + glow("gl2", 8))
    d.css.append(COMMON_CSS)
    d.add('<g clip-path="url(#mclip)">',
          f'<rect width="{CW}" height="{top}" fill="url(#tg)"/>',
          f'<rect width="{CW}" height="{top}" fill="url(#grid)"/>',
          f'<rect width="{CW}" height="{top}" fill="url(#spot)"/>')
    if design_h:
        # illustrations are drawn on a 600x216 canvas, scaled to fit the top 40%
        k = top / design_h
        d.add(f'<g transform="translate({CW * (1 - k) / 2:.1f},0) scale({k:.4f})">')
        illus(d, CW, design_h)
        d.add("</g>")
    else:
        illus(d, CW, top)
    d.add(f'<rect y="{top - 1}" width="{CW}" height="2" fill="url(#seam)" opacity="0.7"/>', "</g>", sheen,
          f'<path d="{shape}" fill="none" stroke="url(#rim)" stroke-width="1.5"/>')

    X, maxw = 34, CW - 68
    y = top + 44
    if meta:
        d.text(X, y, meta, "mono", 400, 14, HOT)
        y += 38
    size = fit(title_, maxw, "sans", 600, 28)
    d.text(X, y, title_, "sans", 600, size, "#fff")
    y += 36
    if desc:
        for ln in wrap(desc, maxw, "sans", 400, 17)[:4]:
            d.text(X, y, ln, "sans", 400, 17, BODY)
            y += 25
    if items:
        x, y = X, y - 6
        for it in items:
            w = width(it, "mono", 400, 14) + 26
            if x + w > CW - X:
                x, y = X, y + 38
            d.add(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="30" rx="15" fill="{HOT}" fill-opacity="0.08" stroke="{HOT}" stroke-opacity="0.35"/>')
            d.text(x + w / 2, y + 20, it, "mono", 400, 14, V200, "middle")
            x += w + 9
    # bottom row: tags on the left, status on the right
    yb = H - 46
    sw = 0
    if status:
        txt, kind = status
        col = {"live": GREEN, "award": HOT}.get(kind, V400)
        sw = width(txt, "sans", 600, 15) + 22
        d.add(f'<circle class="pulse" cx="{CW - X - sw + 5:.1f}" cy="{yb + 15}" r="5" fill="{col}"/>')
        d.text(CW - X, yb + 20, txt, "sans", 600, 15, V300 if kind is None else col, "end")
    x = X
    for tg in tags:
        w = width(tg, "mono", 400, 13) + 22
        if x + w > CW - X - sw - 12:
            break
        d.add(f'<rect x="{x:.1f}" y="{yb}" width="{w:.1f}" height="28" rx="8" fill="{TILE}" stroke="{LINE}"/>')
        d.text(x + w / 2, yb + 19, tg, "mono", 400, 13, V300, "middle")
        x += w + 8
    d.write(f"{name}.svg")


# --------------------------------------------------------------------------- illustrations (top 40% of each card)
def graph_nodes(d, pts, edges, col, base_begin=0.0, dur=3.0, r=7):
    for a, b in edges:
        d.add(f'<line x1="{pts[a][0]}" y1="{pts[a][1]}" x2="{pts[b][0]}" y2="{pts[b][1]}" stroke="{col}" stroke-opacity="0.45" stroke-width="1.5"/>')
    for k, (x, y) in enumerate(pts):
        d.add(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{BG0}" stroke="{col}" stroke-width="2.5" filter="url(#gl)">'
              f'<animate attributeName="fill" values="{BG0};{col};{BG0}" dur="{dur}s" begin="{base_begin + 0.5 * k}s" repeatCount="indefinite"/></circle>')


def il_pgxlod(d, W, H):
    left = [(95, 62), (160, 38), (225, 74), (112, 140), (196, 160), (158, 100)]
    right = [(380, 70), (446, 42), (508, 88), (398, 150), (478, 158), (440, 104)]
    edges = [(0, 5), (1, 5), (2, 5), (3, 5), (4, 5), (0, 1), (1, 2), (3, 4)]
    for k, ((x1, y1), (x2, y2)) in enumerate(zip(left, right)):
        d.add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{HOT}" stroke-width="1.6" stroke-dasharray="4 5" opacity="0">'
              f'<animate attributeName="opacity" values="0;0.85;0.85;0" keyTimes="0;0.15;0.75;1" dur="3s" begin="{0.5 * k}s" repeatCount="indefinite"/></line>')
    graph_nodes(d, left, edges, V300)
    graph_nodes(d, right, edges, HOT)
    d.text(40, 30, "G₁", "mono", 400, 13, V300)
    d.text(W - 40, 30, "G₂", "mono", 400, 13, HOT, "end")
    d.text(W / 2, H - 16, "owl:sameAs ?", "mono", 400, 13, HOT, "middle")


def il_nexus(d, W, H):
    cx, cy = W / 2, H / 2 + 4
    models = ["JAPE", "GCN-Align", "BootEA", "NAEA", "KECG", "AliNet", "MRAEA", "RREA", "DGMC"]
    dur = 4.5
    for k, m in enumerate(models):
        a = -math.pi / 2 + 2 * math.pi * k / len(models)
        x, y = cx + 218 * math.cos(a), cy + 76 * math.sin(a)
        w = width(m, "mono", 700, 12) + 20
        d.add(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="{V400}" stroke-opacity="0.5" class="flow"/>')
        t0 = dur * k / len(models)
        d.add(f'<rect x="{x - w / 2:.1f}" y="{y - 13:.1f}" width="{w:.1f}" height="26" rx="13" fill="{TILE}" stroke="{V400}" stroke-width="1.5"/>'
              f'<rect x="{x - w / 2:.1f}" y="{y - 13:.1f}" width="{w:.1f}" height="26" rx="13" fill="{HOT}" fill-opacity="0.3" stroke="{HOT}" stroke-width="1.5" opacity="0">'
              f'{blink(t0, t0 + dur / len(models), dur)}</rect>')
        d.text(x, y + 4.5, m, "mono", 700, 12, V100, "middle")
    d.add(f'<circle cx="{cx}" cy="{cy}" r="36" fill="{HOT}" fill-opacity="0.2" stroke="{HOT}" stroke-width="2" filter="url(#gl2)"/>',
          f'<circle cx="{cx}" cy="{cy}" r="36" fill="none" stroke="{HOT}"><animate attributeName="r" values="36;56" dur="2.2s" repeatCount="indefinite"/>'
          f'<animate attributeName="stroke-opacity" values="0.7;0" dur="2.2s" repeatCount="indefinite"/></circle>')
    d.text(cx, cy + 5, "DBP15K", "mono", 700, 13, "#fff", "middle")


def il_rsna(d, W, H):
    cx, cy = 300, H / 2 + 2
    d.defs.append('<radialGradient id="brain" cx="0.45" cy="0.4" r="0.7"><stop offset="0" stop-color="#484E57"/>'
                  '<stop offset="1" stop-color="#1C1F24"/></radialGradient>')
    for k in range(4):
        d.add(f'<ellipse cx="{92 + k * 9}" cy="{cy - 18 + k * 12}" rx="34" ry="40" fill="#1C1F24" stroke="{V400}" stroke-opacity="{0.25 + 0.15 * k:.2f}"/>')
    d.text(110, H - 14, "~1M CT scans", "mono", 400, 12, MUTED, "middle")
    d.add(f'<ellipse cx="{cx}" cy="{cy}" rx="70" ry="86" fill="none" stroke="{V100}" stroke-width="6" opacity="0.85"/>',
          f'<ellipse cx="{cx}" cy="{cy}" rx="60" ry="76" fill="url(#brain)"/>',
          f'<path d="M{cx - 8},{cy - 10} q-14,10 -6,30 q6,10 12,0 z M{cx + 8},{cy - 10} q14,10 6,30 q-6,10 -12,0 z" fill="{BG0}" opacity="0.8"/>')
    for k in range(5):
        y = cy - 55 + k * 26
        d.add(f'<path d="M{cx - 48},{y} q12,-8 24,0 t24,0 t24,0 t24,0" fill="none" stroke="{V300}" stroke-opacity="0.22"/>')
    hx, hy, dur = cx + 26, cy - 34, 3.2
    t_hit = dur * ((hy - 18) / (H - 36))
    d.add(f'<circle cx="{hx}" cy="{hy}" r="13" fill="{HOT}" opacity="0.35" filter="url(#gl)">{blink(t_hit, dur, dur, 0.35, 0.95)}</circle>',
          f'<rect x="{hx - 24}" y="{hy - 22}" width="48" height="44" rx="4" fill="none" stroke="{HOT}" stroke-width="1.5" stroke-dasharray="5 4" opacity="0">'
          f'{blink(t_hit, dur, dur)}</rect>')
    d.text(hx + 32, hy - 26, "ICH 0.97", "mono", 700, 12, HOT, attrs=' opacity="0"', inner=blink(t_hit, dur, dur))
    d.add(f'<rect x="{cx - 92}" y="18" width="184" height="2" fill="{V200}" filter="url(#gl)">'
          f'<animate attributeName="y" values="18;{H - 18};18" dur="{dur * 2}s" repeatCount="indefinite"/></rect>')
    for k, (lab, vals) in enumerate([("EDH", "10;18;10"), ("IPH", "40;92;40"), ("IVH", "20;30;20"), ("SAH", "16;44;16"), ("SDH", "26;20;26")]):
        y = 50 + k * 28
        d.text(430, y + 10, lab, "mono", 400, 12, MUTED)
        d.add(f'<rect x="470" y="{y}" width="96" height="12" rx="6" fill="{TILE}"/>',
              f'<rect x="470" y="{y}" height="12" rx="6" fill="{HOT if lab == "IPH" else V400}" width="10">'
              f'<animate attributeName="width" values="{vals}" dur="{dur * 2}s" repeatCount="indefinite" calcMode="spline" keySplines=".4 0 .2 1;.4 0 .2 1"/></rect>')


def il_nadi(d, W, H):
    for k, w in enumerate([120, 150, 96, 136]):
        y = 44 + k * 34
        d.add(f'<rect x="{44}" y="{y}" width="{w}" height="20" rx="10" fill="{HOT}" fill-opacity="0.12" stroke="{V400}" stroke-opacity="0.6">'
              f'<animate attributeName="x" values="20;44;44;60" keyTimes="0;0.15;0.85;1" dur="4s" begin="{k * 0.6}s" repeatCount="indefinite"/>'
              f'<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.15;0.85;1" dur="4s" begin="{k * 0.6}s" repeatCount="indefinite"/></rect>')
        for j in range(w // 22):
            d.add(f'<rect x="{56 + j * 20}" y="{y + 8}" width="12" height="4" rx="2" fill="{V200}" opacity="0.5"/>')
    d.add(f'<path d="M208,{H / 2} H252" stroke="{V400}" stroke-width="2" class="flow"/>',
          f'<rect x="256" y="{H / 2 - 22}" width="96" height="44" rx="12" fill="{HOT}" fill-opacity="0.18" stroke="{HOT}" filter="url(#gl)"/>',
          f'<path d="M356,{H / 2} H392" stroke="{V400}" stroke-width="2" class="flow"/>')
    d.text(304, H / 2 + 5, "Model", "mono", 700, 13, "#fff", "middle")
    dur = 21 * 0.3
    for k in range(21):
        x, y = 406 + (k % 7) * 22, 62 + (k // 7) * 26
        t0 = 0.3 * k
        d.add(f'<rect x="{x}" y="{y}" width="14" height="14" rx="4" fill="{V400}" opacity="0.35"/>'
              f'<rect x="{x}" y="{y}" width="14" height="14" rx="4" fill="{HOT}" opacity="0">{blink(t0, t0 + 0.6, dur)}</rect>')
    d.text(476, 160, "21 dialects", "mono", 400, 12, MUTED, "middle")
    mx, my = 548, 46
    d.add(f'<path d="M{mx - 10},{my - 34} L{mx - 2},{my - 8} M{mx + 10},{my - 34} L{mx + 2},{my - 8}" stroke="{V400}" stroke-width="5"/>',
          f'<circle cx="{mx}" cy="{my}" r="19" fill="{HOT}" fill-opacity="0.25" stroke="{HOT}" stroke-width="2" filter="url(#gl)"/>')
    d.text(mx, my + 6, "3", "sans", 600, 18, "#fff", "middle")
    d.text(mx, my + 40, "3rd", "mono", 700, 12, HOT, "middle")


def il_pais(d, W, H):
    for k in range(4):
        d.add(f'<path d="M30,{50 + k * 36} H{W - 30}" stroke="{V400}" stroke-opacity="0.1"/>')
    # a connected right-to-left word: ascenders, bowls, teeth and a descending tail
    stroke = ("M552,132 H508 C500,132 496,126 496,118 V52 "
              "M496,120 C496,140 474,142 462,134 C450,126 452,108 464,106 C476,104 482,120 474,132 H430 "
              "C420,132 416,124 416,114 V60 "
              "M416,118 C416,140 398,142 386,136 H344 C338,136 336,128 336,122 C336,132 330,136 324,136 "
              "C318,136 316,128 316,122 C316,132 310,136 304,136 H262 "
              "C240,136 232,150 244,164 C256,178 222,192 196,182 C166,170 168,144 186,136 H130 "
              "C112,136 100,150 108,166 C118,184 76,188 64,162")
    dur = 6
    d.add(f'<path d="{stroke}" fill="none" stroke="{HOT}" stroke-width="7" stroke-linecap="round" pathLength="1" '
          f'stroke-dasharray="1" stroke-dashoffset="1" filter="url(#gl)">'
          f'<animate attributeName="stroke-dashoffset" values="1;0;0;1" keyTimes="0;0.4;0.92;1" dur="{dur}s" repeatCount="indefinite"/></path>')
    for x, y, t in [(466, 88, 2.4), (320, 106, 2.6), (334, 106, 2.6), (120, 112, 3.0)]:
        d.add(f'<circle cx="{x}" cy="{y}" r="5" fill="{V100}" opacity="0">{blink(t, dur * 0.92, dur)}</circle>')
    for k, (x0, x1) in enumerate([(486, 556), (404, 486), (294, 404), (174, 294), (56, 174)]):
        t = 3.0 + 0.25 * k
        d.add(f'<rect x="{x0}" y="40" width="{x1 - x0}" height="156" rx="6" fill="{HOT}" fill-opacity="0.05" stroke="{V300}" '
              f'stroke-dasharray="5 4" opacity="0">{blink(t, dur * 0.92, dur)}</rect>')
        d.text((x0 + x1) / 2, 30, f"c{5 - k}", "mono", 400, 11, V300, "middle", ' opacity="0"', blink(t, dur * 0.92, dur))


def il_fraud(d, W, H):
    pts = [(70, 60), (150, 34), (150, 104), (240, 60), (330, 92), (250, 140), (420, 46), (440, 128), (520, 82)]
    edges = [(0, 1), (0, 2), (1, 3), (2, 3), (3, 4), (2, 5), (5, 4), (4, 6), (4, 7), (6, 8), (7, 8)]
    for i, (a, b) in enumerate(edges):
        (x1, y1), (x2, y2) = pts[a], pts[b]
        d.add(f'<path id="t{i}" d="M{x1},{y1} L{x2},{y2}" stroke="{V400}" stroke-opacity="0.45" stroke-width="1.5"/>',
              f'<circle r="3" fill="{V100}"><animateMotion dur="{1.6 + (i % 3) * 0.5:.1f}s" repeatCount="indefinite" begin="-{i * 0.37:.2f}s"><mpath href="#t{i}"/></animateMotion></circle>')
    for k, (x, y) in enumerate(pts):
        bad = k == 4
        d.add(f'<circle cx="{x}" cy="{y}" r="{10 if bad else 7}" fill="{BG0}" stroke="{HOT if bad else V300}" stroke-width="2.5" filter="url(#gl)"/>')
    d.add(f'<circle cx="330" cy="92" r="10" fill="none" stroke="{HOT}"><animate attributeName="r" values="10;30" dur="1.8s" repeatCount="indefinite"/>'
          f'<animate attributeName="stroke-opacity" values="0.9;0" dur="1.8s" repeatCount="indefinite"/></circle>')
    d.text(352, 86, "anomaly 0.98", "mono", 700, 12, HOT)
    xs = list(range(40, 562, 18))
    ys = [190 - 8 * math.sin(i * 0.9) - 4 * math.cos(i * 2.3) for i in range(len(xs))]
    spike = 17
    ys[spike] = 158
    poly = " ".join(f"{x},{y:.1f}" for x, y in zip(xs, ys))
    d.add(f'<polyline points="{poly}" fill="none" stroke="{V400}" stroke-width="2" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1">'
          f'<animate attributeName="stroke-dashoffset" values="1;0;0" keyTimes="0;0.6;1" dur="5s" repeatCount="indefinite"/></polyline>',
          f'<circle cx="{xs[spike]}" cy="{ys[spike]}" r="5" fill="{HOT}" opacity="0">{blink(5 * 0.6 * spike / len(xs), 5, 5)}</circle>')


def il_drive(d, W, H):
    vx, vy = W / 2, 34
    d.add(f'<path d="M{vx - 14},{vy} L{vx + 14},{vy} L{vx + 190},{H} L{vx - 190},{H} Z" fill="#1A1D21"/>',
          f'<path d="M{vx - 14},{vy} L{vx - 190},{H} M{vx + 14},{vy} L{vx + 190},{H}" stroke="{V300}" stroke-width="3" stroke-opacity="0.8"/>')
    d.css.append(".lane{stroke-dasharray:14 16;animation:lane .6s linear infinite}@keyframes lane{to{stroke-dashoffset:-30}}")
    d.add(f'<path d="M{vx},{vy} L{vx},{H}" stroke="{HOT}" stroke-width="4" class="lane"/>')
    for k in range(5):
        y = 50 + k * 34
        d.add(f'<rect x="40" y="{y}" width="{20 + (k * 37) % 50}" height="22" fill="#2B2F35" opacity="0.8"/>',
              f'<rect x="{W - 90}" y="{y - 10}" width="{24 + (k * 23) % 40}" height="30" fill="#2B2F35" opacity="0.8"/>')
    d.add(f'<g><animateTransform attributeName="transform" type="translate" values="-10 0;10 0;-10 0" dur="3s" repeatCount="indefinite"/>'
          f'<rect x="{vx - 36}" y="{H - 64}" width="72" height="44" rx="10" fill="#383D45" stroke="{V200}" stroke-width="2"/>'
          f'<rect x="{vx - 26}" y="{H - 58}" width="52" height="16" rx="5" fill="{BG0}"/>'
          f'<rect x="{vx - 32}" y="{H - 34}" width="14" height="6" rx="3" fill="{HOT}" filter="url(#gl)"/>'
          f'<rect x="{vx + 18}" y="{H - 34}" width="14" height="6" rx="3" fill="{HOT}" filter="url(#gl)"/></g>')
    d.text(30, 30, "steer −0.12", "mono", 400, 12.5, V300)
    d.text(W - 30, 30, "ONNX · 30 FPS", "mono", 400, 12.5, V300, "end")


def il_pepper(d, W, H):
    cx, cy = 300, H / 2 + 6
    d.add(f'<rect x="{cx - 70}" y="{cy - 64}" width="140" height="116" rx="52" fill="{V100}" stroke="{V300}" stroke-width="3"/>',
          f'<rect x="{cx - 50}" y="{cy - 30}" width="100" height="44" rx="22" fill="{BG0}"/>')
    for ex in (cx - 22, cx + 22):
        d.add(f'<ellipse cx="{ex}" cy="{cy - 8}" rx="10" ry="10" fill="{HOT}" filter="url(#gl)">'
              f'<animate attributeName="ry" values="10;10;1;10;10" keyTimes="0;0.9;0.93;0.96;1" dur="4s" repeatCount="indefinite"/></ellipse>')
    d.add(f'<path d="M{cx - 70},{cy + 58} q70,30 140,0" fill="none" stroke="{V300}" stroke-width="3"/>')
    bx, by = 400, 40
    d.add(f'<rect x="{bx}" y="{by}" width="168" height="54" rx="14" fill="{HOT}" fill-opacity="0.12" stroke="{HOT}" stroke-opacity="0.7"/>',
          f'<path d="M{bx + 10},{by + 54} l-14,16 l30,-16" fill="{HOT}" fill-opacity="0.12" stroke="{HOT}" stroke-opacity="0.7"/>')
    for k in range(3):
        d.add(f'<circle cx="{bx + 64 + k * 20}" cy="{by + 27}" r="5" fill="{V200}">'
              f'<animate attributeName="opacity" values="0.2;1;0.2" dur="1.2s" begin="{k * 0.2}s" repeatCount="indefinite"/></circle>')
    d.text(bx + 84, by + 82, "« Bonjour ! »", "mono", 400, 12.5, V300, "middle")
    d.add(f'<rect x="58" y="52" width="92" height="118" rx="6" fill="#383D45" stroke="{V300}" stroke-width="2"/>',
          f'<path d="M70,52 V170" stroke="{V300}" stroke-opacity="0.6"/>')
    for k, (x, y) in enumerate([(92, 80), (126, 92), (104, 120), (132, 140), (88, 150), (118, 66)]):
        d.add(f'<circle cx="{x}" cy="{y}" r="7" fill="none" stroke="{HOT}" stroke-width="1.5" opacity="0">{blink(0.3 * k, 2.6, 3.4)}</circle>')
    d.text(104, H - 14, "SIFT match", "mono", 400, 12, MUTED, "middle")


def il_pacr(d, W, H):
    cell = 24
    obstacles = [(5, 2), (5, 3), (5, 4), (6, 4), (11, 1), (11, 2), (11, 3), (16, 4), (16, 5), (17, 5), (9, 6), (14, 2)]
    for gx in range(1, 24):
        d.add(f'<path d="M{gx * cell},12 V{H - 12}" stroke="{V400}" stroke-opacity="0.08"/>')
    for gy in range(1, 9):
        d.add(f'<path d="M12,{gy * cell} H{W - 12}" stroke="{V400}" stroke-opacity="0.08"/>')
    for gx, gy in obstacles:
        d.add(f'<rect x="{gx * cell + 2}" y="{gy * cell + 2}" width="{cell - 4}" height="{cell - 4}" rx="4" fill="#444A53"/>')
    path = "M60,180 L108,180 L132,156 L204,156 L228,132 L228,84 L252,60 L300,60 L324,84 L372,108 L420,108 L444,84 L492,60 L540,36"
    dur = 5
    d.add(f'<path id="route" d="{path}" fill="none" stroke="{HOT}" stroke-width="3" stroke-linejoin="round" pathLength="1" '
          f'stroke-dasharray="1" stroke-dashoffset="1"><animate attributeName="stroke-dashoffset" values="1;0;0;1" keyTimes="0;0.6;0.9;1" dur="{dur}s" repeatCount="indefinite"/></path>',
          f'<circle r="9" fill="{BG0}" stroke="{V100}" stroke-width="3" filter="url(#gl)">'
          f'<animateMotion dur="{dur}s" repeatCount="indefinite" keyPoints="0;1;1;0" keyTimes="0;0.6;0.9;1" calcMode="linear"><mpath href="#route"/></animateMotion></circle>',
          f'<circle cx="60" cy="180" r="6" fill="{V300}"/>',
          f'<path d="M540,36 l0,-22 l16,7 l-16,7" fill="{HOT}" stroke="{HOT}"/>')
    d.text(60, 206, "start", "mono", 400, 12, MUTED, "middle")
    d.text(522, 62, "goal", "mono", 400, 12, HOT, "end")


def il_slam(d, W, H):
    cx, cy, dur = 300, H / 2, 4.0
    room = [(170, 30), (430, 30), (430, 80), (470, 80), (470, 190), (130, 190), (130, 70), (170, 70)]
    pts = []
    for (x1, y1), (x2, y2) in zip(room, room[1:] + room[:1]):
        n = max(int(math.hypot(x2 - x1, y2 - y1) // 12), 1)
        pts += [(x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n) for k in range(n)]
    for x, y in pts:
        ang = (math.degrees(math.atan2(y - cy, x - cx)) + 360) % 360
        t = dur * ang / 360
        d.add(f'<rect x="{x - 2:.1f}" y="{y - 2:.1f}" width="4" height="4" fill="{HOT}" opacity="0.25">{blink(t, t + 1.2, dur, 0.25, 1)}</rect>')
    d.defs.append(f'<linearGradient id="beam" x1="0" x2="1"><stop offset="0" stop-color="{V200}" stop-opacity="0.9"/>'
                  f'<stop offset="1" stop-color="{V200}" stop-opacity="0"/></linearGradient>')
    d.add(f'<g><animateTransform attributeName="transform" type="rotate" from="0 {cx} {cy}" to="360 {cx} {cy}" dur="{dur}s" repeatCount="indefinite"/>'
          f'<path d="M{cx},{cy} L{cx + 190},{cy - 22} L{cx + 190},{cy + 22} Z" fill="url(#beam)" opacity="0.3"/>'
          f'<path d="M{cx},{cy} L{cx + 190},{cy}" stroke="url(#beam)" stroke-width="2"/></g>',
          f'<circle cx="{cx}" cy="{cy}" r="12" fill="{HOT}" stroke="#fff" stroke-width="2" filter="url(#gl)"/>')
    for mx, my in [(150, 120), (450, 140)]:
        d.add(f'<rect x="{mx - 9}" y="{my - 9}" width="18" height="18" fill="{V100}"/>'
              f'<rect x="{mx - 5}" y="{my - 5}" width="5" height="5" fill="{BG0}"/><rect x="{mx + 1}" y="{my}" width="4" height="5" fill="{BG0}"/>')
    d.text(30, 30, "ArUco + Kalman", "mono", 400, 12, MUTED)


def tiles_row(d, W, H, entries, size=64):
    """A row of floating icon tiles: (kind, value) where kind is 'icon' or 'text'."""
    gap = 18
    total = len(entries) * size + (len(entries) - 1) * gap
    x0, y = (W - total) / 2, H / 2 - size / 2 - 6
    d.add(f'<ellipse cx="{W / 2}" cy="{H - 26}" rx="{total / 2 + 20}" ry="10" fill="{HOT}" opacity="0.14" filter="url(#gl2)"/>')
    for k, (kind, val) in enumerate(entries):
        x = x0 + k * (size + gap)
        style = f' class="bob" style="animation-delay:-{k * 0.35:.2f}s"'
        if kind == "icon":
            pad = 0 if val.startswith("sk-") else 16
            inner = ("" if not pad else
                     f'<rect x="{x:.1f}" y="{y:.1f}" width="{size}" height="{size}" rx="{size * 0.22:.1f}" fill="{TILE}" stroke="{LINE}"/>')
            d.add(f'<g{style}>{inner}<image href="{icon_uri(val, HOT)}" x="{x + pad:.1f}" y="{y + pad:.1f}" '
                  f'width="{size - 2 * pad}" height="{size - 2 * pad}"/></g>')
        else:
            fs = fit(val, size - 10, "mono", 700, 15)
            d.use(val, "mono", 700)
            d.add(f'<g{style}><rect x="{x:.1f}" y="{y:.1f}" width="{size}" height="{size}" rx="{size * 0.22:.1f}" fill="{TILE}" stroke="{HOT}" stroke-opacity="0.5"/>'
                  f'<text x="{x + size / 2:.1f}" y="{y + size / 2 + fs * 0.35:.1f}" text-anchor="middle" font-family="{FAMILY["mono"]}" '
                  f'font-weight="700" font-size="{fs}" fill="{V200}">{e(val)}</text></g>')


# --------------------------------------------------------------------------- content
RESEARCH = [
    ("card-pgxlod", "teal", il_pgxlod, "Entity Alignment on PGxLOD", "2026 · Inria / LORIA",
     "A benchmark of 8 entity-alignment models and a structure-only baseline on a pharmacogenomic "
     "knowledge graph: 6 tasks, leak-free splits, filtered and multi-reference ranking, decision F1.",
     ["PyTorch", "Knowledge Graphs", "GNNs"], ("Open source", "live")),
    ("card-nexus", "sky", il_nexus, "EntityAlignment-Nexus", "Reproducibility · DBP15K",
     "Nine entity-alignment models rebuilt from scratch in PyTorch, with one data layer, one trainer "
     "and paper-versus-repo results for every model.",
     ["PyTorch", "Entity Alignment"], ("Open source", "live")),
    ("card-rsna", "rose", il_rsna, "Intracranial Hemorrhage Detection", "2024–25 · RSNA challenge",
     "Transformers and explainable AI trained on about one million CT scans to detect and classify "
     "intracranial hemorrhages.",
     ["ViT", "Medical imaging", "XAI"], ("Paper in progress", None)),
    ("card-nadi", "amber", il_nadi, "Arabic Dialect Identification", "2024 · NADI shared task, ArabicNLP",
     "A multi-classifier system that identifies 21 Arabic dialects, ranked 3rd among international "
     "research teams.",
     ["NLP", "Classification"], ("3rd place", "award")),
    ("card-pais", "green", il_pais, "Arabic Handwriting Recognition", "2025 · IEEE PAIS",
     "Transformers and CNNs with a new segmentation method and data augmentation for handwritten "
     "Arabic characters.",
     ["Transformers", "CNNs", "OCR"], ("Published", "live")),
    ("card-fraud", "orange", il_fraud, "Banking Fraud Detection", "2025 · BEYN e-banking",
     "GNNs, autoencoders, GANs and sequence models that flag anomalies in transaction time series.",
     ["GNNs", "Autoencoders", "GANs"], ("Industry", None)),
]

PROJECTS = [
    ("card-drive", "blue", il_drive, "Autonomous Driving, End to End", "ROS2 · PyTorch · ONNX",
     "Behavioral cloning with CNNs and ViTs, from MPC and PID data collection to a real-time "
     "autopilot with a safety switch.",
     ["ROS2", "ViT", "ONNX"], ("Open source", "live")),
    ("card-pepper", "pink", il_pepper, "Pepper Library Assistant", "ROS2 · SoftBank Pepper",
     "A library assistant robot with French voice interaction, book cover recognition, A* "
     "navigation and Visual SLAM.",
     ["ROS2", "SIFT", "SLAM"], ("Open source", "live")),
    ("card-pacr", "lime", il_pacr, "PACR Solutions", "ROS2 · planning",
     "Path planning with Pure Pursuit and DWA local planners, and task planning as an MDP solved "
     "by value iteration.",
     ["A*", "DWA", "MDP"], ("Open source", "live")),
    ("card-slam", "cyan", il_slam, "Robot Cartographe SLAM", "ESP32 · Python · OpenCV",
     "A hands-on course: a robot maps a room with a laser, ArUco markers and a Kalman filter, then "
     "navigates it alone, in 14 labs.",
     ["ESP32", "OpenCV", "Kalman"], ("Open source", "live")),
]

STACK = [
    ("stack-llm", "lavender", [("icon", "si-huggingface"), ("icon", "si-meta"), ("text", "Qwen"), ("text", "vLLM"), ("text", "RAG")],
     "LLMs & GenAI", ["RAG", "GraphRAG", "Agentic AI", "Transformers", "Hugging Face", "Qwen", "Llama", "Mistral", "LoRA / PEFT", "vLLM"]),
    ("stack-kg", "teal", [("icon", "si-semanticweb"), ("text", "RDF"), ("text", "OWL"), ("text", "SPARQL"), ("text", "KG")],
     "Knowledge Graphs", ["RDF / OWL", "SPARQL", "Linked Open Data", "Entity Alignment", "Ontology Matching", "KG Embeddings"]),
    ("stack-dl", "orange", [("icon", "sk-python"), ("icon", "sk-pytorch"), ("icon", "sk-tensorflow"), ("icon", "sk-sklearn"), ("icon", "si-onnx")],
     "Deep Learning", ["PyTorch", "TensorFlow / Keras", "R-GCN · GCN · GAT", "CNN · ViT", "GANs", "Autoencoders", "scikit-learn", "ONNX"]),
    ("stack-eng", "sky", [("icon", "sk-ros"), ("icon", "sk-opencv"), ("icon", "sk-docker"), ("icon", "sk-linux"), ("icon", "sk-githubactions")],
     "Robotics & Engineering", ["ROS2", "Visual SLAM", "OpenCV", "Docker", "Linux", "GitHub Actions", "GitLab CI", "C++", "Grid'5000"]),
]


# --------------------------------------------------------------------------- closing waves
def footer_wave():
    """Three orange waves rolling under the closing GIF, on a transparent background."""
    W, H = 1200, 126

    def wave(amp, length, base):
        path = f"M0 {base}"
        for i in range(2 * (int(2 * W / length) + 2)):
            x = i * length / 2
            path += f" Q{x + length / 4:.1f} {base + (amp if i % 2 == 0 else -amp)} {x + length / 2:.1f} {base}"
        return path + f" V{H} H0 Z"

    d = Doc(W, H, "Orange waves")
    for amp, length, base, dur, color in [(16, 400, 30, 11, "#FDBA74"), (12, 300, 52, 8, "#FB923C"), (10, 240, 76, 6, "#EA580C")]:
        d.add(f'<path d="{wave(amp, length, base)}" fill="{color}">'
              f'<animateTransform attributeName="transform" type="translate" values="0 0;-{length} 0" dur="{dur}s" repeatCount="indefinite"/></path>')
    d.write("footer-wave.svg")


if __name__ == "__main__":
    footer_wave()
    for key, label in [("about", "About Me"), ("research", "Research"), ("stack", "Tech Stack"),
                       ("projects", "Featured Projects"), ("stats", "GitHub Stats")]:
        title(key, label)
    whoami()
    for name, acc, il, t, meta, desc, tags, status in RESEARCH + PROJECTS:
        set_accent(ACCENTS[acc])
        card(name, 470, f"{t}. {meta}. {desc}", il, t, meta, desc, tags, status)
    for name, acc, entries, t, items in STACK:
        set_accent(ACCENTS[acc])
        card(name, 350, f"{t}: {', '.join(items)}", lambda d, W, H, en=entries: tiles_row(d, W, H, en), t,
             items=items, design_h=None)
