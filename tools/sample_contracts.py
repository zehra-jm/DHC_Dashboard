"""Preview helper: copy data/sample/ to OUT_DIR and add made-up Booking.com rooms for the
hotels in data/contract-hotels.json, priced around the private rate sheet so the comparison
view has something to show. OUT_DIR must be outside the repository: the result is derived
from the private rates.

Usage: python tools/sample_contracts.py PRIVATE_RATES.json OUT_DIR
       SAMPLE_DIR=OUT_DIR python collector/build.py
"""
import json
import random
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
rates = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
out = Path(sys.argv[2])
contracts = json.loads((ROOT / "data/contract-hotels.json").read_text(encoding="utf-8"))["hotels"]
if out.exists():
    shutil.rmtree(out)
shutil.copytree(ROOT / "data/sample", out)

rnd = random.Random(11)
level = {c["id"]: rnd.uniform(0.8, 1.45) for c in contracts}


def booking_name(letter_name):
    n = re.sub(r"\(.*?\)", "", letter_name).replace("Floor", "Room").strip()
    return n if re.search(r"room|suite", n, re.I) else n + " Room"


for f in sorted(out.glob("*/*.json")):
    snap = json.loads(f.read_text(encoding="utf-8"))
    for c in contracts:
        if rnd.random() < 0.04:
            level[c["id"]] *= rnd.choice([0.93, 0.96, 1.05, 1.09])
        r = rates["hotels"][c["id"]]
        rooms = []
        for room in c["rooms"]:
            v = r["rooms"][room["id"]]
            dbl = v["double"] or v["single"] + (r["extra_person"] or 0)
            gross = dbl if r["tax_included"] else dbl * 1.15
            total = int(round(gross * level[c["id"]] * rnd.uniform(0.97, 1.03), -2))
            rooms.append({"name": booking_name(room["name"]), "meal": "breakfast", "price": int(round(total / 1.15, -2)),
                          "total": total, "free_cancel": True})
            rooms.append({"name": booking_name(room["name"]), "meal": "room only", "price": int(round(total * 0.9 / 1.15, -2)),
                          "total": int(round(total * 0.9, -2)), "free_cancel": False})
        rooms.append({"name": "Budget Single Room", "meal": "room only", "price": 9000, "total": 10400, "free_cancel": False})
        rooms.sort(key=lambda x: x["price"])
        h = next((h for h in snap["hotels"] if any(k in h["name"].lower() for k in c["name_keys"])), None)
        if h is None:
            h = {"id": c["id"], "name": c["name"], "stars": None, "area": "", "score": None,
                 "url": c["booking_url"] or "https://www.booking.com/", "room_hint": None}
            snap["hotels"].append(h)
        h.update(contract=c["id"], rooms=rooms, price=rooms[0]["price"], room_hint=rooms[0]["name"])
    snap["hotels"].sort(key=lambda h: h["name"])
    f.write_text(json.dumps(snap, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("wrote", out)
