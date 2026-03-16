import os
import json
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
from viral_alert import run_viral_check, get_transcript, send_telegram

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")
MY_TELEGRAM_ID = int(os.getenv("MY_TELEGRAM_ID"))
HISTORY_FILE = "history.json"
MEMORY_FILE = "memory.txt"
MAX_HISTORY = 30

client = Anthropic(api_key=ANTHROPIC_KEY)

with open("system_prompt.txt", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("⛔ Доступ закрыт.")
        return
    user_text = update.message.text
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
        "Режимы:\n"
        "режим: идеи\nрежим: скрипт\nрежим: анализ\nрежим: бенд\n"
        "режим: стратегия\nрежим: критик\nрежим: reddit\n\n"
        "Команды:\n"
        "/clear — очистить историю\n"
        "/digest — аналитика конкурентов\n"
        "/tracker — статистика твоих каналов\n"
        "/weekly — еженедельный отчёт\n"
        "/viral — проверить вирусные видео сейчас\n"
        "/transcript ссылка — транскрипция видео\n"
        "/remember текст — запомнить навсегда\n"
        "/memory — показать память"
    )

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
        await update.message.reply_text("Напиши что запомнить.\nПример: /remember я перешёл в нишу космоса")
        return
    save_memory(text)
    await update.message.reply_text(f"✅ Запомнил: {text}")

async def show_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    memory = load_memory()
    if memory:
        await update.message.reply_text(f"🧠 Моя память:\n{memory}")
    else:
        await update.message.reply_text("Память пустая.")

async def manual_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text("⏳ Генерирую еженедельный отчёт...")
    run_weekly_report()

async def manual_tracker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text("⏳ Собираю статистику твоих каналов...")
    run_tracker()

async def manual_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text("⏳ Запускаю аналитику конкурентов...")
    run_daily_digest()

async def manual_viral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text("⏳ Проверяю вирусные видео...")
    run_viral_check()

async def transcript_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if not context.args:
        await update.message.reply_text("Укажи ссылку.\nПример: /transcript https://youtube.com/watch?v=xxxxx")
        return
    url = context.args[0]
    video_id = None
    if "v=" in url:
        video_id = url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in url:
        video_id = url.split("youtu.be/")[1].split("?")[0]
    if not video_id:
        await update.message.reply_text("Не могу извлечь ID видео. Проверь ссылку.")
        return
    await update.message.reply_text("⏳ Получаю транскрипцию...")
    transcript = get_transcript(video_id)
    if not transcript:
        await update.message.reply_text("❌ Транскрипция недоступна для этого видео.")
        return
    prompt = f"""
Это транскрипция YouTube видео.

ТРАНСКРИПЦИЯ:
{transcript}

Сделай полный анализ:
1. HOOK — что именно зацепило в первые 3-5 секунд
2. СТРУКТУРА — breakdown по частям
3. ВИРУСНЫЕ ТРИГГЕРЫ — что держит зрителя
4. ТЕМП И ПАУЗЫ — где ускорение, где замедление
5. КАК АДАПТИРОВАТЬ для 3D анимации в стиле Zach D Films
6. ГОТОВЫЙ СКРИПТ-НАБРОСОК для похожего видео
"""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    result = f"📝 <b>ТРАНСКРИПЦИЯ:</b>\n{transcript[:1000]}...\n\n"
    result += f"🧠 <b>АНАЛИЗ:</b>\n{response.content[0].text}"
    if len(result) > 4000:
        parts = [result[i:i+4000] for i in range(0, len(result), 4000)]
        for part in parts:
            await update.message.reply_text(part, parse_mode="HTML")
    else:
        await update.message.reply_text(result, parse_mode="HTML")

async def scheduled_digest():
    run_daily_digest()

async def scheduled_tracker():
    run_tracker()

async def scheduled_viral():
    run_viral_check()

async def post_init(application):
    scheduler = AsyncIOScheduler()
    kyiv_tz = pytz.timezone("Europe/Kiev")
    scheduler.add_job(scheduled_digest, CronTrigger(hour=9, minute=0, timezone=kyiv_tz))
    scheduler.add_job(scheduled_tracker, CronTrigger(hour=9, minute=5, timezone=kyiv_tz))
    scheduler.add_job(run_weekly_report, CronTrigger(day_of_week="sun", hour=10, minute=0, timezone=kyiv_tz))
    scheduler.add_job(scheduled_viral, CronTrigger(hour="*/3", timezone=kyiv_tz))
    scheduler.start()

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(CommandHandler("digest", manual_digest))
    app.add_handler(CommandHandler("tracker", manual_tracker))
    app.add_handler(CommandHandler("weekly", manual_weekly))
    app.add_handler(CommandHandler("viral", manual_viral))
    app.add_handler(CommandHandler("transcript", transcript_command))
    app.add_handler(CommandHandler("remember", remember))
    app.add_handler(CommandHandler("memory", show_memory))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
