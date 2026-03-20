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

MY_CHANNELS = {
    "Anna Odyssey": "UClPEf1WtPs3WVlacsg0H7CA",
    "CoColaCat": "UCYnrKUlHqZRFB0kVF6HwQUw",
    "Midnight Archive": "UC44AR7MVps8NNMHfxqf1z3Q",
}

COMPETITOR_CHANNELS = [
    "theartofwarrr", "ZeckFelms", "Shade_Scrolls", "AstryStudios",
    "Wholesomewendy", "TrickedEntertain", "Yarnhub", "AfrimaxEnglish",
    "fern-tv", "zackdfilms", "nykentertain", "TerraMystica-YT",
    "universo_labz", "doggyzuko", "CurioCatStories", "PinsGuy",
    "HoodieGuyStories", "Snook_YT", "tuchniyzhab", "upvotemedia"
]

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for i in range(0, len(text), 4000):
        requests.post(url, json={"chat_id": MY_TELEGRAM_ID, "text": text[i:i+4000], "parse_mode": "HTML"})

def get_channel_id(handle):
    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {"part": "id,statistics,snippet", "forHandle": handle, "key": YOUTUBE_API_KEY}
    r = requests.get(url, params=params).json()
    if "items" in r and r["items"]:
        item = r["items"][0]
        return item["id"], item.get("statistics", {}), item.get("snippet", {})
    return None, {}, {}

def get_channel_videos(channel_id, days=30):
    published_after = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet", "channelId": channel_id,
        "publishedAfter": published_after, "order": "date",
        "maxResults": 50, "type": "video", "key": YOUTUBE_API_KEY
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
        params={"part": "statistics,snippet", "id": ",".join(video_ids[:50]), "key": YOUTUBE_API_KEY}
    ).json()
    videos = []
    for item in stats_r.get("items", []):
        pub = item["snippet"]["publishedAt"]
        videos.append({
            "title": item["snippet"]["title"],
            "views": int(item["statistics"].get("viewCount", 0)),
            "likes": int(item["statistics"].get("likeCount", 0)),
            "comments": int(item["statistics"].get("commentCount", 0)),
            "published": pub,
            "day": datetime.strptime(pub[:10], "%Y-%m-%d").strftime("%A"),
            "id": item["id"],
        })
    return videos

