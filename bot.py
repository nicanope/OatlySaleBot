import json
import os
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


# -----------------------------
# ENV
# -----------------------------
dotenv_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=dotenv_path)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
SCRAPEDO_TOKEN = os.getenv("SCRAPEDO_TOKEN")
CHECK_EVERY_MINUTES = int(os.getenv("CHECK_EVERY_MINUTES", "30"))

STATE_FILE = Path(__file__).parent / ".alert_state.json"

if not BOT_TOKEN:
    raise ValueError("Missing BOT_TOKEN")
if not CHAT_ID:
    raise ValueError("Missing CHAT_ID")
if not SCRAPEDO_TOKEN:
    raise ValueError("Missing SCRAPEDO_TOKEN")


# -----------------------------
# PRODUCTS TO WATCH
# -----------------------------
PRODUCTS = [
    {
        "store": "Amazon",
        "label": "Oatly Barista 32oz",
        "threshold": 4.00,
        "url": "https://www.amazon.com/Oatly-Milk-Barista-Original-Ounce/dp/B07NSW3TSY",
        "expected_keywords": ["oatly", "barista"],
    },
    {
        "store": "Amazon",
        "label": "Oatly Original 64oz",
        "threshold": 5.00,
        "url": "https://www.amazon.com/Oatly-OATLY-Original-Oat-Milk/dp/B075QJ8M1K",
        "expected_keywords": ["oatly"],
    },
    {
        "store": "Target",
        "label": "Oatly Barista 32oz",
        "threshold": 4.00,
        "url": "https://www.target.com/p/oatly-barista-edition-oatmilk-ambient-32oz/-/A-82798362",
        "expected_keywords": ["oatly", "barista"],
    },
    {
        "store": "Target",
        "label": "Oatly Original 64oz",
        "threshold": 5.00,
        "url": "https://www.target.com/p/oatly-oatmilk-0-5gal/-/A-53328399",
        "expected_keywords": ["oatly"],
    },
    {
        "store": "H-E-B",
        "label": "Oatly Barista 32oz",
        "threshold": 4.00,
        "url": "https://www.heb.com/product-detail/oatly-oat-milk-barista-edition/4379081",
        "expected_keywords": ["oatly", "barista"],
    },
    {
        "store": "H-E-B",
        "label": "Oatly Full Fat 64oz",
        "threshold": 5.00,
        "url": "https://www.heb.com/product-detail/oatly-full-fat-oat-milk/9026509",
        "expected_keywords": ["oatly"],
    },
    {
        "store": "H-E-B",
        "label": "Oatly Original 64oz",
        "threshold": 5.00,
        "url": "https://www.heb.com/product-detail/oatly-the-original-oat-milk/2242160",
        "expected_keywords": ["oatly"],
    },
    {
        "store": "Randalls",
        "label": "Oatly Barista 32oz",
        "threshold": 4.00,
        "url": "https://www.randalls.com/shop/product-details.970008328.html",
        "expected_keywords": ["oatly", "barista"],
    },
    {
        "store": "Randalls",
        "label": "Oatly Original 64oz",
        "threshold": 5.00,
        "url": "https://www.randalls.com/shop/product-details.960451820.html",
        "expected_keywords": ["oatly"],
    },
    {
        "store": "Randalls",
        "label": "Oatly Full Fat 64oz",
        "threshold": 5.00,
        "url": "https://www.randalls.com/shop/product-details.960536091.html",
        "expected_keywords": ["oatly"],
    },
]


# -----------------------------
# TELEGRAM
# -----------------------------
def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    response = requests.post(
        url,
        data={"chat_id": CHAT_ID, "text": message},
        timeout=20,
    )
    print("Telegram:", response.status_code)
    response.raise_for_status()


# -----------------------------
# STATE
# -----------------------------
def load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


# -----------------------------
# SCRAPE.DO
# -----------------------------
def fetch_html(url):
    params = {
        "token": SCRAPEDO_TOKEN,
        "url": url,
        "render": "true",
        "geoCode": "us",
        "super": "true",
        "timeout": "60000",
    }

    response = requests.get(
        "https://api.scrape.do/",
        params=params,
        timeout=90,
    )
    response.raise_for_status()
    return response.text


# -----------------------------
# PARSING HELPERS
# -----------------------------
def clean_text(text):
    return " ".join(text.split())


def title_from_soup(soup):
    selectors = [
        'meta[property="og:title"]',
        'meta[name="title"]',
        "h1",
        "title",
    ]

    for selector in selectors:
        el = soup.select_one(selector)
        if not el:
            continue

        if el.name == "meta":
            content = el.get("content")
            if content:
                return clean_text(content)

        text = el.get_text(" ", strip=True)
        if text:
            return clean_text(text)

    return ""


def page_contains_expected_product(title, expected_keywords):
    title_lower = title.lower()
    return all(keyword.lower() in title_lower for keyword in expected_keywords)


