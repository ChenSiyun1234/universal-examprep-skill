#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cheatsheet renderer (v4-P5) — cheatsheet.md → print-optimized HTML → PDF, pure stdlib.

The compiler (exam-cheatsheet) writes cheatsheet.md; THIS tool renders the printable artifact:
dense multi-column layout, small tunable font, and — critically for printers that eat edges —
`@page` margins that never drop below 12 mm. The PDF step drives a LOCAL headless Edge/Chrome
(`--headless --print-to-pdf`, zero new dependencies); when no browser is found it degrades to
HTML + a one-line print instruction (exit 3, same degradation contract as retrieve.py).

Page-count fitting: a chars-per-page heuristic picks the starting font size for the student's
--pages target, then (browser path only) the ACTUAL page count of the produced PDF is read back
(chromium writes one /Type /Page object per page) and the font is nudged until the sheet fits
exactly — as crowded as possible without overflowing. The agent may additionally do a VISUAL
whitespace check (render + screenshot) per the skill contract; this tool owns the deterministic
part. Exit: 0 ok · 2 usage · 3 no-browser degradation · 1 render failure.

    python scripts/cheatsheet_render.py --workspace <ws> --pages 2
    python scripts/cheatsheet_render.py --workspace <ws> --pages 1 --font-size 7 --html-only
"""
import argparse
import html as html_mod
import os
import re
import shutil
import subprocess
import sys

for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8")
    except Exception:
        pass

MIN_MARGIN_MM = 12          # printers eat edges — hard floor, do not lower
FONT_MIN, FONT_MAX = 6.0, 12.0
CHARS_PER_PAGE_9PT = 5200   # A4, 2 columns, 9pt, line-height 1.25 — measured heuristic seed
MD_NAME = "cheatsheet.md"


def _die(msg, code=2):
    sys.stderr.write("cheatsheet_render: " + msg + "\n")
    raise SystemExit(code)


# ---------------- tiny md subset → html (the compiler controls the input dialect) ----------------

_INLINE = [
    (re.compile(r"\*\*([^*]+)\*\*"), r"<strong>\1</strong>"),
    (re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)"), r"<em>\1</em>"),
    (re.compile(r"`([^`]+)`"), r"<code>\1</code>"),
    # 图片必须先于普通链接处理（Codex r2）：否则 ![题面图](references/assets/….png) 会被下一条
    # 链接压平规则吃掉，打印版把依赖图的例题图丢了——恰恰违反小抄「图必须真展示」契约。
    (re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)"),
     r'<img src="\2" alt="\1" style="max-width:100%;max-height:60mm">'),
    (re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)"), r'<span class="lnk">\1</span>'),  # print: no live links
]


def _inline(s):
    s = html_mod.escape(s, quote=False)
    for pat, rep in _INLINE:
        s = pat.sub(rep, s)
    return s


def md_to_html_body(md):
    """Headings/lists/tables/hr/paragraphs — the documented subset the compiler emits."""
    out, in_ul, in_ol, in_table = [], False, False, False

    def close_lists():
        nonlocal in_ul, in_ol, in_table
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False
        if in_table:
            out.append("</table>")
            in_table = False

    for line in (md or "").splitlines():
        s = line.rstrip()
        if not s.strip():
            close_lists()
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            close_lists()
            n = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (n, _inline(m.group(2)), n))
            continue
        if re.match(r"^\s*(?:---+|\*\*\*+)\s*$", s):
            close_lists()
            out.append("<hr/>")
            continue
        if re.match(r"^\s*\|[\s:\-|]+\|?\s*$", s):
            continue                                   # table separator row
        if s.lstrip().startswith("|"):
            cells = [c.strip() for c in s.strip().strip("|").split("|")]
            if not in_table:
                close_lists()
                out.append('<table>')
                in_table = True
                out.append("<tr>" + "".join("<th>%s</th>" % _inline(c) for c in cells) + "</tr>")
            else:
                out.append("<tr>" + "".join("<td>%s</td>" % _inline(c) for c in cells) + "</tr>")
            continue
        m = re.match(r"^\s*[-*]\s+(.*)$", s)
        if m:
            if in_table or in_ol:
                close_lists()
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append("<li>%s</li>" % _inline(m.group(1)))
            continue
        m = re.match(r"^\s*\d+[.)]\s+(.*)$", s)
        if m:
            if in_table or in_ul:
                close_lists()
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append("<li>%s</li>" % _inline(m.group(1)))
            continue
        close_lists()
        out.append("<p>%s</p>" % _inline(s))
    close_lists()
    return "\n".join(out)


# ---------------- layout math ----------------

def chars_per_page(font_pt, columns):
    """Heuristic capacity of one A4 page. Area scales ~1/font² ; 3 columns pack ~8% denser."""
    base = CHARS_PER_PAGE_9PT * (9.0 / font_pt) ** 2
    return base * (1.08 if columns >= 3 else 1.0)


def pick_font(total_chars, pages):
    """Smallest-work font that fits `pages`: prefer the LARGEST font that still fits (crowded
    but readable); clamp to [FONT_MIN, FONT_MAX]. Returns (font_pt, columns)."""
    for font in [x / 2.0 for x in range(int(FONT_MAX * 2), int(FONT_MIN * 2) - 1, -1)]:
        cols = 3 if font < 7.5 else 2
        if total_chars <= chars_per_page(font, cols) * pages:
            return font, cols
    return FONT_MIN, 3


def render_html(md, font_pt, columns, margin_mm=MIN_MARGIN_MM, title="Cheatsheet"):
    if margin_mm < MIN_MARGIN_MM:
        margin_mm = MIN_MARGIN_MM                      # hard floor — printers eat edges
    body = md_to_html_body(md)
    return """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>%s</title>
