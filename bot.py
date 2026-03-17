import os
import json
import tempfile
import asyncio
import requests
from dotenv import load_dotenv
from anthropic import Anthropic
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from analytics import run_daily_digest
from tracker import run_tracker
from weekly_report import run_weekly_report
from weekly_forecast import run_weekly_forecast, run_monday_plan
from viral_alert import run_viral_check, get_transcript
from calories import add_food, get_today_summary, reset_calories, run_daily_reset, DAILY_LIMIT
from redis_stats import update_tg_stats, update_whisper_stats

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")
MY_TELEGRAM_ID = int(os.getenv("MY_TELEGRAM_ID"))
OPENAI_KEY = os.getenv("OPENAI_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
HISTORY_FILE = "history.json"
MEMORY_FILE = "memory.txt"
MAX_HISTORY = 10

client = Anthropic(api_key=ANTHROPIC_KEY)

with open("system_prompt.txt", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

GUIDE_TEXT = """🤖 ANNA BOT — РУКОВОДСТВО

🎯 РЕЖИМЫ РАБОТЫ
Пиши в чат без команд, просто текст:

💡 режим: идеи — генерирует 10 идей для Shorts с описанием визуала, hook и причиной почему зайдёт

✍️ режим: скрипт — пишет полный скрипт с SSML тегами для ElevenLabs v3, готовый к озвучке

🔍 режим: анализ — присылаешь скрипт конкурента текстом, бот разбирает структуру и пишет твою адаптацию

🌀 режим: бенд — запускает методологию Niche Bending, генерирует нишевые бенды с заголовками

📊 режим: стратегия — думает как YouTube стратег, даёт план роста и контент-стратегию

🔥 режим: критик — жёстко и честно оценивает твои идеи или скрипты без смягчений

👾 режим: reddit — переключается на Midnight Archive, пишет и анализирует Reddit-формат

⚙️ АВТОМАТИЧЕСКИЕ КОМАНДЫ

📰 /digest — аналитика всех конкурентов за 24 часа. Автоматически в 9:00
📈 /tracker — статистика твоих каналов. Автоматически в 9:05
📊 /weekly — еженедельный отчёт. Автоматически вс 10:00
🚨 /viral — вирусные видео. Автоматически каждые 3 часа
🔮 /forecast — прогноз на неделю. Автоматически пт 18:00
📋 /plan — контент-план. Автоматически пн 9:10

🔧 РУЧНЫЕ КОМАНДЫ

🔬 /analyze ссылка — полный разбор видео конкурента
📝 /transcript ссылка — транскрипция YouTube видео
📋 /report username — полный разбор канала
🧠 /remember текст — запомнить навсегда
💾 /memory — показать память
🧹 /clear — очистить историю

🥗 КАЛЬКУЛЯТОР КАЛОРИЙ

/cal продукт — добавить еду и получить КБЖУ каждого продукта + общее
/today — полная сводка за сегодня
/caloreset — сбросить счётчик вручную
Лимит: 1800 ккал/день. Сбрасывается автоматически в 00:00.

📖 /guide или напиши "гайд" — показать руководство
🌐 Веб-версия: https://anna-bot-web.vercel.app
🎤 ГОЛОС — просто отправь голосовое"""

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def trim_history(history):
    return history[-MAX_HISTORY:]

def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def save_memory(text):
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n- {text}")

def is_authorized(update: Update) -> bool:
    return update.effective_user.id == MY_TELEGRAM_ID

def extract_video_id(url):
    if "v=" in url:
        return url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    return None

def get_channel_full_report(handle):
    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {"part": "statistics,snippet", "forHandle": handle, "key": YOUTUBE_API_KEY}
    r = requests.get(url, params=params).json()
    if not r.get("items"):
        return None, None, None
    item = r["items"][0]
    return item["statistics"], item["snippet"], item["id"]

def get_top_videos_channel(channel_id, max_results=10):
    from datetime import datetime, timedelta
    published_after = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet", "channelId": channel_id,
        "publishedAfter": published_after, "order": "viewCount",
        "maxResults": max_results, "type": "video", "key": YOUTUBE_API_KEY
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
            "id": item["id"],
            "published": item["snippet"]["publishedAt"][:10]
        })
    return sorted(videos, key=lambda x: x["views"], reverse=True)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("⛔ Доступ закрыт.")
        return
    user_text = update.message.text
    if user_text.lower().strip() in ["гайд", "guide", "руководство", "помощь", "help"]:
        await update.message.reply_text(GUIDE_TEXT)
        return
    if user_text.lower().strip() in ["начнем", "начнём", "старт", "привет", "го"]:
        await start(update, context)
        return
    await update.message.reply_text("⏳ Думаю...")
    history = load_history()
    history.append({"role": "user", "content": user_text})
    history = trim_history(history)
    memory = load_memory()
    system_with_memory = SYSTEM_PROMPT
    if memory:
        system_with_memory += f"\n\n== ДОЛГОСРОЧНАЯ ПАМЯТЬ ==\n{memory}"
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=system_with_memory,
        messages=history
    )
    reply = response.content[0].text
    history.append({"role": "assistant", "content": reply})
    save_history(history)
    try:
        update_tg_stats(response.usage.input_tokens, response.usage.output_tokens)
    except Exception:
        pass
    if len(reply) > 4000:
        parts = [reply[i:i+4000] for i in range(0, len(reply), 4000)]
        for part in parts:
            await update.message.reply_text(part)
    else:
        await update.message.reply_text(reply)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if not OPENAI_KEY:
        await update.message.reply_text("❌ OPENAI_KEY не настроен в Railway Variables.")
        return
    await update.message.reply_text("🎤 Транскрибирую...")
    voice = update.message.voice
    duration = voice.duration or 10
    file = await context.bot.get_file(voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        await file.download_to_drive(tmp.name)
        tmp_path = tmp.name
    with open(tmp_path, "rb") as audio_file:
        headers = {"Authorization": f"Bearer {OPENAI_KEY}"}
        files = {"file": ("voice.ogg", audio_file, "audio/ogg")}
        data = {"model": "whisper-1", "language": "ru"}
        r = requests.post("https://api.openai.com/v1/audio/transcriptions", headers=headers, files=files, data=data)
    os.unlink(tmp_path)
    if r.status_code != 200:
        await update.message.reply_text("❌ Ошибка транскрипции.")
        return
    text = r.json().get("text", "")
    try:
        update_whisper_stats(duration)
    except Exception:
        pass
    await update.message.reply_text(f"🎤 Ты сказал: {text}\n\n⏳ Думаю...")
    history = load_history()
    history.append({"role": "user", "content": text})
    history = trim_history(history)
    memory = load_memory()
    system_with_memory = SYSTEM_PROMPT
    if memory:
        system_with_memory += f"\n\n== ДОЛГОСРОЧНАЯ ПАМЯТЬ ==\n{memory}"
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=system_with_memory,
        messages=history
    )
    reply = response.content[0].text
    history.append({"role": "assistant", "content": reply})
    save_history(history)
    try:
        update_tg_stats(response.usage.input_tokens, response.usage.output_tokens)
    except Exception:
        pass
    if len(reply) > 4000:
        parts = [reply[i:i+4000] for i in range(0, len(reply), 4000)]
        for part in parts:
            await update.message.reply_text(part)
    else:
        await update.message.reply_text(reply)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "✅ Бот запущен.\n\n"
        "🎯 Режимы:\n"
        "💡 режим: идеи | ✍️ режим: скрипт\n"
        "🔍 режим: анализ | 🌀 режим: бенд\n"
        "📊 режим: стратегия | 🔥 режим: критик | 👾 режим: reddit\n\n"
        "⚙️ YouTube:\n"
        "/digest /tracker /weekly /viral /forecast /plan\n"
        "/analyze /transcript /report\n\n"
        "🥗 Калории:\n"
        "/cal [еда] — добавить и получить КБЖУ\n"
        "/today — сводка за сегодня\n"
        "/caloreset — сбросить счётчик\n\n"
        "/remember /memory /clear /guide\n\n"
        "🎤 Голосовые поддерживаются\n"
        "🌐 https://anna-bot-web.vercel.app"
    )

