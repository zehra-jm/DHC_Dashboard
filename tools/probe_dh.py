"""One-off: open discounthotels.pk in a browser and save what it serves (pages, links, JSON calls)
so the collector can be written against the real site. Output goes to probe/."""
import json, re, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("probe"); OUT.mkdir(exist_ok=True)
calls = []
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1366, "height": 900})
    def on_resp(r):
        ct = r.headers.get("content-type", "")
        if "json" in ct or r.request.resource_type in ("xhr", "fetch"):
            try: body = r.text()[:200000]
            except Exception: body = None
            calls.append({"url": r.url, "status": r.status, "ct": ct, "method": r.request.method, "post": r.request.post_data, "body": body})
    pg.on("response", on_resp)
    seen, queue = set(), ["https://discounthotels.pk/"]
    while queue and len(seen) < 25:
        u = queue.pop(0)
        if u in seen: continue
        seen.add(u)
        try:
            pg.goto(u, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print("fail", u, e); continue
        pg.wait_for_timeout(2500)
        name = re.sub(r"[^a-z0-9]+", "_", u.split("//", 1)[1].lower()).strip("_")[:80] or "home"
        (OUT / f"{name}.html").write_text(pg.content(), encoding="utf-8")
        (OUT / f"{name}.txt").write_text(pg.inner_text("body"), encoding="utf-8")
        for h in pg.eval_on_selector_all("a[href]", "els => els.map(e => e.href)"):
            h = h.split("#")[0]
            if "discounthotels.pk" in h and h not in seen and not re.search(r"\.(jpg|png|pdf|webp)$", h) and any(k in h.lower() for k in ("hotel", "room", "karachi", "search", "stay", "property")):
                queue.append(h)
        print("ok", u, pg.url)
    b.close()
(OUT / "calls.json").write_text(json.dumps(calls, indent=1, ensure_ascii=False), encoding="utf-8")
(OUT / "pages.txt").write_text("\n".join(sorted(seen)))
