import os
import json
import requests
from datetime import datetime
from anthropic import Anthropic

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MY_TELEGRAM_ID = os.getenv("MY_TELEGRAM_ID")

client = Anthropic(api_key=ANTHROPIC_KEY)

MY_CHANNELS = {
    "Anna Odyssey (3D)": "UC44AR7MVps8NNMHfxqf1z3Q",
    "CoColaCat (2D)": "CoColaCat",
    "Midnight Archive (Reddit)": "Midnights_Archives"
}

STATS_FILE = "channel_stats_history.json"

RPM_ESTIMATES = {
    "Anna Odyssey (3D)": (3, 8),
    "CoColaCat (2D)": (2, 5),
    "Midnight Archive (Reddit)": (2, 4)
}

def load_stats_history():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_stats_history(data):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_channel_stats_by_id(channel_id):
    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {
        "part": "statistics,snippet",
        "id": channel_id,
        "key": YOUTUBE_API_KEY
    }
    r = requests.get(url, params=params).json()
    if "items" in r and r["items"]:
        item = r["items"][0]
        return item["statistics"], item["snippet"]
    return {}, {}

def get_channel_stats_by_handle(handle):
    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {
        "part": "statistics,snippet",
        "forHandle": handle,
        "key": YOUTUBE_API_KEY
    }
    r = requests.get(url, params=params).json()
    if "items" in r and r["items"]:
        item = r["items"][0]
        return item["statistics"], item["snippet"], item["id"]
    return {}, {}, None

def get_top_videos_week(channel_id):
    from datetime import timedelta
    published_after = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "channelId": channel_id,
        "publishedAfter": published_after,
        "order": "viewCount",
        "maxResults": 3,
        "type": "video",
        "key": YOUTUBE_API_KEY
    }
    r = requests.get(url, params=params).json()
    items = r.get("items", [])
    if not items:
        return []
    video_ids = [v["id"]["videoId"] for v in items if "videoId" in v.get("id", {})]
    if not video_ids:
        return []
    stats_url = "https://www.googleapis.com/youtube/v3/videos"
    stats_params = {
        "part": "statistics,snippet",
        "id": ",".join(video_ids),
        "key": YOUTUBE_API_KEY
    }
    stats_r = requests.get(stats_url, params=stats_params).json()
    videos = []
    for item in stats_r.get("items", []):
        videos.append({
            "title": item["snippet"]["title"],
            "views": int(item["statistics"].get("viewCount", 0)),
            "likes": int(item["statistics"].get("likeCount", 0)),
            "comments": int(item["statistics"].get("commentCount", 0)),
            "id": item["id"]
        })
    return sorted(videos, key=lambda x: x["views"], reverse=True)

def estimate_earnings(views, rpm_range):
    low = views / 1000 * rpm_range[0]
    high = views / 1000 * rpm_range[1]
    return low, high

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    max_len = 4000
    for i in range(0, len(text), max_len):
        requests.post(url, json={
            "chat_id": MY_TELEGRAM_ID,
            "text": text[i:i+max_len],
            "parse_mode": "HTML"
        })

def run_tracker():
    today = datetime.now().strftime("%Y-%m-%d")
    history = load_stats_history()
    report = f"📈 <b>ТРЕКЕР ТВОИХ КАНАЛОВ — {datetime.now().strftime('%d %B %Y')}</b>\n\n"

    channel_ids = {
        "Anna Odyssey (3D)": "UC44AR7MVps8NNMHfxqf1z3Q",
        "CoColaCat (2D)": None,
        "Midnight Archive (Reddit)": None
    }
    handles = {
        "CoColaCat (2D)": "CoColaCat",
        "Midnight Archive (Reddit)": "Midnights_Archives"
    }

    for name, channel_id in channel_ids.items():
        if channel_id is None:
            stats, snippet, channel_id = get_channel_stats_by_handle(handles[name])
        else:
            stats, snippet = get_channel_stats_by_id(channel_id)

        if not stats:
            report += f"❌ {name} — не удалось получить данные\n\n"
            continue

        subs = int(stats.get("subscriberCount", 0))
        total_views = int(stats.get("viewCount", 0))
        total_videos = int(stats.get("videoCount", 0))

        prev = history.get(name, {})
        prev_subs = prev.get("subs", subs)
        prev_views = prev.get("views", total_views)
        prev_date = prev.get("date", today)

        day_diff = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(prev_date, "%Y-%m-%d")).days
        if day_diff == 0:
            day_diff = 1

        subs_day = subs - prev_subs
        views_day = total_views - prev_views

        top_videos = get_top_videos_week(channel_id) if channel_id else []

        rpm_range = RPM_ESTIMATES.get(name, (2, 5))
        week_views = sum(v["views"] for v in top_videos)
        earn_low, earn_high = estimate_earnings(week_views, rpm_range)

        report += f"<b>{name}</b>\n"
        report += f"👥 Подписчики: {subs:,} "
        report += f"({'+'if subs_day>=0 else ''}{subs_day:,} за день)\n"
        report += f"👁 Просмотры всего: {total_views:,} "
        report += f"({'+'if views_day>=0 else ''}{views_day:,} за день)\n"
        report += f"🎬 Видео на канале: {total_videos}\n"
        report += f"💰 Оценка заработка за неделю: ~${earn_low:.0f}–${earn_high:.0f}\n"

        if top_videos:
            report += f"\n🏆 Топ видео за 7 дней:\n"
            for i, v in enumerate(top_videos[:3], 1):
                report += f"{i}. {v['title']}\n"
                report += f"   👁 {v['views']:,} | ❤️ {v['likes']:,} | 💬 {v['comments']:,}\n"
                report += f"   https://youtube.com/watch?v={v['id']}\n"

        report += "\n"

        history[name] = {
            "subs": subs,
            "views": total_views,
            "date": today
        }

    save_stats_history(history)

    prompt = f"""
Ты YouTube стратег. Вот данные по трём каналам Влада за сегодня:

{report}

Дай короткий (3-5 предложений) стратегический вывод:
- Какой канал растёт быстрее всех и почему это хорошо/плохо
- Что нужно сделать на следующей неделе чтобы ускорить рост
- Один конкретный совет по каждому каналу
"""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    analysis = response.content[0].text
    report += f"🧠 <b>Стратегический анализ:</b>\n{analysis}"

    send_telegram(report)

if __name__ == "__main__":
    run_tracker()