async def guide_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text(GUIDE_TEXT)

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    save_history([])
    await update.message.reply_text("🧹 История очищена.")

async def remember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Пример: /remember я перешёл в нишу космоса")
        return
    save_memory(text)
    await update.message.reply_text(f"✅ Запомнил: {text}")

async def show_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    memory = load_memory()
    if memory:
        await update.message.reply_text(f"💾 Моя память:\n{memory}")
    else:
        await update.message.reply_text("Память пустая.")

async def cal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if not context.args:
        await update.message.reply_text("Напиши что съел.\nПример: /cal овсянка 200г и банан")
        return
    food_text = " ".join(context.args)
    await update.message.reply_text("⏳ Считаю КБЖУ...")
    loop = asyncio.get_event_loop()
    items, total, over_limit = await loop.run_in_executor(None, add_food, food_text)
    if not items:
        await update.message.reply_text("❌ Не удалось определить КБЖУ. Попробуй написать точнее.")
        return
    msg = "🍽 ДОБАВЛЕНО:\n━━━━━━━━━━━━━━\n"
    for item in items:
        msg += f"\n{item['name']} ({item['amount']})\n"
        msg += f"  🔥 {item['calories']} ккал | 💪 Б:{item['protein']}г | 🧈 Ж:{item['fat']}г | 🍞 У:{item['carbs']}г\n"
    msg += f"\n━━━━━━━━━━━━━━\n"
    msg += f"📊 ИТОГО ЗА СЕГОДНЯ\n"
    msg += f"🔥 {total['calories']} / {DAILY_LIMIT} ккал\n"
    msg += f"💪 Б:{total['protein']}г | 🧈 Ж:{total['fat']}г | 🍞 У:{total['carbs']}г\n\n"
    if over_limit:
        over = total["calories"] - DAILY_LIMIT
        msg += f"⚠️ ЛИМИТ ПРЕВЫШЕН на {over} ккал!"
    else:
        remaining = DAILY_LIMIT - total["calories"]
        msg += f"✅ Осталось: {remaining} ккал"
    await update.message.reply_text(msg)

