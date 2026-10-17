"""Bundle docs/ and its data into one self-contained HTML file (for sharing a preview)."""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "docs"
summary = json.loads((D / "data/summary.json").read_text(encoding="utf-8"))
hotels = {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in (D / "data/hotels").glob("*.json")}
contracts = json.loads((D / "data/contracts.json").read_text(encoding="utf-8")) if (D / "data/contracts.json").exists() else []
rates = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")) if len(sys.argv) > 2 else None
data = json.dumps({"summary": summary, "hotels": hotels, "contracts": contracts, "rates": rates}, ensure_ascii=False).replace("</", "<\\/")
html = (D / "index.html").read_text(encoding="utf-8")
body = re.search(r"<body>(.*)</body>", html, re.S).group(1)
fonts = re.search(r'<link rel="stylesheet" href="https://fonts[^>]+>', html).group(0)
body = body.replace('<script src="app.js"></script>',
    "<script>window.RATE_DATA=" + data + "</script>\n<script>" + (D / "app.js").read_text(encoding="utf-8") + "</script>")
out = ('<title>Karachi Rate Board</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n' + fonts +
       "\n<style>\n" + (D / "app.css").read_text(encoding="utf-8") + "</style>\n" + body)
Path(sys.argv[1]).write_text(out, encoding="utf-8")
print("wrote", sys.argv[1], len(out) // 1024, "KB")
