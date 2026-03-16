import os
import requests
from datetime import datetime, timedelta
from anthropic import Anthropic

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MY_TELEGRAM_ID = os.getenv("MY_TELEGRAM_ID")

client = Anthropic(api_key=ANTHROPIC_KEY)

CHANNELS = {
    "3D (Anna Odyssey)": [
        "theartofwarrr", "ZeckFelms", "Shade_Scrolls", "AstryStudios",
        "Wholesomewendy", "TrickedEntertain", "Yarnhub", "AfrimaxEnglish",
        "fern-tv", "zackdfilms", "nykentertain", "TerraMystica-YT"
    ],
    "2D (CoColaCat)": [
        "universo_labz", "doggyzuko", "CurioCatStories", "PinsGuy", "HoodieGuyStories"
    ],
    "Reddit (Midnight Archive)": [
        "Snook_YT", "tuchniyzhab", "upvotemedia"
    ]
}

MY_CHANNELS = {
    "3D": "Anna Odyssey — кинематографичные 3D Shorts в стиле Zach D Films",
    "2D": "CoColaCat — 2D анимация",
    "Reddit": "Midnight Archive — Reddit истории"
}

def get_channel_id(username):
    url = f"https://www.googleapis.com/youtube/v3/channels"
    params = {"part": "id,statistics", "forHandle": username, "key": YOUTUBE_API_KEY}
    r = requests.get(url, params=params).json()
    if "items" in r and r["items"]:
        return r["items"][0]["id"], r["items"][0].get("statistics", {})
    return None, {}

def get_recent_videos(channel_id, days=1):
    published_after = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "channelId": channel_id,
        "publishedAfter": published_after,
        "order": "date",
        "maxResults": 10,
        "type": "video",
        "key": YOUTUBE_API_KEY
    }
    r = requests.get(url, params=params).json()
    return r.get("items", [])

def get_video_stats(video_ids):
    if not video_ids:
        return {}
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {"part": "statistics", "id": ",".join(video_ids), "key": YOUTUBE_API_KEY}
    r = requests.get(url, params=params).json()
    return {item["id"]: item["statistics"] for item in r.get("items", [])}

def get_channel_weekly_stats(channel_id):
    url = "https://www.googleapis.com/youtube/v3/search"
    published_after = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "part": "snippet",
        "channelId": channel_id,
        "publishedAfter": published_after,
        "order": "date",
        "maxResults": 50,
        "type": "video",
        "key": YOUTUBE_API_KEY
    }
    r = requests.get(url, params=params).json()
    return len(r.get("items", []))

def detect_outlier(views, avg_views):
    if avg_views == 0:
        return False
    return views > avg_views * 3

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    max_len = 4000
    for i in range(0, len(text), max_len):
        requests.post(url, json={"chat_id": MY_TELEGRAM_ID, "text": text[i:i+max_len], "parse_mode": "HTML"})

def build_digest_for_section(section_name, usernames, my_channel_desc):
    all_videos_data = []
    channel_weekly = []

    for username in usernames:
        channel_id, ch_stats = get_channel_id(username)
        if not channel_id:
            continue

        videos = get_recent_videos(channel_id, days=1)
        video_ids = [v["id"]["videoId"] for v in videos if "videoId" in v.get("id", {})]
        stats = get_video_stats(video_ids)
        weekly_count = get_channel_weekly_stats(channel_id)

        subs = ch_stats.get("subscriberCount", "?")
        channel_weekly.append(f"• @{username}: {weekly_count} видео за неделю | {subs} подписчиков")

        for v in videos:
            vid_id = v.get("id", {}).get("videoId")
            if not vid_id:
                continue
            title = v["snippet"]["title"]
            vs = stats.get(vid_id, {})
            views = int(vs.get("viewCount", 0))
            likes = int(vs.get("likeCount", 0))
            comments = int(vs.get("commentCount", 0))
            all_videos_data.append({
                "channel": username,
                "title": title,
                "views": views,
                "likes": likes,
                "comments": comments,
                "vid_id": vid_id
            })

    if not all_videos_data:
        return f"📊 {section_name}\n\nНет новых видео за последние 24 часа."

    avg_views = sum(v["views"] for v in all_videos_data) / len(all_videos_data) if all_videos_data else 0

    videos_text = ""
    for v in sorted(all_videos_data, key=lambda x: x["views"], reverse=True):
        outlier = "🔥 OUTLIER" if detect_outlier(v["views"], avg_views) else ""
        videos_text += f"\n• @{v['channel']} — {v['title']}\n  👁 {v['views']:,} | ❤️ {v['likes']:,} | 💬 {v['comments']:,} {outlier}\n  https://youtube.com/watch?v={v['vid_id']}\n"

    weekly_text = "\n".join(channel_weekly)

    prompt = f"""
Ты YouTube стратег. Вот данные по конкурентам в нише "{section_name}".

МОЙ КАНАЛ: {my_channel_desc}

НОВЫЕ ВИДЕО ЗА 24 ЧАСА:
{videos_text}

СРЕДНИЕ ПРОСМОТРЫ: {avg_views:.0f}

Сделай:
1. Какая тема/формат показал лучший результат сегодня и почему (2-3 предложения)
2. Предложи 5 конкретных идей для моего канала основанных на успешных видео конкурентов
   Формат каждой идеи: Название | Почему зайдёт | Hook первые 3 секунды
"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    analysis = response.content[0].text

    digest = f"""📊 <b>{section_name}</b> — {datetime.now().strftime('%d %B %Y')}

📺 <b>Новые видео за 24 часа:</b>
{videos_text}

📈 <b>Недельная статистика:</b>
{weekly_text}

💡 <b>Анализ и идеи от Claude:</b>
{analysis}
"""
    return digest

def run_daily_digest():
    send_telegram(f"🌅 Доброе утро! Готовлю аналитику по {sum(len(v) for v in CHANNELS.values())} каналам...")

    for section, usernames in CHANNELS.items():
        my_desc = MY_CHANNELS.get(section.split()[0], "")
        digest = build_digest_for_section(section, usernames, my_desc)
        send_telegram(digest)

    send_telegram("✅ Дайджест готов. Удачного дня!")

if __name__ == "__main__":
    run_daily_digest()
