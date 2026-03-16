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
    "3D": ["theartofwarrr", "ZeckFelms", "Shade_Scrolls", "AstryStudios",
           "Wholesomewendy", "TrickedEntertain", "Yarnhub", "AfrimaxEnglish",
           "fern-tv", "zackdfilms", "nykentertain", "TerraMystica-YT"],
    "2D": ["universo_labz", "doggyzuko", "CurioCatStories", "PinsGuy", "HoodieGuyStories"],
    "Reddit": ["Snook_YT", "tuchniyzhab", "upvotemedia"]
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

def get_top_videos(channel_id, days=7):
    published_after = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet", "channelId": channel_id,
        "publishedAfter": published_after, "order": "viewCount",
        "maxResults": 5, "type": "video", "key": YOUTUBE_API_KEY
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
            "id": item["id"]
        })
    return sorted(videos, key=lambda x: x["views"], reverse=True)

def collect_week_data():
    data = {}
    for niche, handles in COMPETITOR_CHANNELS.items():
        niche_videos = []
        for handle in handles:
            channel_id, _ = get_channel_id(handle)
            if not channel_id:
                continue
            videos = get_top_videos(channel_id, days=7)
            for v in videos:
                v["channel"] = handle
                niche_videos.append(v)
        data[niche] = sorted(niche_videos, key=lambda x: x["views"], reverse=True)
    return data

def run_weekly_forecast():
    data = collect_week_data()
    top_videos_text = ""
    for niche, videos in data.items():
        top_videos_text += f"\n{niche.upper()} НИША — топ видео недели:\n"
        for v in videos[:5]:
            top_videos_text += f"- @{v['channel']}: {v['title']} → {v['views']:,} просмотров\n"

    prompt = f"""
Ты топовый YouTube стратег. Сейчас пятница — время прогнозировать следующую неделю.

Вот топ видео конкурентов за последние 7 дней:
{top_videos_text}

КАНАЛЫ ВЛАДА:
- Anna Odyssey (3D Shorts, стиль Zach D Films, аудитория США)
- CoColaCat (2D анимация)
- Midnight Archive (Reddit истории)

Сделай ПРОГНОЗ НА СЛЕДУЮЩУЮ НЕДЕЛЮ в таком формате:

🔮 ПРОГНОЗ ТРЕНДОВ
Какие темы и форматы скорее всего взорвутся на следующей неделе и почему (3-5 пунктов, каждый с обоснованием на основе данных)

📊 ПАТТЕРНЫ КОТОРЫЕ ПОВТОРЯТСЯ
Что работало эту неделю и точно будет работать снова

⚡ ОКНА ВОЗМОЖНОСТЕЙ
Темы которые конкуренты НЕ покрыли но аудитория точно хочет

🎯 ПРИОРИТЕТЫ ДЛЯ ANNA ODYSSEY (3 идеи)
Для каждой: Название | Почему именно сейчас | Hook первые 3 секунды

🎨 ПРИОРИТЕТЫ ДЛЯ COCOLACAT (2 идеи)
Для каждой: Название | Почему именно сейчас

👾 ПРИОРИТЕТЫ ДЛЯ MIDNIGHT ARCHIVE (2 идеи)
Для каждой: Название | Почему именно сейчас

⚠️ ЧЕГО ИЗБЕГАТЬ
Форматы и темы которые показали плохой результат — не тратить время

Будь конкретным. Только данные и выводы. Никакой воды.
"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}]
    )

    date_str = datetime.now().strftime("%d.%m.%Y")
    next_week = (datetime.now() + timedelta(days=7)).strftime("%d.%m.%Y")

    msg = f"🔮 <b>ПРОГНОЗ НА НЕДЕЛЮ</b>\n"
    msg += f"📅 {date_str} → {next_week}\n"
    msg += f"{'─'*30}\n\n"
    msg += response.content[0].text

    send_telegram(msg)

def run_monday_plan():
    data = collect_week_data()
    top_videos_text = ""
    for niche, videos in data.items():
        top_videos_text += f"\n{niche.upper()}:\n"
        for v in videos[:3]:
            top_videos_text += f"- @{v['channel']}: {v['title']} → {v['views']:,} просмотров\n"

    prompt = f"""
Ты YouTube стратег. Сегодня понедельник — начало рабочей недели.

Топ видео конкурентов за прошлую неделю:
{top_videos_text}

КАНАЛЫ ВЛАДА:
- Anna Odyssey (3D Shorts, стиль Zach D Films, США)
- CoColaCat (2D анимация)
- Midnight Archive (Reddit истории)

Составь КОНТЕНТ-ПЛАН НА НЕДЕЛЮ в таком формате:

📋 КОНТЕНТ-ПЛАН — ПОНЕДЕЛЬНИК→ВОСКРЕСЕНЬЕ

ANNA ODYSSEY (3D):
ПН: [Название видео] | [Hook 3 сек] | [Почему зайдёт]
СР: [Название видео] | [Hook 3 сек] | [Почему зайдёт]
ПТ: [Название видео] | [Hook 3 сек] | [Почему зайдёт]

COCOLACAT (2D):
ВТ: [Название видео] | [Hook 3 сек] | [Почему зайдёт]
ЧТ: [Название видео] | [Hook 3 сек] | [Почему зайдёт]

MIDNIGHT ARCHIVE (Reddit):
СР: [Название видео] | [Тема истории] | [Почему зайдёт]
СБ: [Название видео] | [Тема истории] | [Почему зайдёт]

🎯 ГЛАВНЫЙ ФОКУС НЕДЕЛИ
Одна самая важная вещь которую нужно сделать на этой неделе

⚡ БЫСТРАЯ ПОБЕДА
Самое простое видео которое можно снять за день и которое точно наберёт просмотры

Только конкретные названия. Никаких абстракций.
"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    date_str = datetime.now().strftime("%d.%m.%Y")

    msg = f"📋 <b>КОНТЕНТ-ПЛАН НЕДЕЛИ</b>\n"
    msg += f"📅 Неделя от {date_str}\n"
    msg += f"{'─'*30}\n\n"
    msg += response.content[0].text

    send_telegram(msg)

if __name__ == "__main__":
    run_weekly_forecast()
