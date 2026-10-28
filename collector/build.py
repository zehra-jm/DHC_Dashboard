"""Turn the saved snapshots into the small JSON files the dashboard reads.

  docs/data/summary.json        every hotel with its current rate, changes and 30-day trend,
                                plus the feed of price changes over the last 7 days
  docs/data/hotels/<id>.json    one hotel's rooms with their changes and trends

Comparisons use the snapshot nearest to 1 day, 7 days and 30 days before the latest one.
Raw snapshots older than KEEP_DAYS are folded into data/archive/YYYY-MM.json (one closing
rate per hotel and room per day) and deleted, so the repository stays small.

If data/snapshots/ is empty the sample data in data/sample/ is used and the dashboard says so.
"""
import json
import os
import shutil
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPS = ROOT / "data" / "snapshots"
SAMPLE = Path(os.environ.get("SAMPLE_DIR") or ROOT / "data" / "sample")
ARCHIVE = ROOT / "data" / "archive"
STATUS = ROOT / "data" / "status.json"
CONTRACTS = ROOT / "data" / "contract-hotels.json"
OUT = ROOT / "docs" / "data"
KEEP_DAYS = 45
FEED_DAYS = 7
TAX = 0.15  # Sindh sales tax on hotel rooms
MIN_MOVE = 0.005  # ignore moves under 0.5% (rounding, currency conversion noise)
WINDOWS = {"d1": (timedelta(days=1), timedelta(hours=8)),
           "d7": (timedelta(days=7), timedelta(days=1)),
           "d30": (timedelta(days=30), timedelta(days=3))}


def load(folder):
    snaps = []
    for f in sorted(folder.glob("*/*.json")):
        s = json.loads(f.read_text(encoding="utf-8"))
        if "contracts" in s:  # only hotels with a DHC rate letter are shown
            s["hotels"] = [h for h in s["hotels"] if h.get("contract")]
        for h in s["hotels"]:  # every rate on the dashboard is before tax
            for r in h.get("rooms", []):
                r["price"] = net(r)
            if h.get("rooms"):  # a hotel's rate is its cheapest room for 2 adults, so single rooms don't count
                h["price"] = min(r["price"] for r in for_two(h["rooms"]))
        s["_t"] = datetime.fromisoformat(s["taken_at"])
        s["_file"] = f
        s["_hotels"] = {h["id"]: h for h in s["hotels"]}
        snaps.append(s)
    snaps.sort(key=lambda s: s["_t"])
    return snaps


def room_key(r):
    return f'{r["name"]}|{r.get("meal", "")}'


def rooms_of(h):
    return {room_key(r): r for r in (h or {}).get("rooms", [])}


def nearest(snaps, target, tol):
    best = min(snaps, key=lambda s: abs(s["_t"] - target), default=None)
    return best if best is not None and abs(best["_t"] - target) <= tol else None


def change(now, then):
    if not now or not then:
        return None
    return {"was": then, "diff": now - then, "pct": round((now - then) / then * 100, 1)}


def daily(snaps, days, value):
    """Closing value per calendar day for the last `days` days: [[date, value|null], ...]."""
    by_day = {}
    for s in snaps:
        by_day[s["_t"].date().isoformat()] = value(s)
    last = snaps[-1]["_t"].date()
    return [[d, by_day.get(d)] for d in
            ((last - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1))]


def archive_and_prune(snaps):
    cutoff = snaps[-1]["_t"] - timedelta(days=KEEP_DAYS)
    old = [s for s in snaps if s["_t"] < cutoff]
    if not old:
        return snaps
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    by_month = defaultdict(list)
    for s in old:
        by_month[s["_t"].strftime("%Y-%m")].append(s)
    for month, group in by_month.items():
        f = ARCHIVE / f"{month}.json"
        arc = json.loads(f.read_text()) if f.exists() else {}
        for s in group:  # later snapshots overwrite earlier ones: the day's closing rate
            day = s["_t"].date().isoformat()
            for h in s["hotels"]:
                e = arc.setdefault(h["id"], {"name": h["name"], "days": {}})
                e["days"][day] = {"price": h.get("price"),
                                  "rooms": {room_key(r): r["price"] for r in h.get("rooms", [])}}
        f.write_text(json.dumps(arc, ensure_ascii=False, separators=(",", ":")))
    for s in old:
        s["_file"].unlink()
        if not any(s["_file"].parent.iterdir()):
            s["_file"].parent.rmdir()
    return [s for s in snaps if s["_t"] >= cutoff]


