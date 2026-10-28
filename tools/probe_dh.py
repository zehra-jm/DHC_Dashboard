"""One-off: ask the discounthotels.pk API for every hotel's rooms for 1 and 2 adults. Output goes to probe/."""
import json, urllib.request
from datetime import date, timedelta
from pathlib import Path

API = "https://api.discounthotels.pk/api"
OUT = Path("probe"); OUT.mkdir(exist_ok=True)
d1 = date.today() + timedelta(days=1); d2 = d1 + timedelta(days=1)
def call(path, body=None):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=30))
hotels = call("/hotels")["hotels"]
out = {"hotels": hotels, "avail": {}}
for h in hotels:
    for a in (1, 2):
        out["avail"][f'{h["id"]}-{a}'] = call("/availability", {"hotelId": h["id"], "dateFrom": d1.isoformat(), "dateTo": d2.isoformat(), "adults": a, "children": 0})
(OUT / "api.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
