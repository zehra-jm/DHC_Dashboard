"""Collect one snapshot of Booking.com rates for 3, 4 and 5 star hotels in Karachi.

What is priced: one room for 2 adults, checking in tomorrow (Karachi time) for 1 night,
in PKR. Every run prices the same kind of stay, so runs can be compared over time.

Writes data/snapshots/YYYY-MM-DD/HHMM.json, and data/status.json saying whether the run
worked. The status tells a page-layout change (the collector needs fixing) apart from a
bot block (usually clears on its own), and the dashboard shows a warning bar from it.
On any problem it saves the page HTML and a screenshot under debug/.

Usage: python collector/collect.py [--max-hotels N] [--no-rooms]
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

ROOT = Path(__file__).resolve().parent.parent
SNAP_DIR = ROOT / "data" / "snapshots"
DEBUG_DIR = ROOT / "debug"
CONTRACTS = ROOT / "data" / "contract-hotels.json"
STATUS = ROOT / "data" / "status.json"
BLOCK_SIGNS = ("captcha", "are you a robot", "verify you are human", "unusual traffic",
               "access denied", "request blocked", "too many requests")
ALERT_BLOCKED_AFTER = timedelta(hours=12)  # one blocked run is normal; a day of them is not
PKT = timezone(timedelta(hours=5))
PAGE_SIZE = 25
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# Runs inside the search results page and returns one object per property card.
CARDS_JS = r"""
() => [...document.querySelectorAll('[data-testid="property-card"]')].map(card => {
  const q = s => card.querySelector(s);
  const txt = s => (q(s)?.innerText || '').trim();
  const link = q('a[data-testid="title-link"]') || q('a[href*="/hotel/"]');
  let stars = card.querySelectorAll('[data-testid="rating-stars"] > span, [data-testid="rating-squares"] > span').length;
  if (!stars) {
    const lab = q('[aria-label*="out of 5"]')?.getAttribute('aria-label') || '';
    const m = lab.match(/(\d)\s*out of 5/); if (m) stars = +m[1];
  }
  const score = (q('[data-testid="review-score"]')?.innerText || '').match(/\d+(\.\d)?/);
  return {
    name: txt('[data-testid="title"]'),
    url: link ? link.href : '',
    stars,
    area: txt('[data-testid="address"]'),
    price_text: txt('[data-testid="price-and-discounted-price"]'),
    original_text: txt('[data-testid="availability-rate-information"] [aria-hidden="true"]:not([data-testid])'),
    room_hint: txt('[data-testid="recommended-units"] h4'),
    score: score ? +score[0] : null,
  };
})
"""

# Runs inside a hotel page. Returns the room table as rows of {name, price_text, meal, cancel, guests}.
ROOMS_JS = r"""
() => {
  const rows = [...document.querySelectorAll('#hprt-table tbody tr')];
  let current = '';
  const out = [];
  for (const tr of rows) {
    const nameEl = tr.querySelector('.hprt-roomtype-icon-link, [data-testid="room-name"], .hprt-roomtype-link');
    if (nameEl) current = nameEl.innerText.trim();
    const priceEl = tr.querySelector('.bui-price-display__value, .prco-valign-middle-helper, [data-testid="price-and-discounted-price"]');
    if (!current || !priceEl) continue;
    const cond = (tr.querySelector('.hprt-table-cell-conditions')?.innerText || '').toLowerCase();
    const guests = tr.querySelectorAll('.c-occupancy-icons__adults i, .bicon-occupancy').length
      || +((tr.querySelector('.hprt-occupancy-occupancy-info')?.innerText || '').match(/\d+/) || [0])[0];
    const bfLine = (cond.match(/[^\n]*breakfast[^\n]*/) || [''])[0];
    const priceCell = priceEl.closest('td') || tr;
    const taxEl = priceCell.querySelector('.prd-taxes-and-fees-under-price, [data-testid="taxes-and-charges"]');
    const taxText = taxEl ? taxEl.innerText : ((priceCell.innerText.match(/[^\n]*tax[^\n]*/i) || [''])[0]);
    out.push({
      name: current,
      price_text: priceEl.innerText.trim(),
      tax_text: taxText.trim(),
      meal: bfLine && !/pkr|costs|optional|extra/.test(bfLine) ? 'breakfast' : 'room only',
      cancel: /free cancellation/.test(cond),
      guests,
    });
  }
  return out;
}
"""


def money(text):
    """'PKR 23,456' -> 23456. Takes the last number in the text (the discounted price)."""
    nums = re.findall(r"\d[\d,]*", text or "")
    return int(nums[-1].replace(",", "")) if nums else None


def with_taxes(price, tax_text):
    """Price including taxes and charges, or None when Booking.com doesn't say."""
    t = (tax_text or "").lower()
    if "include" in t:
        return price
    extra = money(t) if "tax" in t or "charge" in t else None
    return price + extra if extra is not None else None


