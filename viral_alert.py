import os
import json
import requests
from datetime import datetime, timedelta
from anthropic import Anthropic

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MY_TELEGRAM_ID = os.getenv("MY_TELEGRAM_ID")

client = Anthropic(api_key=ANTHROPIC_KEY)

ALERT_FILE = "viral_seen.json"
VIRAL_MULTIPLIER = 5

ALL_CHANNELS = [
    "theartofwarrr", "ZeckFelms", "Shade_Scrolls", "AstryStudios",
    "Wholesomewendy", "TrickedEntertain", "Yarnhub", "AfrimaxEnglish",
    "fern-tv", "zackdfilms", "nykentertain", "TerraMystica-YT",
    "universo_labz", "doggyzuko", "CurioCatStories", "PinsGuy", "HoodieGuyStories",
    "Snook_YT", "tuchniyzhab", "upvotemedia"
]

def load_seen():
    if os.path.exists(ALERT_FILE):
        with open(ALERT_FILE, "r") as f:
            return json.load(f)
    return {}

def save_seen(data):
    with open(ALERT_FILE, "w") as f:
        json.dump(data, f)

def get_channel_id(handle):
    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {"part": "id,statistics", "forHandle": handle, "key": YOUTUBE_API_KEY}
    r = requests.get(url, params=params).json()
    if "items" in r and r["items"]:
        return r["items"][0]["id"], r["items"][0].get("statistics", {})
    return None, {}

def get_recent_videos(channel_id, hours=6):
    published_after = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "channelId": channel_id,
        "publishedAfter": published_after,
        "order": "date",
        "maxResults": 5,
        "type": "video",
        "key": YOUTUBE_API_KEY
    }
    r = requests.get(url, params=params).json()
    return r.get("items", [])

def get_video_stats(video_ids):
    if not video_ids:
        return {}
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {"part": "statistics,snippet", "id": ",".join(video_ids), "key": YOUTUBE_API_KEY}
    r = requests.get(url, params=params).json()
    return {item["id"]: item for item in r.get("items", [])}

def get_channel_avg_views(channel_id):
    published_after = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "id",
        "channelId": channel_id,
        "publishedAfter": published_after,
        "type": "video",
        "maxResults": 20,
        "key": YOUTUBE_API_KEY
    }
    r = requests.get(url, params=params).json()
    items = r.get("items", [])
    if not items:
        return 0
    video_ids = [v["id"]["videoId"] for v in items if "videoId" in v.get("id", {})]
    if not video_ids:
        return 0
    stats = get_video_stats(video_ids[:10])
    views = [int(v["statistics"].get("viewCount", 0)) for v in stats.values()]
    return sum(views) / len(views) if views else 0

def get_transcript(video_id):
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "en-US"])
        text = " ".join([t["text"] for t in transcript])
        return text[:3000]
    except Exception:
        return None

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for i in range(0, len(text), 4000):
        requests.post(url, json={"chat_id": MY_TELEGRAM_ID, "text": text[i:i+4000], "parse_mode": "HTML"})

def run_viral_check():
    seen = load_seen()

    for handle in ALL_CHANNELS:
        channel_id, _ = get_channel_id(handle)
        if not channel_id:
            continue

        videos = get_recent_videos(channel_id, hours=6)
        if not videos:
            continue

        video_ids = [v["id"]["videoId"] for v in videos if "videoId" in v.get("id", {})]
        if not video_ids:
            continue

        stats = get_video_stats(video_ids)
        avg_views = get_channel_avg_views(channel_id)

        for vid_id, item in stats.items():
            if vid_id in seen:
                continue

            views = int(item["statistics"].get("viewCount", 0))
            likes = int(item["statistics"].get("likeCount", 0))
            comments = int(item["statistics"].get("commentCount", 0))
            title = item["snippet"]["title"]

            if avg_views > 0 and views > avg_views * VIRAL_MULTIPLIER:
                multiplier = views / avg_views

                transcript = get_transcript(vid_id)

                alert = f"🚨 <b>ВИРУСНОЕ ВИДЕО ОБНАРУЖЕНО!</b>\n\n"
                alert += f"📺 Канал: @{handle}\n"
                alert += f"🎬 {title}\n"
                alert += f"👁 {views:,} просмотров\n"
                alert += f"❤️ {likes:,} | 💬 {comments:,}\n"
                alert += f"📈 В {multiplier:.1f}x больше среднего канала\n"
                alert += f"🔗 https://youtube.com/watch?v={vid_id}\n\n"

                if transcript:
                    prompt = f"""
Это транскрипция вирусного видео с YouTube канала @{handle}.
Видео набрало {views:,} просмотров — в {multiplier:.1f}x больше обычного.

ТРАНСКРИПЦИЯ:
{transcript}

Сделай быстрый анализ:
1. HOOK (первые 3-5 секунд) — что именно зацепило зрителя
2. СТРУКТУРА — как построено видео
3. ВИРУСНЫЙ ТРИГГЕР — почему это взорвалось
4. КАК АДАПТИРОВАТЬ для 3D анимации в стиле Zach D Films
5. ГОТОВЫЙ ЗАГОЛОВОК для похожего видео на Anna Odyssey
"""
                    response = client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=1000,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    alert += f"📝 <b>ТРАНСКРИПЦИЯ (фрагмент):</b>\n{transcript[:500]}...\n\n"
                    alert += f"🧠 <b>АНАЛИЗ:</b>\n{response.content[0].text}"
                else:
                    alert += "📝 Транскрипция недоступна для этого видео."

                send_telegram(alert)
                seen[vid_id] = {"handle": handle, "views": views, "date": datetime.now().isoformat()}

    save_seen(seen)

if __name__ == "__main__":
    run_viral_check()