def parse_price_string(raw):
    if not raw:
        return None

    raw = raw.replace(",", "").strip()
    match = re.search(r"(\d+(?:\.\d{1,2})?)", raw)
    if not match:
        return None

    try:
        value = float(match.group(1))
    except ValueError:
        return None

    return round(value, 2)


def valid_carton_price(value):
    if value is None:
        return False
    return 2.50 <= value <= 12.00


def prices_from_meta(soup):
    prices = []

    selectors = [
        'meta[itemprop="price"]',
        'meta[property="product:price:amount"]',
    ]

    for selector in selectors:
        for el in soup.select(selector):
            value = parse_price_string(el.get("content") or el.get("value"))
            if valid_carton_price(value):
                prices.append(value)

    return prices


def prices_from_json_ld(soup):
    prices = []

    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text()
        if not raw:
            continue

        try:
            data = json.loads(raw)
        except Exception:
            continue

        def walk(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key in {"price", "lowPrice", "highPrice"}:
                        parsed = parse_price_string(str(value))
                        if valid_carton_price(parsed):
                            prices.append(parsed)
                    else:
                        walk(value)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(data)

    return prices


def prices_from_visible_text(soup, store):
    text = clean_text(soup.get_text(" ", strip=True))
    prices = []

    patterns = [
        r"Current price[:\s]*\$?\s*(\d+(?:\.\d{1,2})?)",
        r"Sale price[:\s]*\$?\s*(\d+(?:\.\d{1,2})?)",
        r"Price[:\s]*\$?\s*(\d+(?:\.\d{1,2})?)",
        r"Now[:\s]*\$?\s*(\d+(?:\.\d{1,2})?)",
        r"\$(\d+(?:\.\d{1,2})?)",
    ]

    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            value = parse_price_string(match)
            if valid_carton_price(value):
                prices.append(value)

    # Extra cleanup for Amazon noise:
    # Prefer prices that are not tiny unit prices.
    if store.lower() == "amazon":
        prices = [p for p in prices if p >= 3.00]

    return prices


def choose_best_price(prices):
    if not prices:
        return None
    return min(prices)


def parse_product_page(html, store, expected_keywords):
    soup = BeautifulSoup(html, "html.parser")

    title = title_from_soup(soup)
    if not title:
        return {"title": "", "price": None, "valid_product": False}

    valid_product = page_contains_expected_product(title, expected_keywords)

    candidates = []
    candidates.extend(prices_from_meta(soup))
    candidates.extend(prices_from_json_ld(soup))
    candidates.extend(prices_from_visible_text(soup, store))

    price = choose_best_price(candidates)

    return {
        "title": title,
        "price": price,
        "valid_product": valid_product,
    }


# -----------------------------
# BUSINESS LOGIC
# -----------------------------
def already_alerted_same_price(state, url, price):
    existing = state.get(url)
    if not existing:
        return False
    return existing.get("last_alert_price") == price


def remember_alert(state, product, title, price):
    state[product["url"]] = {
        "store": product["store"],
        "label": product["label"],
        "last_alert_price": price,
        "last_title": title,
        "updated_at": int(time.time()),
    }


def build_message(alerts):
    lines = ["🛒 Oatly deal alert", ""]

    for item in alerts:
        lines.append(f"{item['store']}: ${item['price']:.2f}")
        lines.append(item["title"])
        lines.append(item["url"])
        lines.append("")

    return "\n".join(lines).strip()


def check_all_products():
    print("Checking deals...")
    state = load_state()
    alerts = []

    for product in PRODUCTS:
        try:
            print(f"Fetching {product['store']} | {product['label']}")
            html = fetch_html(product["url"])

            parsed = parse_product_page(
                html=html,
                store=product["store"],
                expected_keywords=product["expected_keywords"],
            )

            print(
                f"Parsed {product['store']} | title={parsed['title']} | price={parsed['price']} | valid_product={parsed['valid_product']}"
            )

            if not parsed["valid_product"]:
                print("Skipping: page does not look like the expected product.")
                continue

            if parsed["price"] is None:
                print("Skipping: no usable carton price found.")
                continue

            if parsed["price"] > product["threshold"]:
                continue

            if already_alerted_same_price(state, product["url"], parsed["price"]):
                print("Skipping: already alerted for this same price.")
                continue

            alerts.append(
                {
                    "store": product["store"],
                    "title": parsed["title"],
                    "price": parsed["price"],
                    "url": product["url"],
                }
            )

            remember_alert(
                state=state,
                product=product,
                title=parsed["title"],
                price=parsed["price"],
            )

        except Exception as e:
            print(f"Error checking {product['store']} | {product['label']}: {e}")

    if alerts:
        send_telegram(build_message(alerts))
        print("Alert sent.")
    else:
        print("No deals found.")

    save_state(state)


# -----------------------------
# MAIN LOOP
# -----------------------------
if __name__ == "__main__":
    while True:
        check_all_products()
        time.sleep(CHECK_EVERY_MINUTES * 60)