def hotel_id(url):
    m = re.search(r"/hotel/[a-z]{2}/([^./?]+)", urlparse(url).path)
    return m.group(1) if m else None


def dismiss_popups(page):
    for sel in ("#onetrust-accept-btn-handler", 'button[aria-label="Dismiss sign-in info."]',
                'button[aria-label="Dismiss sign in information."]'):
        try:
            page.locator(sel).first.click(timeout=1500)
        except Exception:
            pass


def save_debug(page, name):
    DEBUG_DIR.mkdir(exist_ok=True)
    try:
        (DEBUG_DIR / f"{name}.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(DEBUG_DIR / f"{name}.png"), full_page=True)
    except Exception as e:
        print("could not save debug page:", e)


def search_url(checkin, checkout, offset):
    return "https://www.booking.com/searchresults.en-gb.html?" + urlencode({
        "ss": "Karachi, Sindh, Pakistan", "dest_type": "city",
        "checkin": checkin, "checkout": checkout,
        "group_adults": 2, "no_rooms": 1, "group_children": 0,
        "selected_currency": "PKR", "lang": "en-gb",
        "nflt": "class=3;class=4;class=5", "offset": offset,
    })


def hotel_url(url, checkin, checkout):
    base = url.split("?")[0]
    return base + "?" + urlencode({"checkin": checkin, "checkout": checkout, "group_adults": 2,
                                   "no_rooms": 1, "group_children": 0,
                                   "selected_currency": "PKR", "lang": "en-gb"})



class Problem(Exception):
    """state is 'layout' (Booking changed its pages) or 'blocked' (Booking served a bot check)."""
    def __init__(self, state, message):
        super().__init__(message)
        self.state = state


def blocked(page, response):
    if response is not None and response.status in (403, 429):
        return True
    try:
        text = (page.title() + " " + page.inner_text("body")[:4000]).lower()
    except Exception:
        return False
    return any(s in text for s in BLOCK_SIGNS)


def collect_search(page, checkin, checkout, max_hotels):
    hotels = {}
    offset = 0
    while offset < max_hotels:
        resp = page.goto(search_url(checkin, checkout, offset), wait_until="domcontentloaded", timeout=60000)
        dismiss_popups(page)
        try:
            page.wait_for_selector('[data-testid="property-card"]', timeout=25000)
        except PWTimeout:
            if offset > 0:
                break
            save_debug(page, "search")
            if blocked(page, resp):
                raise Problem("blocked", "Booking.com showed a bot check instead of the search results.")
            raise Problem("layout", "The search page loaded but no hotel cards were found on it.")
        page.mouse.wheel(0, 20000)
        time.sleep(1.5)
        cards = page.evaluate(CARDS_JS)
        readable = [c for c in cards if c["name"] and hotel_id(c["url"])]
        priced = [c for c in readable if money(c["price_text"])]
        if offset == 0 and (len(readable) < len(cards) / 2 or len(priced) < len(readable) * 0.3):
            save_debug(page, "search")
            raise Problem("layout", f"Hotel cards were found but their names or prices could not be read "
                                    f"({len(readable)} of {len(cards)} named, {len(priced)} priced).")
        new = 0
        for c in readable:
            hid = hotel_id(c["url"])
            if hid in hotels or (c["stars"] and c["stars"] < 3):
                continue
            hotels[hid] = {
                "id": hid, "name": c["name"], "stars": c["stars"] or None, "area": c["area"],
                "url": c["url"].split("?")[0], "score": c["score"],
                "price": money(c["price_text"]), "room_hint": c["room_hint"], "rooms": [],
            }
            new += 1
        print(f"offset {offset}: {len(cards)} cards, {new} new")
        if new == 0 or len(cards) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(2)
    return hotels


def collect_rooms(page, hotel, checkin, checkout):
    """Returns (rooms, problem) where problem is None, 'blocked' or 'layout'."""
    resp = page.goto(hotel_url(hotel["url"], checkin, checkout), wait_until="domcontentloaded", timeout=60000)
    dismiss_popups(page)
    try:
        page.wait_for_selector("#hprt-table", timeout=15000)
    except PWTimeout:
        if blocked(page, resp):
            return [], "blocked"
        # A hotel with a price in the search results should have a room table.
        return [], ("layout" if hotel["price"] else None)
    rows = page.evaluate(ROOMS_JS)
    best = {}
    for r in rows:
        p = money(r["price_text"])
        if not p or 0 < r["guests"] < 2:  # we price a stay for 2 adults
            continue
        key = f'{r["name"]}|{r["meal"]}'  # room-only and breakfast rates are tracked separately
        cur = best.get(key)
        if cur is None or p < cur["price"]:
            best[key] = {"name": r["name"], "meal": r["meal"], "price": p, "free_cancel": r["cancel"],
                         "total": with_taxes(p, r["tax_text"])}
    if hotel["price"] and not best:
        return [], "layout"
    return sorted(best.values(), key=lambda r: r["price"]), None


def page_name(page):
    for sel in ('[data-testid="property-name"]', "h2.pp-header__title", "#hp_hotel_name"):
        try:
            t = page.locator(sel).first.inner_text(timeout=2000).strip()
            if t:
                return t.splitlines()[-1].strip()
        except Exception:
            pass
    return page.title().split(",")[0].strip()


def name_ok(name, keys):
    n = (name or "").lower()
    return any(k in n for k in keys)


def resolve_contract(page, c, checkin, checkout):
    """Find a contract hotel's Booking.com page: the saved URL if its name matches, else a name search."""
    if c.get("booking_url"):
        page.goto(hotel_url(c["booking_url"], checkin, checkout), wait_until="domcontentloaded", timeout=60000)
        dismiss_popups(page)
        if "/hotel/" in page.url and name_ok(page_name(page), c["name_keys"]):
            return page.url.split("?")[0], page_name(page)
    page.goto("https://www.booking.com/searchresults.en-gb.html?" + urlencode({
        "ss": f'{c["name"]}, Karachi', "checkin": checkin, "checkout": checkout, "group_adults": 2,
        "no_rooms": 1, "selected_currency": "PKR", "lang": "en-gb"}), wait_until="domcontentloaded", timeout=60000)
    dismiss_popups(page)
    try:
        page.wait_for_selector('[data-testid="property-card"]', timeout=20000)
    except PWTimeout:
        return None, None
    for card in page.evaluate(CARDS_JS):
        if name_ok(card["name"], c["name_keys"]):
            return card["url"].split("?")[0], card["name"]
    return None, None


def add_contract_hotels(page, hotels, checkin, checkout):
    """Make sure every hotel with a DHC rate letter is in the snapshot, star rating or not."""
    found = {}
    contracts = json.loads(CONTRACTS.read_text(encoding="utf-8"))["hotels"] if CONTRACTS.exists() else []
    for c in contracts:
        url, name = resolve_contract(page, c, checkin, checkout)
        if not url:
            print(f"contract hotel not found on Booking.com: {c['name']}")
            found[c["id"]] = None
            continue
        hid = hotel_id(url)
        if hid not in hotels:
            hotels[hid] = {"id": hid, "name": name or c["name"], "stars": None, "area": "", "url": url,
                           "score": None, "price": None, "room_hint": None, "rooms": []}
        hotels[hid]["contract"] = c["id"]
        found[c["id"]] = hid
        time.sleep(1.5)
    return found


def write_status(now, state, message):
    prev = json.loads(STATUS.read_text()) if STATUS.exists() else {}
    stamp = now.isoformat(timespec="minutes")
    since = prev.get("since", stamp) if prev.get("state") == state else stamp
    alert = state in ("layout", "rooms") or (
        state == "blocked" and now - datetime.fromisoformat(since) >= ALERT_BLOCKED_AFTER)
    status = {"state": state, "message": message, "checked_at": stamp, "since": since,
              "last_ok": stamp if state in ("ok", "rooms") else prev.get("last_ok"), "alert": alert}
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(status, indent=1), encoding="utf-8")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"state={state}\nalert={'true' if alert else 'false'}\n")
    print(f"status: {state} - {message}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-hotels", type=int, default=300)
    ap.add_argument("--no-rooms", action="store_true")
    args = ap.parse_args()

    now = datetime.now(PKT)
    checkin = (now + timedelta(days=1)).date()
    checkout = checkin + timedelta(days=1)
    ci, co = checkin.isoformat(), checkout.isoformat()
    room_problems = {"layout": 0, "blocked": 0}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
            ctx = browser.new_context(user_agent=UA, locale="en-GB", timezone_id="Asia/Karachi",
                                      viewport={"width": 1366, "height": 900})
            ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
            page = ctx.new_page()
            hotels = collect_search(page, ci, co, args.max_hotels)
            if not hotels:
                raise Problem("layout", "The search page had cards but none could be read as 3 to 5 star hotels.")
            print(f"{len(hotels)} hotels found")
            contract_map = add_contract_hotels(page, hotels, ci, co)
            print(f"contract hotels: {sum(1 for v in contract_map.values() if v)} of {len(contract_map)} found")
            if not args.no_rooms:
                for i, h in enumerate(hotels.values(), 1):
                    try:
                        h["rooms"], prob = collect_rooms(page, h, ci, co)
                    except Exception as e:
                        print(f"rooms failed for {h['id']}: {e}")
                        prob = None
                    if prob == "layout" and not h["price"] and h.get("contract"):
                        prob = None  # contract hotel outside the search: no search price to expect a table from
                    if prob:
                        if not any(room_problems.values()):
                            save_debug(page, f"hotel-{h['id']}")
                        room_problems[prob] += 1
                    if h["rooms"] and (h["price"] is None or h["rooms"][0]["price"] < h["price"]):
                        h["price"] = h["rooms"][0]["price"]
                    print(f"[{i}/{len(hotels)}] {h['name']}: {len(h['rooms'])} room types" + (f" ({prob})" if prob else ""))
                    time.sleep(1.2)
            browser.close()
    except Problem as e:
        write_status(now, e.state, str(e))
        sys.exit(1)

    snap = {
        "taken_at": now.isoformat(timespec="minutes"), "source": "booking.com",
        "checkin": ci, "nights": 1, "adults": 2, "currency": "PKR",
        "contracts": contract_map,
        "hotels": sorted(hotels.values(), key=lambda h: h["name"]),
    }
    out = SNAP_DIR / now.strftime("%Y-%m-%d") / (now.strftime("%H%M") + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("saved", out.relative_to(ROOT))

    priced = sum(1 for h in hotels.values() if h["price"])
    if room_problems["layout"] > max(2, priced * 0.4):
        write_status(now, "rooms", f"Room tables could not be read on {room_problems['layout']} of {priced} "
                                   "hotel pages. Hotel rates were saved; room rates were not.")
    else:
        write_status(now, "ok", f"{len(hotels)} hotels, {sum(len(h['rooms']) for h in hotels.values())} room rates.")


if __name__ == "__main__":
    main()
