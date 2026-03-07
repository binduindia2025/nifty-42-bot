import os
import telebot
import pandas as pd
import yfinance as yf
import requests
import time
from datetime import datetime
import pytz

# ✅ FIXED: os.environ.get() takes the SECRET NAME, not the value
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID   = os.environ.get("CHAT_ID")
IST       = pytz.timezone("Asia/Kolkata")

def is_market_open():
    now = datetime.now(IST)
    if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False
    start = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    end   = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return start <= now <= end

def get_oi_levels():
    try:
        headers = {
            "User-Agent"     : "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer"        : "https://www.nseindia.com/"
        }
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        time.sleep(2)
        url  = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
        resp = session.get(url, headers=headers, timeout=10)
        data = resp.json()
        records = data['records']['data']
        df      = pd.DataFrame(records)
        df['CE_OI'] = df['CE'].apply(lambda x: x.get('openInterest', 0) if isinstance(x, dict) else 0)
        df['PE_OI'] = df['PE'].apply(lambda x: x.get('openInterest', 0) if isinstance(x, dict) else 0)
        support    = int(df.loc[df['PE_OI'].idxmax(), 'strikePrice'])
        resistance = int(df.loc[df['CE_OI'].idxmax(), 'strikePrice'])
        return support, resistance
    except Exception as e:
        print("OI error: " + str(e))
        return "N/A", "N/A"

def get_price_and_ema():
    try:
        data  = yf.download('^NSEI', interval='15m', period='5d', progress=False)
        close = data['Close'].dropna()
        open_ = data['Open'].dropna()

        price  = round(float(close.iloc[-1]), 1)
        open_p = round(float(open_.iloc[-1]),  1)
        high   = round(float(data['High'].dropna().iloc[-1]), 1)
        low    = round(float(data['Low'].dropna().iloc[-1]),  1)

        ema42  = round(float(close.ewm(span=42, adjust=False).mean().iloc[-1]), 1)
        ema8   = round(float(close.ewm(span=8,  adjust=False).mean().iloc[-1]), 1)

        return price, open_p, high, low, ema42, ema8
    except Exception as e:
        print("Price error: " + str(e))
        return None, None, None, None, None, None

def main():
    # ✅ FIXED: Proper validation with clear error messages
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN secret is missing or not set in GitHub Secrets.")
        return
    if not CHAT_ID:
        print("ERROR: CHAT_ID secret is missing or not set in GitHub Secrets.")
        return

    bot = telebot.TeleBot(BOT_TOKEN)

    if not is_market_open():
        now = datetime.now(IST).strftime("%H:%M")
        print("Market closed at " + now + " - exiting.")
        bot.send_message(CHAT_ID, f"Bot triggered at {now} IST, but market is closed.")
        return

    # Fetch Data
    support, resistance = get_oi_levels()
    price, open_p, high, low, ema42, ema8 = get_price_and_ema()

    if None in [price, open_p, ema42, ema8]:
        bot.send_message(CHAT_ID, "Price data fetch failed. Will retry next cycle.")
        return

    # --- SIGNAL LOGIC ---
    ce_signal = "HOLD / WAIT"
    pe_signal = "HOLD / WAIT"

    # CE Logic
    if open_p > ema42:
        ce_signal = "BUY CE Signal (Open > 42 EMA)"
    if open_p < ema8:
        ce_signal = "EXIT CE Signal (Open < 8 EMA)"

    # PE Logic
    if open_p < ema42:
        pe_signal = "BUY PE Signal (Open < 42 EMA)"
    if open_p > ema8:
        pe_signal = "EXIT PE Signal (Open > 8 EMA)"

    now = datetime.now(IST).strftime("%H:%M")

    msg = (
        f"NIFTY 50 | {now} IST (15m)\n"
        "------------------------\n"
        f"Open  : {open_p}\n"
        f"High  : {high}\n"
        f"Low   : {low}\n"
        f"Close : {price}\n"
        "------------------------\n"
        f"8 EMA  : {ema8}\n"
        f"42 EMA : {ema42}\n"
        "------------------------\n"
        "CE (CALL) STATUS:\n"
        f"-> {ce_signal}\n\n"
        "PE (PUT) STATUS:\n"
        f"-> {pe_signal}\n"
        "------------------------\n"
        f"Support (OI)    : {support}\n"
        f"Resistance (OI) : {resistance}\n"
    )

    bot.send_message(CHAT_ID, msg)
    print("Alert sent at " + now)

if __name__ == "__main__":
    main()
