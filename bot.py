import os
import time
import requests
from pathlib import Path
from urllib.parse import quote_plus
from dotenv import load_dotenv
from bs4 import BeautifulSoup

dotenv_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=dotenv_path)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
ZIP_CODE = os.getenv("ZIP_CODE", "78613")

TARGET_BARISTA_MAX = 4.00
TARGET_64OZ_MAX = 5.00

CHECK_EVERY_SECONDS = 1800  # 30 minutes


def send_telegram(message: str) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        response = requests.post(
            url,
            data={"chat_id": CHAT_ID, "text": message},
            timeout=20,
        )
        print("Telegram status:", response.status_code)
        print("Telegram response:", response.text)
    except Exception as e:
        print("Telegram error:", e)


def safe_get(url: str, params=None, headers=None):
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    if headers:
        default_headers.update(headers)

    response = requests.get(url, params=params, headers=default_headers, timeout=20)
    response.raise_for_status()
    return response


def normalize_name(name: str) -> str:
    return " ".join(name.lower().split())


def is_target_product(name: str):
    n = normalize_name(name)

    barista_match = (
        "oatly" in n
        and "barista" in n
        and ("32 oz" in n or "32 fl oz" in n or "32oz" in n)
    )

    size64_match = (
        "oatly" in n
        and (
            "64 oz" in n
            or "64 fl oz" in n
            or "64oz" in n
            or "1/2 gal" in n
            or "half gallon" in n
        )
    )

    return barista_match, size64_match


def format_deal(store: str, name: str, price: float, url: str):
    return {
        "store": store,
        "name": name.strip(),
        "price": round(float(price), 2),
        "url": url,
    }


def check_target():
    deals = []
    try:
        url = "https://redsky.target.com/redsky_aggregations/v1/web/plp_search_v2"
        params = {
            "key": "9f36aeafbe60771d0a2fd6d6bdfeeb03",
            "keyword": "oatly",
            "channel": "WEB",
            "count": 24,
            "default_purchasability_filter": "true",
        }

        response = safe_get(url, params=params)
        data = response.json()

        products = data.get("data", {}).get("search", {}).get("products", [])
        for item in products:
            title = (
                item.get("item", {})
                .get("product_description", {})
                .get("title", "")
            )
            price = item.get("price", {}).get("current_retail")
            tcin = item.get("tcin")

            if not title or price is None:
                continue

            barista_match, size64_match = is_target_product(title)

            product_url = f"https://www.target.com/p/-/A-{tcin}" if tcin else "https://www.target.com/s?searchTerm=oatly"

            if barista_match and float(price) < TARGET_BARISTA_MAX:
                deals.append(format_deal("Target", title, price, product_url))

            if size64_match and float(price) < TARGET_64OZ_MAX:
                deals.append(format_deal("Target", title, price, product_url))

    except Exception as e:
        print("Target error:", e)

    return deals


def extract_first_price(text: str):
    if not text:
        return None
    cleaned = text.replace(",", "")
    num = []
    seen_digit = False
    seen_dot = False

    for ch in cleaned:
        if ch.isdigit():
            num.append(ch)
            seen_digit = True
        elif ch == "." and seen_digit and not seen_dot:
            num.append(ch)
            seen_dot = True
        elif seen_digit:
            break

    try:
        return float("".join(num)) if num else None
    except Exception:
        return None


def check_amazon():
    deals = []
    try:
        url = "https://www.amazon.com/s"
        params = {"k": "oatly"}
        soup = BeautifulSoup(safe_get(url, params=params).text, "html.parser")

        for item in soup.select("[data-component-type='s-search-result']"):
            title_el = item.select_one("h2 span")
            whole = item.select_one(".a-price-whole")
            frac = item.select_one(".a-price-fraction")
            link_el = item.select_one("h2 a")

            if not title_el or not whole:
                continue

            title = title_el.get_text(" ", strip=True)
            price_text = whole.get_text(strip=True)
            if frac:
                price_text += "." + frac.get_text(strip=True)

            price = extract_first_price(price_text)
            if price is None:
                continue

            barista_match, size64_match = is_target_product(title)

            href = link_el.get("href") if link_el else None
            product_url = f"https://www.amazon.com{href}" if href else "https://www.amazon.com/s?k=oatly"

            if barista_match and price < TARGET_BARISTA_MAX:
                deals.append(format_deal("Amazon", title, price, product_url))

            if size64_match and price < TARGET_64OZ_MAX:
                deals.append(format_deal("Amazon", title, price, product_url))

    except Exception as e:
        print("Amazon error:", e)

    return deals


def parse_heb_product(url: str):
    deals = []
    try:
        soup = BeautifulSoup(safe_get(url).text, "html.parser")

        title = ""
        h1 = soup.select_one("h1")
        if h1:
            title = h1.get_text(" ", strip=True)

        page_text = soup.get_text(" ", strip=True)
        price = None

        # Try to find common H-E-B price patterns near dollar signs
        for marker in ["$"]:
            idx = page_text.find(marker)
            if idx != -1:
                chunk = page_text[idx:idx + 20]
                price = extract_first_price(chunk)
                if price is not None:
                    break

        if title and price is not None:
            barista_match, size64_match = is_target_product(title)

            if barista_match and price < TARGET_BARISTA_MAX:
                deals.append(format_deal("H-E-B", title, price, url))

            if size64_match and price < TARGET_64OZ_MAX:
                deals.append(format_deal("H-E-B", title, price, url))

   