<style>
@page { size: A4; margin: %dmm; }
html, body { margin: 0; padding: 0; }
body { font: %.1fpt/%.2f "Segoe UI", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
       column-count: %d; column-gap: 4mm; column-fill: auto; }
h1 { font-size: %.1fpt; margin: 0 0 2pt; column-span: all; }
h2 { font-size: %.1fpt; margin: 3pt 0 1pt; border-bottom: .5pt solid #999; break-after: avoid; }
h3, h4 { font-size: %.1fpt; margin: 2pt 0 1pt; break-after: avoid; }
p, li { margin: 0 0 1pt; }
ul, ol { margin: 0 0 1pt; padding-left: 9pt; }
table { border-collapse: collapse; width: 100%%; margin: 1pt 0; }
th, td { border: .5pt solid #aaa; padding: .5pt 2pt; text-align: left; }
code { font-family: Consolas, monospace; font-size: 92%%; background: #f2f2f2; padding: 0 1pt; }
hr { border: none; border-top: .5pt solid #bbb; margin: 2pt 0; }
section, .block { break-inside: avoid; }
</style></head><body>
%s
</body></html>
""" % (html_mod.escape(title), margin_mm, font_pt, 1.22, columns,
       font_pt * 1.5, font_pt * 1.2, font_pt * 1.05, body)


# ---------------- pdf via local headless browser ----------------

def find_browser():
    if os.environ.get("EXAMPREP_NO_BROWSER") == "1":   # test hook: force the degradation path
        return None
    for name in ("msedge", "chrome", "chromium", "google-chrome"):
        p = shutil.which(name)
        if p:
            return p
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        if os.path.isfile(p):
            return p
    return None


def print_to_pdf(browser, html_path, pdf_path, timeout=120):
    url = "file:///" + os.path.abspath(html_path).replace("\\", "/")
    args = [browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
            "--print-to-pdf=%s" % os.path.abspath(pdf_path), url]
    r = subprocess.run(args, capture_output=True, timeout=timeout)
    if r.returncode != 0 and not os.path.isfile(pdf_path):
        _die("无头浏览器打印失败（%s）：%s" % (os.path.basename(browser),
             (r.stderr or b"")[:300].decode("utf-8", "replace")), 1)


def pdf_page_count(pdf_path):
    """Chromium PDFs carry one '/Type /Page' object per page (plus one '/Type /Pages' tree node)."""
    with open(pdf_path, "rb") as f:
        data = f.read()
    return len(re.findall(rb"/Type\s*/Page\b(?!s)", data))


# ---------------- main ----------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="cheatsheet.md → dense printable HTML/PDF "
                                             "(stdlib; local headless Edge/Chrome for PDF)")
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--pages", type=int, required=True, help="target page count (user-specified)")
    ap.add_argument("--font-size", type=float, default=0, help="override the fitted font size")
    ap.add_argument("--margin-mm", type=int, default=MIN_MARGIN_MM,
                    help="page margin, floored at %dmm (printer edge-eating)" % MIN_MARGIN_MM)
    ap.add_argument("--html-only", action="store_true")
    args = ap.parse_args(argv)
    if args.pages <= 0:
        _die("--pages 必须为正整数")
    if args.font_size and not (FONT_MIN <= args.font_size <= FONT_MAX):
        _die("--font-size 须在 %.1f–%.1f pt 之间" % (FONT_MIN, FONT_MAX))

    ws = os.path.abspath(args.workspace)
    md_path = os.path.join(ws, MD_NAME)
    if not os.path.isfile(md_path):
        _die("找不到 %s——先让 exam-cheatsheet 编译出小抄，再来渲染" % MD_NAME)
    with open(md_path, "r", encoding="utf-8") as f:
        md = f.read()
    total = len(re.sub(r"\s+", "", md))

    if args.font_size:
        font, cols = args.font_size, (3 if args.font_size < 7.5 else 2)
    else:
        font, cols = pick_font(total, args.pages)
    html_path = os.path.join(ws, "cheatsheet.html")
    pdf_path = os.path.join(ws, "cheatsheet.pdf")

    browser = None if args.html_only else find_browser()
    for attempt in range(4):                            # fit loop: nudge font vs actual pages
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(render_html(md, font, cols, args.margin_mm))
        if args.html_only or not browser:
            break
        print_to_pdf(browser, html_path, pdf_path)
        got = pdf_page_count(pdf_path)
        if got == args.pages:
            break
        if got > args.pages and font > FONT_MIN:        # overflow → shrink
            font = max(FONT_MIN, font - 0.5)
            cols = 3 if font < 7.5 else 2
        elif got < args.pages and font < FONT_MAX:      # trailing whitespace → grow to refill
            font = min(FONT_MAX, font + 0.5)
            cols = 3 if font < 7.5 else 2
        else:
            break

    print("[+] cheatsheet.html：字号 %.1fpt · %d 栏 · 边距 %dmm（≥%dmm 打印安全）"
          % (font, cols, max(args.margin_mm, MIN_MARGIN_MM), MIN_MARGIN_MM))
    if args.html_only:
        return 0
    if not browser:
        sys.stderr.write("cheatsheet_render: no_browser: 本机未找到 Edge/Chrome——已生成 "
                         "cheatsheet.html，请打开后 Ctrl+P 打印为 PDF（边距选默认、勾选背景图形）\n")
        raise SystemExit(3)
    got = pdf_page_count(pdf_path)
    print("[+] cheatsheet.pdf：%d 页（目标 %d 页%s）"
          % (got, args.pages, "" if got == args.pages else "——已尽力拟合，可用 --font-size 微调"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
