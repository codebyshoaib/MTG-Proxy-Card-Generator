#!/usr/bin/env python3
"""Turn the client brief into a PDF.

Small hand-rolled markdown subset (headings, paragraphs, bullets, numbered lists, tables) wrapped
in print CSS, then rendered by headless Chrome. No pandoc, no LaTeX, nothing to install.

Run:  python3 make_pdf.py BRIEF-FOR-CLIENT.md "MTG Proxy Card Generator - Gemini test findings"
"""
import html, pathlib, re, subprocess, sys, tempfile

CSS = """
@page { size: A4; margin: 20mm 18mm 18mm 18mm; }
body { font: 11pt/1.55 Georgia, 'Times New Roman', serif; color: #1c1c1c; }
h1 { font: 600 20pt/1.3 Georgia, serif; margin: 0 0 4pt; }
h2 { font: 600 13.5pt/1.35 Georgia, serif; margin: 20pt 0 6pt;
     border-bottom: 1px solid #d8d8d8; padding-bottom: 3pt; page-break-after: avoid; }
h3 { font: 600 11.5pt/1.35 Georgia, serif; margin: 14pt 0 4pt; page-break-after: avoid; }
p { margin: 0 0 8pt; }
ul, ol { margin: 0 0 8pt; padding-left: 18pt; }
li { margin-bottom: 4pt; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0 12pt;
        font-size: 10pt; page-break-inside: avoid; }
th { text-align: left; background: #f2f2f2; font-weight: 600; }
th, td { border: 1px solid #cfcfcf; padding: 5pt 7pt; }
td:nth-child(n+2), th:nth-child(n+2) { text-align: right; white-space: nowrap; }
.date { color: #666; font-size: 10pt; margin-bottom: 14pt; }
"""


def inline(s):
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"(?<![\w`])\*(?!\s)(.+?)(?<!\s)\*", r"<em>\1</em>", s)


def convert(md):
    out, i = [], 0
    lines = md.split("\n")
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1
            continue
        if ln.startswith("|"):                                   # table
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            rows = [r for r in rows if not all(set(c) <= set("-: ") for c in r)]
            out.append("<table><tr>" + "".join(f"<th>{inline(c)}</th>" for c in rows[0])
                       + "</tr>")
            for r in rows[1:]:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            out.append("</table>")
            continue
        if m := re.match(r"(#{1,3}) (.+)", ln):
            out.append(f"<h{len(m[1])}>{inline(m[2])}</h{len(m[1])}>")
            i += 1
            continue
        if re.match(r"[*\-] |^\d+\. ", ln):                        # list
            tag = "ul" if ln[0] in "*-" else "ol"
            items, cur = [], ""
            while i < len(lines) and lines[i].strip():
                if re.match(r"[*\-] |^\d+\. ", lines[i]):
                    if cur:
                        items.append(cur)
                    cur = re.sub(r"^([*\-] |\d+\. )", "", lines[i]).strip()
                else:
                    cur += " " + lines[i].strip()
                i += 1
            if cur:
                items.append(cur)
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
            continue
        para = []                                                  # paragraph
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(("#", "|", "* ", "- ")):
            para.append(lines[i].strip())
            i += 1
        text = " ".join(para)
        cls = ' class="date"' if re.fullmatch(r"\d+ \w+ \d{4}", text) else ""
        out.append(f"<p{cls}>{inline(text)}</p>")
    return "\n".join(out)


if __name__ == "__main__":
    src = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "BRIEF-FOR-CLIENT.md")
    title = sys.argv[2] if len(sys.argv) > 2 else src.stem
    body = convert(src.read_text())
    page = (f"<!doctype html><meta charset='utf-8'><title>{html.escape(title)}</title>"
            f"<style>{CSS}</style>{body}")
    tmp = pathlib.Path(tempfile.mkdtemp()) / "brief.html"
    tmp.write_text(page)
    pdf = src.with_suffix(".pdf")
    subprocess.run(["/opt/google/chrome/chrome", "--headless=new", "--disable-gpu",
                    f"--user-data-dir={tmp.parent}/prof", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf}", tmp.as_uri()],
                   check=True, capture_output=True, timeout=180)
    print(f"{pdf}  {pdf.stat().st_size / 1024:.0f} KB")