async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    data = get_today_summary()
    if not data["items"]:
        await update.message.reply_text("🥗 Сегодня ещё ничего не записано.\n\nДобавь еду: /cal продукт")
        return
    total = data["total"]
    remaining = DAILY_LIMIT - total["calories"]
    msg = f"📊 СВОДКА ЗА СЕГОДНЯ\n━━━━━━━━━━━━━━\n\n"
    for i, item in enumerate(data["items"], 1):
        msg += f"{i}. {item['name']} ({item['amount']})\n"
        msg += f"   🔥 {item['calories']} ккал | 💪 Б:{item['protein']}г | 🧈 Ж:{item['fat']}г | 🍞 У:{item['carbs']}г\n\n"
    msg += f"━━━━━━━━━━━━━━\n"
    msg += f"🔥 Итого: {total['calories']} / {DAILY_LIMIT} ккал\n"
    msg += f"💪 Белки: {total['protein']} г\n"
    msg += f"🧈 Жиры: {total['fat']} г\n"
    msg += f"🍞 Углеводы: {total['carbs']} г\n\n"
    if total["calories"] > DAILY_LIMIT:
        over = total["calories"] - DAILY_LIMIT
        msg += f"⚠️ ЛИМИТ ПРЕВЫШЕН на {over} ккал!"
    else:
        msg += f"✅ Осталось: {remaining} ккал"
    await update.message.reply_text(msg)

