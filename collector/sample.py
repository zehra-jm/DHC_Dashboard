"""Write made-up snapshots to data/sample/ so the dashboard can be previewed before the
collector has run. Hotel names are real Karachi properties; every price is invented.
The build step ignores this folder as soon as one real snapshot exists."""
import json
import random
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sample"
PKT = timezone(timedelta(hours=5))

HOTELS = [  # name, stars, area, base rate for the cheapest room, room types
    ("Karachi Marriott Hotel", 5, "Abdullah Haroon Road", 48000, ["Deluxe King", "Deluxe Twin", "Executive King", "Executive Suite"]),
    ("Pearl-Continental Hotel Karachi", 5, "Club Road", 52000, ["Superior King", "Superior Twin", "Deluxe King", "Executive Suite"]),
    ("Mövenpick Hotel Karachi", 5, "Club Road, Civil Lines", 50000, ["Classic Room", "Deluxe Room", "Executive Room", "Junior Suite"]),
    ("Avari Towers Karachi", 5, "Fatima Jinnah Road", 41000, ["World Traveler Room", "Business Class Room", "Executive Room"]),
    ("Hotel Mehran", 4, "Shahrah-e-Faisal", 23500, ["Deluxe Room", "Executive Room", "Superior Room", "Junior Suite"]),
    ("Ramada by Wyndham Karachi Creek", 4, "DHA Phase 8", 27000, ["Standard King", "Deluxe Twin", "Suite"]),
    ("Beach Luxury Hotel", 4, "M.T. Khan Road", 29000, ["Superior Room", "Deluxe Room", "Executive Room"]),
    ("Regent Plaza Hotel", 4, "Shahrah-e-Faisal", 21000, ["Standard Room", "Deluxe Room", "Executive Suite"]),
    ("Carlton Hotel", 4, "Shahrah-e-Faisal", 22000, ["Deluxe Double", "Executive Double", "Suite"]),
    ("Dreamworld Resort", 4, "Gulshan-e-Maymar", 19500, ["Standard Room", "Deluxe Room", "Family Suite"]),
    ("Hotel One Karachi", 3, "PECHS", 13500, ["Standard Double", "Deluxe Double"]),
    ("Faran Hotel", 3, "Shahrah-e-Faisal", 11000, ["Standard Room", "Deluxe Room", "Family Room"]),
    ("Hotel Crown Inn", 3, "Shahrah-e-Faisal", 9800, ["Standard Double", "Deluxe Double"]),
    ("Sarawan Hotel", 3, "Saddar", 8500, ["Standard Room", "Executive Room"]),
    ("Ambassador Hotel", 3, "Saddar", 9200, ["Standard Twin", "Deluxe King"]),
]


def slug(name):
    return "".join(c if c.isalnum() else "-" for c in name.lower().replace("ö", "o")).strip("-").replace("--", "-")


def main():
    rnd = random.Random(7)
    if OUT.exists():
        shutil.rmtree(OUT)
    end = datetime.now(PKT).replace(minute=5, second=0, microsecond=0)
    times = [end - timedelta(hours=6 * i) for i in range(35 * 4 - 1, -1, -1)]
    level = {h[0]: 1.0 for h in HOTELS}
    gap = {h[0]: [1 + 0.18 * i + rnd.uniform(-0.04, 0.04) for i in range(len(h[4]))] for h in HOTELS}
    for t in times:
        hotels = []
        for name, stars, area, base, rooms in HOTELS:
            if rnd.random() < 0.035:  # occasional real repricing
                level[name] *= rnd.choice([0.92, 0.95, 1.05, 1.08, 1.12])
            level[name] += (1.0 - level[name]) * 0.06  # drift back toward normal
            weekend = 1.04 if (t + timedelta(days=1)).weekday() in (4, 5) else 1.0
            sold_out = rnd.random() < 0.01
            rr = []
            for i, rn in enumerate(rooms):
                if sold_out or rnd.random() < 0.03:
                    continue
                p = base * level[name] * weekend * gap[name][i] * rnd.uniform(0.995, 1.005)
                meal = "breakfast" if i % 2 == 0 else "room only"
                rr.append({"name": rn, "meal": meal, "price": int(round(p, -2)), "free_cancel": i < 2})
            rr.sort(key=lambda r: r["price"])
            hotels.append({"id": slug(name), "name": name, "stars": stars, "area": area,
                           "url": f"https://www.booking.com/searchresults.html?ss={name.replace(' ', '+')}",
                           "score": round(random.Random(name).uniform(7.2, 8.9), 1),
                           "price": rr[0]["price"] if rr else None,
                           "room_hint": rr[0]["name"] if rr else None, "rooms": rr})
        snap = {"taken_at": t.isoformat(timespec="minutes"), "source": "booking.com (sample)",
                "checkin": (t + timedelta(days=1)).date().isoformat(), "nights": 1, "adults": 2,
                "currency": "PKR", "hotels": hotels}
        f = OUT / t.strftime("%Y-%m-%d") / (t.strftime("%H%M") + ".json")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(snap, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(times)} sample snapshots")


if __name__ == "__main__":
    main()