def feed(snaps):
    start = snaps[-1]["_t"] - timedelta(days=FEED_DAYS)
    events = []
    for prev, cur in zip(snaps, snaps[1:]):
        if cur["_t"] < start:
            continue
        for hid, h in cur["_hotels"].items():
            p = prev["_hotels"].get(hid)
            if p is None:
                continue
            old, new = p.get("price"), h.get("price")
            ev = None
            if old and not new:
                ev = {"kind": "soldout", "old": old, "new": None}
            elif new and not old:
                ev = {"kind": "back", "old": None, "new": new}
            elif old and new and abs(new - old) / old >= MIN_MOVE:
                ev = {"kind": "up" if new > old else "down", "old": old, "new": new,
                      "pct": round((new - old) / old * 100, 1)}
            pr, cr = rooms_of(p), rooms_of(h)
            up = down = 0
            for k, r in cr.items():
                if k in pr and abs(r["price"] - pr[k]["price"]) / pr[k]["price"] >= MIN_MOVE:
                    up += r["price"] > pr[k]["price"]
                    down += r["price"] < pr[k]["price"]
            if ev is None and (up or down):
                ev = {"kind": "rooms", "old": old, "new": new}
            if ev:
                ev.update({"t": cur["taken_at"], "id": hid, "name": h["name"],
                           "stars": h.get("stars"), "rooms_up": up, "rooms_down": down})
                events.append(ev)
    events.sort(key=lambda e: e["t"], reverse=True)
    return events[:500]


def for_two(rooms):
    return [r for r in rooms if "single room" not in r["name"].lower()] or rooms


def net(r):
    """Booking.com room price before tax. Booking.com shows Karachi prices with tax excluded;
    if a price ever says it includes tax, the 15% sales tax is taken back out."""
    if "include" in (r.get("tax_text") or "").lower():
        return round(r["price"] / (1 + TAX))
    return r["price"]


def matches(booking_name, room):
    n = booking_name.lower()
    return (any(all(t in n for t in alt) for alt in room["keys"])
            and not any(t in n for t in room["exclude"]))


def best_match(hotel, room):
    """Cheapest Booking.com offer for a letter room type, preferring offers with breakfast
    (every rate letter includes breakfast). Value compared is the price before tax."""
    cands = [r for r in (hotel or {}).get("rooms", []) if matches(r["name"], room)]
    if not cands:
        return None
    bf = [r for r in cands if r.get("meal") == "breakfast"]
    pick = min(bf or cands, key=net)
    return {"booking_room": pick["name"], "meal": pick.get("meal"), "price": pick["price"],
            "value": net(pick)}


def site_rooms(snap, site_id):
    """Discounthotels.pk rooms for one hotel in a snapshot, with the price before tax (the site's include 15%)."""
    h = ((snap.get("dhc_site") or {}).get(str(site_id)) or {}) if site_id else {}
    return [dict(r, net=round(r["price"] / (1 + TAX))) for r in h.get("rooms", [])]


def site_low(rooms):
    two = [r for r in rooms if "single" not in r["name"].lower()] or rooms
    r = min(two, key=lambda r: r["net"], default=None)
    return r and {"name": r["name"], "net": r["net"]}


def site_match(rooms, room):
    """The Discounthotels.pk room that is the same as a rate-letter room, preferring double-occupancy names."""
    cands = [r for r in rooms if any(all(t in r["name"].lower() for t in alt) for alt in room["keys"])
             and not any(t in r["name"].lower() for t in room["exclude"] if t != "single room")]
    if not cands:
        return None
    r = min(cands, key=lambda r: ("double" not in r["name"].lower(), "single" in r["name"].lower(), r["net"]))
    return {"name": r["name"], "net": r["net"]}


def contract_hotel(snap, cid):
    return next((h for h in snap["hotels"] if h.get("contract") == cid), None)