async def caloreset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    reset_calories()
    await update.message.reply_text("🔄 Счётчик калорий сброшен.\n\nЦель: 1800 ккал 🎯")

async def manual_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text("⏳ Генерирую еженедельный отчёт...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_weekly_report)

async def manual_tracker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text("⏳ Собираю статистику твоих каналов...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_tracker)

async def manual_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text("⏳ Запускаю аналитику конкурентов...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_daily_digest)

async def manual_viral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text("⏳ Проверяю вирусные видео...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_viral_check)

async def manual_forecast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text("⏳ Генерирую прогноз на следующую неделю...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_weekly_forecast)

async def manual_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text("⏳ Составляю контент-план...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_monday_plan)

async def transcript_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if not context.args:
        await update.message.reply_text("Пример: /transcript https://youtube.com/watch?v=xxxxx")
        return
    video_id = extract_video_id(context.args[0])
    if not video_id:
        await update.message.reply_text("Не могу извлечь ID видео.")
        return
    await update.message.reply_text("⏳ Получаю транскрипцию...")
    transcript = get_transcript(video_id)
    if not transcript:
        await update.message.reply_text("❌ Транскрипция недоступна.")
        return
    await update.message.reply_text(f"📝 Транскрипция:\n\n{transcript[:3500]}")

async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if not context.args:
        await update.message.reply_text("Пример: /analyze https://youtube.com/watch?v=xxxxx")
        return
    video_id = extract_video_id(context.args[0])
    if not video_id:
        await update.message.reply_text("Не могу извлечь ID видео.")
        return
    await update.message.reply_text("⏳ Анализирую видео...")
    transcript = get_transcript(video_id)
    if not transcript:
        await update.message.reply_text("❌ Транскрипция недоступна для этого видео.")
        return
    prompt = f"""Транскрипция YouTube видео конкурента:

{transcript}

Полный анализ:
1. HOOK (первые 3-5 сек)
2. СТРУКТУРА с таймингом
3. ВИРУСНЫЕ ТРИГГЕРЫ
4. ТЕМП
5. ЭМОЦИОНАЛЬНЫЙ ARC
6. СЛАБЫЕ МЕСТА
7. АДАПТАЦИЯ для Anna Odyssey
8. СКРИПТ-НАБРОСОК с SSML тегами
9. 3 ЗАГОЛОВКА"""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}]
    )
    try:
        update_tg_stats(response.usage.input_tokens, response.usage.output_tokens)
    except Exception:
        pass
    result = f"🔬 АНАЛИЗ ВИДЕО:\n\n{response.content[0].text}"
    if len(result) > 4000:
        parts = [result[i:i+4000] for i in range(0, len(result), 4000)]
        for part in parts:
            await update.message.reply_text(part)
    else:
        await update.message.reply_text(result)

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if not context.args:
        await update.message.reply_text("Пример: /report zackdfilms")
        return
    handle = context.args[0].replace("@", "")
    await update.message.reply_text(f"⏳ Анализирую @{handle}...")
    stats, snippet, channel_id = get_channel_full_report(handle)
    if not stats:
        await update.message.reply_text("❌ Канал не найден.")
        return
    subs = int(stats.get("subscriberCount", 0))
    total_views = int(stats.get("viewCount", 0))
    total_videos = int(stats.get("videoCount", 0))
    avg_per_video = total_views // total_videos if total_videos > 0 else 0
    top_videos = get_top_videos_channel(channel_id)
    avg_recent = sum(v["views"] for v in top_videos) / len(top_videos) if top_videos else 0
    outliers = [v for v in top_videos if v["views"] > avg_recent * 3]
    report = f"📋 ОТЧЁТ: @{handle}\n\n"
    report += f"👥 Подписчики: {subs:,}\n"
    report += f"👁 Всего просмотров: {total_views:,}\n"
    report += f"🎬 Всего видео: {total_videos}\n"
    report += f"⌀ Просмотров/видео: {avg_per_video:,}\n"
    report += f"⌀ За 30 дней: {avg_recent:,.0f}/видео\n"
    report += f"🔥 Outliers: {len(outliers)}\n\n"
    if top_videos:
        report += f"🏆 Топ видео за 30 дней:\n"
        for i, v in enumerate(top_videos[:5], 1):
            tag = " 🔥" if v in outliers else ""
            report += f"{i}. {v['title']}{tag}\n"
            report += f"   👁 {v['views']:,} | ❤️ {v['likes']:,} | 💬 {v['comments']:,}\n"
            report += f"   📅 {v['published']}\n\n"
    prompt = f"""YouTube стратег. Данные канала @{handle}:
Подписчики: {subs:,} | Просмотры: {total_views:,} | Видео за 30 дней: {len(top_videos)}
Средние: {avg_recent:,.0f} | Outliers: {len(outliers)}
Топ: {chr(10).join([f"- {v['title']}: {v['views']:,}" for v in top_videos[:5]])}

Анализ: ниша, частота, что работает, что нет, outlier разбор, 3 идеи для Anna Odyssey."""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    try:
        update_tg_stats(response.usage.input_tokens, response.usage.output_tokens)
    except Exception:
        pass
    report += f"🧠 АНАЛИЗ:\n\n{response.content[0].text}"
    if len(report) > 4000:
        parts = [report[i:i+4000] for i in range(0, len(report), 4000)]
        for part in parts:
            await update.message.reply_text(part)
    else:
        await update.message.reply_text(report)

async def scheduled_digest():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_daily_digest)

async def scheduled_tracker():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_tracker)

async def scheduled_viral():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_viral_check)

