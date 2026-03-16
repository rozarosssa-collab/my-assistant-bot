import os
import requests
from datetime import datetime, timedelta
from anthropic import Anthropic

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MY_TELEGRAM_ID = os.getenv("MY_TELEGRAM_ID")

client = Anthropic(api_key=ANTHROPIC_KEY)

COMPETITOR_CHANNELS = {
    "3D (Anna Odyssey)": ["theartofwarrr", "ZeckFelms", "Shade_Scrolls", "AstryStudios",
                          "Wholesomewendy", "TrickedEntertain", "Yarnhub", "AfrimaxEnglish",
                          "fern-tv", "zackdfilms", "nykentertain", "TerraMystica-YT"],
    "2D (CoColaCat)": ["universo_labz", "doggyzuko", "CurioCatStories", "PinsGuy", "HoodieGuyStories"],
    "Reddit (Midnight Archive)": ["Snook_YT", "tuchniyzhab", "upvotemedia"]
}

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for i in range(0, len(text), 4000):
        requests.post(url, json={"chat_id": MY_TELEGRAM_ID, "text": text[i:i+4000], "parse_mode": "HTML"})

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
        "part": "snippet", "channelId": channel_id,
        "publishedAfter": published_after, "order": "viewCount",
        "maxResults": 10, "type": "video", "key": YOUTUBE_API_KEY
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
    if "3D" in niche:
        return (3, 8)
    elif "2D" in niche:
        return (2, 5)
    return (2, 4)

def run_weekly_report():
    week_end = datetime.now().strftime("%d.%m.%Y")
    week_start = (datetime.now() - timedelta(days=7)).strftime("%d.%m.%Y")

    header = f"📊 <b>ЕЖЕНЕДЕЛЬНЫЙ ОТЧЁТ</b>\n"
    header += f"📅 {week_start} — {week_end}\n"
    header += f"{'═'*30}\n\n"
    send_telegram(header)

    all_data_for_ai = ""

    for section, handles in COMPETITOR_CHANNELS.items():
        section_msg = f"{'─'*30}\n"
        section_msg += f"<b>📺 {section}</b>\n"
        section_msg += f"{'─'*30}\n\n"

        channel_summaries = []
        all_videos = []

        for handle in handles:
            channel_id, ch_stats = get_channel_id(handle)
            if not channel_id:
                continue
            videos = get_videos_week(channel_id)
            subs = int(ch_stats.get("subscriberCount", 0))
            total_views = sum(v["views"] for v in videos)
            avg_views = total_views / len(videos) if videos else 0
            rpm = estimate_rpm(section)
            earn_low = total_views / 1000 * rpm[0]
            earn_high = total_views / 1000 * rpm[1]
            outliers = [v for v in videos if detect_outlier(v["views"], avg_views)]

            channel_summaries.append({
                "handle": handle, "subs": subs,
                "videos_count": len(videos), "total_views": total_views,
                "avg_views": avg_views, "outliers": outliers,
                "earn_low": earn_low, "earn_high": earn_high,
                "top_video": videos[0] if videos else None
            })
            for v in videos:
                v["channel"] = handle
                all_videos.append(v)

        channel_summaries.sort(key=lambda x: x["total_views"], reverse=True)

        for ch in channel_summaries:
            if ch["total_views"] == 0:
                continue
            section_msg += f"<b>@{ch['handle']}</b>\n"
            section_msg += f"  👥 {ch['subs']:,} подп.\n"
            section_msg += f"  🎬 {ch['videos_count']} видео за неделю\n"
            section_msg += f"  👁 {ch['total_views']:,} просмотров\n"
            section_msg += f"  ⌀ {ch['avg_views']:,.0f} просмотров/видео\n"
            section_msg += f"  💰 ~${ch['earn_low']:.0f}–${ch['earn_high']:.0f} за неделю\n"

            if ch["outliers"]:
                for o in ch["outliers"][:1]:
                    section_msg += f"  🔥 OUTLIER: {o['title']}\n"
                    section_msg += f"     👁 {o['views']:,} | ❤️ {o['likes']:,} | 💬 {o['comments']:,}\n"
                    section_msg += f"     🔗 youtube.com/watch?v={o['id']}\n"
            elif ch["top_video"]:
                v = ch["top_video"]
                section_msg += f"  🏆 Топ: {v['title']}\n"
                section_msg += f"     👁 {v['views']:,}\n"
            section_msg += "\n"

        all_data_for_ai += f"\n{section}:\n"
        for v in sorted(all_videos, key=lambda x: x["views"], reverse=True)[:5]:
            all_data_for_ai += f"- @{v['channel']}: {v['title']} → {v['views']:,} просмотров\n"

        send_telegram(section_msg)

    prompt = f"""
Ты топовый YouTube стратег. Данные за неделю по конкурентам Влада:

{all_data_for_ai}

КАНАЛЫ ВЛАДА:
- Anna Odyssey (3D Shorts, стиль Zach D Films, США)
- CoColaCat (2D анимация)
- Midnight Archive (Reddit истории)

Анализ строго в формате:

🏆 ТОП-3 ФОРМАТА НЕДЕЛИ
1. [Формат]: [Почему взорвался — 1 предложение]
2. [Формат]: [Почему взорвался — 1 предложение]
3. [Формат]: [Почему взорвался — 1 предложение]

💥 OUTLIER РАЗБОР
[Для каждого outlier: hook + структура + причина]

📈 ИНСАЙТЫ ПО НИШАМ
3D: [Что работало / Что нет / Вывод]
2D: [Что работало / Что нет / Вывод]
Reddit: [Что работало / Что нет / Вывод]

🎯 ИДЕИ ДЛЯ ANNA ODYSSEY (5 идей)
1. [Название] | [Hook] | [Почему зайдёт]
2. [Название] | [Hook] | [Почему зайдёт]
3. [Название] | [Hook] | [Почему зайдёт]
4. [Название] | [Hook] | [Почему зайдёт]
5. [Название] | [Hook] | [Почему зайдёт]

🎨 ИДЕИ ДЛЯ COCOLACAT (3 идеи)
1. [Название] | [Hook] | [Почему зайдёт]
2. [Название] | [Hook] | [Почему зайдёт]
3. [Название] | [Hook] | [Почему зайдёт]

👾 ИДЕИ ДЛЯ MIDNIGHT ARCHIVE (3 идеи)
1. [Название] | [Тема] | [Почему зайдёт]
2. [Название] | [Тема] | [Почему зайдёт]
3. [Название] | [Тема] | [Почему зайдёт]

⚡ ДЕЙСТВИЯ НА СЛЕДУЮЩЕЙ НЕДЕЛЕ
1. [Конкретный шаг]
2. [Конкретный шаг]
3. [Конкретный шаг]
"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )

    analysis_msg = f"{'═'*30}\n"
    analysis_msg += f"🧠 <b>СТРАТЕГИЧЕСКИЙ АНАЛИЗ</b>\n"
    analysis_msg += f"{'═'*30}\n\n"
    analysis_msg += response.content[0].text
    send_telegram(analysis_msg)

if __name__ == "__main__":
    run_weekly_report()
