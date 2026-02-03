import os, json, re
import requests, feedparser
from datetime import datetime, timezone, timedelta
from dateutil import parser as dtparser

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]          # e.g. @SooSimpleIIT
YOUTUBE_CHANNEL_ID = os.environ["YOUTUBE_CHANNEL_ID"]      # e.g. UCxxxx...
LOOKBACK_HOURS = int(os.environ.get("LOOKBACK_HOURS", "24"))

STATE_FILE = "state.json"

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"posted": []}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def extract_video_id(url: str) -> str:
    # works for both /watch?v= and /shorts/
    m = re.search(r"(?:v=|/shorts/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else url

def is_within_last_hours(published_dt: datetime, hours: int) -> bool:
    now = datetime.now(timezone.utc)
    return published_dt >= (now - timedelta(hours=hours))

def format_message(title: str, desc: str, url: str) -> str:
    # Format like your screenshot (title + short desc + watch link)
    desc = (desc or "").strip()
    desc = re.sub(r"\s+", " ", desc)
    desc = desc[:220] + ("..." if len(desc) > 220 else "")  # short teaser line

    return (
        f"📌 {title}\n\n"
        f"{desc}\n\n"
        f"👉 Watch now: {url}"
    )

def telegram_send_message(text: str, disable_preview: bool = False):
    api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    r = requests.post(
        api,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "disable_web_page_preview": disable_preview
        },
        timeout=30
    )
    if r.status_code != 200:
        print("Telegram error:", r.status_code, r.text)
    r.raise_for_status()

def post_with_preview(title: str, desc: str, shorts_url: str, channel_url: str):
    # 1) Send only the shorts link (forces preview card)
    telegram_send_message(shorts_url, disable_preview=False)

    # small delay so Telegram fetches preview
    import time
    time.sleep(3)

    # 2) Send formatted text WITHOUT extra preview
    msg = (
        f"📌 {title}\n\n"
        f"{desc}\n\n"
        f"👉 Watch now: {shorts_url}\n"
        f"🔔 Subscribe: {channel_url}"
    )
    telegram_send_message(msg, disable_preview=True)


def main():
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}"
    feed = feedparser.parse(feed_url)

    state = load_state()
    posted = set(state.get("posted", []))

    cutoff_hours = LOOKBACK_HOURS

    candidates = []
    for e in feed.entries:
        url = e.link
        vid = extract_video_id(url)

        # published
        published_str = getattr(e, "published", None) or getattr(e, "updated", None)
        if not published_str:
            continue
        published_dt = dtparser.parse(published_str).astimezone(timezone.utc)

        if not is_within_last_hours(published_dt, cutoff_hours):
            continue
        if vid in posted:
            continue

        title = getattr(e, "title", "New upload")
        # description can be in summary
        desc = getattr(e, "summary", "") or ""
        desc = re.sub(r"<.*?>", "", desc)  # remove html tags

        candidates.append((published_dt, vid, title, desc, url))

    # newest first
    candidates.sort(key=lambda x: x[0], reverse=True)

    if not candidates:
        print("No new videos in last", cutoff_hours, "hours.")
        return

    # Post ALL new ones from last 24h (or just first one if you prefer)
    for published_dt, vid, title, desc, url in candidates:
        channel_url = "https://www.youtube.com/@ShubhamIITDelhi"  # your channel link
        post_with_preview(title, desc, url, channel_url)
        posted.add(vid)
        print("Posted:", vid, title)

    state["posted"] = list(posted)
    save_state(state)
    print("State updated.")

if __name__ == "__main__":
    main()