def run_monthly_report():
    now = datetime.now()
    month_name = now.strftime("%B %Y")

    send_telegram(f"📅 <b>МЕСЯЧНЫЙ ОТЧЁТ — {month_name}</b>\n\nСобираю данные... ⏳")

    # ===== КОНКУРЕНТЫ =====
    competitor_data = []
    all_titles = []
    day_counts = {"Monday": 0, "Tuesday": 0, "Wednesday": 0, "Thursday": 0, "Friday": 0, "Saturday": 0, "Sunday": 0}
    total_videos_competitors = 0

    for handle in COMPETITOR_CHANNELS:
        channel_id, stats, snippet = get_channel_id(handle)
        if not channel_id:
            continue
        subs = int(stats.get("subscriberCount", 0))
        videos = get_channel_videos(channel_id, days=30)
        if not videos:
            continue
        avg_views = sum(v["views"] for v in videos) / len(videos) if videos else 0
        top_video = max(videos, key=lambda x: x["views"]) if videos else None
        for v in videos:
            all_titles.append(v["title"])
            if v["day"] in day_counts:
                day_counts[v["day"]] += 1
        total_videos_competitors += len(videos)
        competitor_data.append({
            "handle": handle,
            "subs": subs,
            "videos_count": len(videos),
            "avg_views": avg_views,
            "top_video": top_video,
        })

    competitor_data.sort(key=lambda x: x["avg_views"], reverse=True)
    top_by_views = competitor_data[:3]

    subs_growth = sorted(competitor_data, key=lambda x: x["subs"], reverse=True)[:3]

    best_day = max(day_counts, key=day_counts.get) if day_counts else "Unknown"
    avg_videos_per_competitor = total_videos_competitors / len(competitor_data) if competitor_data else 0

    # ===== СВОИ КАНАЛЫ =====
    my_data = []
    for name, channel_id in MY_CHANNELS.items():
        if "placeholder" in channel_id:
            continue
        videos = get_channel_videos(channel_id, days=30)
        if not videos:
            continue
        avg_views = sum(v["views"] for v in videos) / len(videos) if videos else 0
        top_video = max(videos, key=lambda x: x["views"]) if videos else None
        my_data.append({
            "name": name,
            "videos_count": len(videos),
            "avg_views": avg_views,
            "top_video": top_video,
        })

    # ===== ФОРМИРУЕМ ОТЧЁТ =====
    report = f"📊 <b>МЕСЯЧНЫЙ ОТЧЁТ — {month_name}</b>\n\n"

    report += "━━━━━━━━━━━━━━━━\n"
    report += "🏆 <b>ТОП КОНКУРЕНТЫ ПО ПРОСМОТРАМ</b>\n\n"
    for i, c in enumerate(top_by_views, 1):
        report += f"{i}. @{c['handle']}\n"
        report += f"   ⌀ {c['avg_views']:,.0f} просм/видео | {c['videos_count']} видео\n"
        if c["top_video"]:
            report += f"   🔥 Лучшее: {c['top_video']['title'][:50]}\n"
            report += f"   👁 {c['top_video']['views']:,}\n"
        report += "\n"

    report += "━━━━━━━━━━━━━━━━\n"
    report += "📈 <b>ТОП ПО ПОДПИСЧИКАМ</b>\n\n"
    for i, c in enumerate(subs_growth, 1):
        report += f"{i}. @{c['handle']} — {c['subs']:,} подп.\n"

    report += f"\n━━━━━━━━━━━━━━━━\n"
    report += f"📅 <b>ЛУЧШИЙ ДЕНЬ ДЛЯ ПУБЛИКАЦИИ</b>\n"
    report += f"→ {best_day} ({day_counts.get(best_day, 0)} видео опубликовано конкурентами)\n\n"

    report += f"🎬 <b>СРЕДНЯЯ ЧАСТОТА ПУБЛИКАЦИЙ</b>\n"
    report += f"→ {avg_videos_per_competitor:.1f} видео/мес у топ конкурентов\n\n"

    if my_data:
        report += "━━━━━━━━━━━━━━━━\n"
        report += "📺 <b>ТВОИ КАНАЛЫ</b>\n\n"
        for ch in my_data:
            report += f"<b>{ch['name']}</b>\n"
            report += f"→ {ch['videos_count']} видео за месяц\n"
            report += f"→ ⌀ {ch['avg_views']:,.0f} просм/видео\n"
            if ch["top_video"]:
                report += f"→ 🔥 {ch['top_video']['title'][:50]}\n"
                report += f"   👁 {ch['top_video']['views']:,}\n"
            report += "\n"

    send_telegram(report)

    # ===== АНАЛИЗ ОТ АНИ =====
    prompt = f"""Месячный отчёт YouTube за {month_name}.

КОНКУРЕНТЫ:
- Топ по просмотрам: {', '.join([f"@{c['handle']} ({c['avg_views']:,.0f} ср/видео)" for c in top_by_views])}
- Всего видео у конкурентов за месяц: {total_videos_competitors}
- Средняя частота: {avg_videos_per_competitor:.1f} видео/мес
- Лучший день публикации: {best_day}
- Примеры топ заголовков: {chr(10).join(sorted(all_titles, key=lambda x: len(x))[:10])}

МОИ КАНАЛЫ:
{chr(10).join([f"- {ch['name']}: {ch['videos_count']} видео, ср. {ch['avg_views']:,.0f} просм" for ch in my_data]) if my_data else "Данные недоступны"}

Дай:
1. ТРЕНД МЕСЯЦА — что сейчас работает у конкурентов
2. ФОРМАТ МЕСЯЦА — какой формат заголовков/идей доминирует
3. СЛАБОЕ МЕСТО — где я отстаю от конкурентов
4. 3 КОНКРЕТНЫХ ДЕЙСТВИЯ на следующий месяц
5. НИША НА ПОДЪЁМЕ — что стоит попробовать судя по данным"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    analysis = f"🧠 <b>АНАЛИЗ ОТ АНИ</b>\n\n{response.content[0].text}"
    send_telegram(analysis)

if __name__ == "__main__":
    run_monthly_report()
