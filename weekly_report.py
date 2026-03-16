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

COMPETITOR_CHANNELS = {
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
    "Anna Odyssey (3D)": "UC44AR7MVps8NNMHfxqf1z3Q",
    "CoColaCat (2D)": "CoColaCat",
    "Midnight Archive (Reddit)": "Midnights_Archives"
}

def get_channel_id(handle):
    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {"part": "id,statistics", "forHandle": handle, "key": YOUTUBE_API_KEY}
    r = requests.get(url, params=params).json()
    if "items" in r and r["items"]:
        return r["items"][0]["id"], r["items"][0].get("statistics", {})
    return None, {}

def get_videos_week(channel_id):
    published_after = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "channelId": channel_id,
        "publishedAfter": published_after,
        "order": "viewCount",
        "maxResults": 10,
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
    stats_r = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"part": "statistics,snippet", "id": ",".join(video_ids), "key": YOUTUBE_API_KEY}
    ).json()
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

def detect_outlier(views, avg):
    return views > avg * 3 if avg > 0 else False

def estimate_rpm(niche):
    rpms = {"3D": (3, 8), "2D": (2, 5), "Reddit": (2, 4)}
    for key in rpms:
        if key in niche:
            return rpms[key]
    return (2, 5)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for i in range(0, len(text), 4000):
        requests.post(url, json={"chat_id": MY_TELEGRAM_ID, "text": text[i:i+4000], "parse_mode": "HTML"})

def run_weekly_report():
    week_str = datetime.now().strftime("%d.%m.%Y")
    report = f"📊 <b>ЕЖЕНЕДЕЛЬНЫЙ СТРАТЕГИЧЕСКИЙ ОТЧЁТ</b>\nНеделя до {week_str}\n\n"

    all_data = {}

    for section, handles in COMPETITOR_CHANNELS.items():
        report += f"{'='*30}\n<b>{section}</b>\n{'='*30}\n\n"
        section_videos = []
        channel_summaries = []

        for handle in handles:
            channel_id, ch_stats = get_channel_id(handle)
            if not channel_id:
                continue

            videos = get_videos_week(channel_id)
            total_views = sum(v["views"] for v in videos)
            avg_views = total_views / len(videos) if videos else 0
            subs = int(ch_stats.get("subscriberCount", 0))

            rpm = estimate_rpm(section)
            earn_low = total_views / 1000 * rpm[0]
            earn_high = total_views / 1000 * rpm[1]

            outliers = [v for v in videos if detect_outlier(v["views"], avg_views)]

            channel_summaries.append({
                "handle": handle,
                "subs": subs,
                "videos_count": len(videos),
                "total_views": total_views,
                "avg_views": avg_views,
                "outliers": outliers,
                "earn_low": earn_low,
                "earn_high": earn_high,
                "top_video": videos[0] if videos else None
            })
            section_videos.extend(videos)

        channel_summaries.sort(key=lambda x: x["total_views"], reverse=True)

        for ch in channel_summaries:
            report += f"<b>@{ch['handle']}</b>\n"
            report += f"👥 {ch['subs']:,} подп. | 🎬 {ch['videos_count']} видео за неделю\n"
            report += f"👁 {ch['total_views']:,} просмотров | ⌀ {ch['avg_views']:,.0f}/видео\n"
            report += f"💰 Оценка заработка: ~${ch['earn_low']:.0f}–${ch['earn_high']:.0f}\n"

            if ch["outliers"]:
                report += f"🔥 OUTLIER:\n"
                for o in ch["outliers"][:2]:
                    report += f"  • {o['title']} — {o['views']:,} 👁\n"
                    report += f"    https://youtube.com/watch?v={o['id']}\n"

            if ch["top_video"] and not ch["outliers"]:
                report += f"🏆 Топ: {ch['top_video']['title']} — {ch['top_video']['views']:,} 👁\n"

            report += "\n"

        all_data[section] = channel_summaries

    report += "\n"

    prompt = f"""
Ты топовый YouTube стратег. Вот полные данные за неделю по конкурентам Влада в трёх нишах.

{report}

МОИ КАНАЛЫ ВЛАДА:
- Anna Odyssey (3D Shorts, стиль Zach D Films)
- CoColaCat (2D анимация)
- Midnight Archive (Reddit истории)

Сделай ПОЛНЫЙ стратегический отчёт:

1. ГЛАВНЫЕ ТРЕНДЫ НЕДЕЛИ (топ-3 темы/формата которые взорвались)
2. OUTLIER АНАЛИЗ (разбери каждый outlier — почему он взорвался, hook, структура)
3. НИША ПО НИШАМ:
   - 3D: что работало, что нет, средний RPM, лучший канал недели
   - 2D: что работало, что нет, лучший канал недели
   - Reddit: что работало, что нет, лучший канал недели
4. ТОП-5 ИДЕЙ ДЛЯ ANNA ODYSSEY на следующую неделю
5. ТОП-3 ИДЕИ ДЛЯ COCOLACAT на следующую неделю
6. ТОП-3 ИДЕИ ДЛЯ MIDNIGHT ARCHIVE на следующую неделю
7. СТРАТЕГИЧЕСКИЙ ВЫВОД — что делать Владу на следующей неделе (конкретные шаги)

Будь конкретным. Никакой воды. Только данные и выводы.
"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )

    full_report = report + f"\n🧠 <b>СТРАТЕГИЧЕСКИЙ АНАЛИЗ:</b>\n\n{response.content[0].text}"
    send_telegram(full_report)

if __name__ == "__main__":
    run_weekly_report()
