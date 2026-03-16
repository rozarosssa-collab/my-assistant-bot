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

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")
MY_TELEGRAM_ID = int(os.getenv("MY_TELEGRAM_ID"))
HISTORY_FILE = "history.json"
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
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
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
        "✅ Бот запущен.\n\nРежимы:\nрежим: идеи\nрежим: скрипт\nрежим: анализ\nрежим: бенд\nрежим: стратегия\nрежим: критик\nрежим: reddit\n\n/clear — очистить память\n/digest — запустить аналитику сейчас"
    )

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    save_history([])
    await update.message.reply_text("🧹 Память очищена.")

async def manual_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text("⏳ Запускаю аналитику...")
    run_daily_digest()

async def scheduled_digest():
    run_daily_digest()

def main():
async def post_init(application):
    scheduler = AsyncIOScheduler()
    kyiv_tz = pytz.timezone("Europe/Kiev")
    scheduler.add_job(scheduled_digest, CronTrigger(hour=9, minute=0, timezone=kyiv_tz))
    scheduler.start()

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(CommandHandler("digest", manual_digest))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Бот запущен с аналитикой в 9:00 по Киеву...")
    app.run_polling()

if __name__ == "__main__":
    main()