def build_contracts(snaps, refs):
    """Booking.com side of the DHC rate-letter comparison. Rates themselves are never in here."""
    if not CONTRACTS.exists():
        return None
    latest = snaps[-1]
    out = []
    for c in json.loads(CONTRACTS.read_text(encoding="utf-8"))["hotels"]:
        h = contract_hotel(latest, c["id"])
        srooms = site_rooms(latest, c.get("dhc_site_id"))
        rooms, used = [], set()
        for room in c["rooms"]:
            m = best_match(h, room)
            row = {"id": room["id"], "name": room["name"], "match": m, "site": site_match(srooms, room)}
            if m:
                used.add(m["booking_room"])
                for k, ref in refs.items():
                    then = ref and best_match(contract_hotel(ref, c["id"]), room)
                    row[k] = change(m["value"], then and then["value"])
            row["trend"] = [v for _, v in daily(snaps, 30, lambda s: (best_match(contract_hotel(s, c["id"]), room) or {}).get("value"))]
            rooms.append(row)
        out.append({"id": c["id"], "name": c["name"], "found": h is not None,
                    "booking_id": h and h["id"], "booking_name": h and h["name"], "url": h and h["url"],
                    "rooms": rooms, "site_low": min((r["site"] for r in rooms if r["site"]), key=lambda x: x["net"],
                                                    default=None) or site_low(srooms),
                    "site_rooms": len(srooms), "booking_rooms": len((h or {}).get("rooms", [])),
                    "unmatched": sorted({r["name"] for r in (h or {}).get("rooms", []) if r["name"] not in used})})
    return out


def main():
    snaps = load(SNAPS)
    sample = not snaps
    if sample:
        snaps = load(SAMPLE)
    if not snaps:
        raise SystemExit("No snapshots found.")
    if not sample:
        snaps = archive_and_prune(snaps)

    latest = snaps[-1]
    refs = {k: nearest(snaps[:-1], latest["_t"] - d, tol) for k, (d, tol) in WINDOWS.items()}

    if (OUT / "hotels").exists():
        shutil.rmtree(OUT / "hotels")
    (OUT / "hotels").mkdir(parents=True)

    hotels = []
    for hid, h in latest["_hotels"].items():
        row = {k: h.get(k) for k in ("id", "name", "stars", "area", "url", "score", "price", "room_hint")}
        row["room_count"] = len(h.get("rooms", []))
        if h.get("rooms"):
            low = min(for_two(h["rooms"]), key=lambda r: r["price"])
            row["low_room"] = {"name": low["name"], "meal": low.get("meal")}
        today = [(s["_hotels"].get(hid, {}).get("price"), s["taken_at"]) for s in snaps
                 if s["_t"].date() == latest["_t"].date()]
        today = [t for t in today if t[0]]
        row["day_low"] = min(today, default=None) and dict(zip(("price", "at"), min(today)))
        row["day_high"] = max(today, default=None) and dict(zip(("price", "at"), max(today)))
        for k, ref in refs.items():
            row[k] = change(h.get("price"), ref and ref["_hotels"].get(hid, {}).get("price"))
        row["trend"] = [v for _, v in daily(snaps, 30, lambda s: s["_hotels"].get(hid, {}).get("price"))]
        hotels.append(row)

        rooms = []
        for key, r in rooms_of(h).items():
            rr = {"name": r["name"], "meal": r.get("meal"), "free_cancel": r.get("free_cancel"),
                  "price": r["price"]}
            for k, ref in refs.items():
                then = ref and rooms_of(ref["_hotels"].get(hid)).get(key)
                rr[k] = change(r["price"], then and then["price"])
            rr["trend"] = daily(snaps, 30, lambda s: (rooms_of(s["_hotels"].get(hid)).get(key) or {}).get("price"))
            rooms.append(rr)
        rooms.sort(key=lambda r: r["price"])
        detail = dict(row, rooms=rooms,
                      history=daily(snaps, 30, lambda s: s["_hotels"].get(hid, {}).get("price")))
        (OUT / "hotels" / f"{hid}.json").write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")

    summary = {
        "sample": sample,
        "status": None if not STATUS.exists() else json.loads(STATUS.read_text()),
        "repo": os.environ.get("GITHUB_REPOSITORY"),
        "updated": latest["taken_at"],
        "checkin": latest["checkin"], "nights": latest["nights"], "adults": latest["adults"],
        "currency": latest["currency"], "source": latest["source"],
        "snapshots": len(snaps), "first": snaps[0]["taken_at"],
        "compared_to": {k: ref and ref["taken_at"] for k, ref in refs.items()},
        "hotels": sorted(hotels, key=lambda h: h["name"]),
        "changes": feed(snaps),
    }
    contracts = build_contracts(snaps, refs)
    if contracts is not None:
        (OUT / "contracts.json").write_text(json.dumps(contracts, ensure_ascii=False), encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
    print(f"{len(hotels)} hotels, {len(summary['changes'])} changes, {len(snaps)} snapshots"
          + (" (sample data)" if sample else ""))


if __name__ == "__main__":
    main()
