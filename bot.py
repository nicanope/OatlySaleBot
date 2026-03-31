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


# -----------------------------
# PRODUCTS
# -----------------------------
PRODUCTS = [
    {
        "store": "Amazon",
        "label": "Oatly Barista 32oz",
        "threshold": 4.00,
        "url": "https://www.amazon.com/s?k=oatly+barista+32",
    },
    {
        "store": "Amazon",
        "label": "Oatly 64oz",
        "threshold": 5.00,
        "url": "https://www.amazon.com/s?k=oatly+64+oz",
    },
    {
        "store": "Target",
        "label": "Oatly Barista 32oz",
        "threshold": 4.00,
        "url": "https://www.target.com/s?searchTerm=oatly+barista",
    },
    {
        "store": "H-E-B",
        "label": "Oatly",
        "threshold": 5.00,
        "url": "https://www.heb.com/search?q=oatly",
    },
    {
        "store": "Randalls",
        "label": "Oatly",
        "threshold": 5.00,
        "url": "https://www.randalls.com/shop/search-results.html?q=oatly",
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
    )

    print("Telegram:", response.status_code)


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

    response = requests.get("https://api.scrape.do/", params=params, timeout=90)
    response.raise_for_status()
    return response.text

# -----------------------------
# PRICE PARSER
# -----------------------------
def extract_price(text):

    matches = re.findall(r"\$(\d+\.\d{2})", text)

    prices = []

    for m in matches:
        try:
            value = float(m)

            if 1 < value < 20:
                prices.append(value)

        except:
            pass

    if prices:
        return min(prices)

    return None


# -----------------------------
# STATE
# -----------------------------
def load_state():

    if not STATE_FILE.exists():
        return {}

    return json.loads(STATE_FILE.read_text())


def save_state(state):

    STATE_FILE.write_text(json.dumps(state))


# -----------------------------
# CHECK
# -----------------------------
def check():

    print("Checking deals...")

    state = load_state()

    alerts = []

    for product in PRODUCTS:

        try:

            html = fetch_html(product["url"])

            soup = BeautifulSoup(html, "html.parser")

            text = soup.get_text()

            price = extract_price(text)

            print(product["store"], price)

            if price is None:
                continue

            if price <= product["threshold"]:

                old = state.get(product["url"])

                if old == price:
                    continue

                alerts.append(
                    f"{product['store']} ${price}\n{product['url']}"
                )

                state[product["url"]] = price

        except Exception as e:

            print("Error:", e)

    if alerts:

        message = "🛒 Oatly Deals\n\n" + "\n\n".join(alerts)

        send_telegram(message)

    save_state(state)


# -----------------------------
# LOOP
# -----------------------------
if __name__ == "__main__":

    while True:

        check()

        time.sleep(CHECK_EVERY_MINUTES * 60)