async def scheduled_calorie_reset():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_daily_reset)

async def post_init(application):
    scheduler = AsyncIOScheduler()
    kyiv_tz = pytz.timezone("Europe/Kiev")
    scheduler.add_job(scheduled_digest, CronTrigger(hour=9, minute=0, timezone=kyiv_tz), misfire_grace_time=300)
    scheduler.add_job(scheduled_tracker, CronTrigger(hour=9, minute=5, timezone=kyiv_tz), misfire_grace_time=300)
    scheduler.add_job(run_monday_plan, CronTrigger(day_of_week="mon", hour=9, minute=10, timezone=kyiv_tz), misfire_grace_time=300)
    scheduler.add_job(run_weekly_report, CronTrigger(day_of_week="sun", hour=10, minute=0, timezone=kyiv_tz), misfire_grace_time=300)
    scheduler.add_job(run_weekly_forecast, CronTrigger(day_of_week="fri", hour=18, minute=0, timezone=kyiv_tz), misfire_grace_time=300)
    scheduler.add_job(scheduled_viral, CronTrigger(hour="*/3", timezone=kyiv_tz), misfire_grace_time=300)
    scheduler.add_job(scheduled_calorie_reset, CronTrigger(hour=0, minute=0, timezone=kyiv_tz), misfire_grace_time=300)
    scheduler.start()

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("guide", guide_command))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(CommandHandler("digest", manual_digest))
    app.add_handler(CommandHandler("tracker", manual_tracker))
    app.add_handler(CommandHandler("weekly", manual_weekly))
    app.add_handler(CommandHandler("viral", manual_viral))
    app.add_handler(CommandHandler("forecast", manual_forecast))
    app.add_handler(CommandHandler("plan", manual_plan))
    app.add_handler(CommandHandler("transcript", transcript_command))
    app.add_handler(CommandHandler("analyze", analyze_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("remember", remember))
    app.add_handler(CommandHandler("memory", show_memory))
    app.add_handler(CommandHandler("cal", cal_command))
    app.add_handler(CommandHandler("today", today_command))
    app.add_handler(CommandHandler("caloreset", caloreset_command))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
