import os
import time
import requests
from pathlib import Path
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# Point directly to your .env file
dotenv_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=dotenv_path)

# Now read variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
ZIP_CODE = os.getenv("ZIP_CODE")

# TEST: print them
print("BOT_TOKEN =", BOT_TOKEN)
print("CHAT_ID =", CHAT_ID)
print("ZIP_CODE =", ZIP_CODE)

# -------- TELEGRAM -------- #

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": message})
    except Exception as e:
        print("Telegram error:", e)


# -------- TARGET -------- #

def check_target():
    deals = []

    url = "https://redsky.target.com/redsky_aggregations/v1/web/plp_search_v2"

    params = {
        "key": "9f36aeafbe60771d0a2fd6d6bdfeeb03",
        "keyword": "oatly",
        "channel": "WEB",
        "count": 24,
    }

    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json()

        for item in data.get("data", {}).get("search", {}).get("products", []):
            name = item["item"]["product_description"]["title"].lower()
            price = item["price"]["current_retail"]

            if "oatly" in name:
                if "barista" in name and price < 4:
                    deals.append(("Target", name, price))

                if "64" in name and price < 5:
                    deals.append(("Target", name, price))

    except Exception as e:
        print("Target error:", e)

    return deals


# -------- AMAZON -------- #

def check_amazon():
    deals = []

    headers = {"User-Agent": "Mozilla/5.0"}
    url = "https://www.amazon.com/s?k=oatly"

    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")

        for item in soup.select(".s-result-item"):
            title = item.select_one("h2")
            price = item.select_one(".a-price-whole")

            if title and price:
                name = title.text.lower()

                try:
                    price_val = float(price.text.replace(",", ""))
                except:
                    continue

                if "oatly" in name:
                    if "barista" in name and price_val < 4:
                        deals.append(("Amazon", name, price_val))

                    if "64" in name and price_val < 5:
                        deals.append(("Amazon", name, price_val))

    except Exception as e:
        print("Amazon error:", e)

    return deals


# -------- MAIN LOOP -------- #

seen = set()

def run_check():
    print("Checking deals...")

    all_deals = []

    for checker in [check_target, check_amazon]:
        deals = checker()

        for store, name, price in deals:
            key = f"{store}-{name}-{price}"

            if key not in seen:
                seen.add(key)
                all_deals.append((store, name, price))

    if all_deals:
        msg = "🛒 Oatly deals found:\n\n"

        for store, name, price in all_deals:
            msg += f"{store}\n${price} — {name}\n\n"

        send_telegram(msg)
        print("Alert sent")
    else:
        print("No deals found")


# -------- RAILWAY LOOP -------- #

if __name__ == "__main__":
    send_telegram("✅ Oatly bot is now running on Railway!")

    while True:
        run_check()
        time.sleep(1800)
    while True:
        run_check()
        time.sleep(1800)  # every 30 minutes
