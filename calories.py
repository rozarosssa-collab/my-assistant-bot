import os
import json
import re
import requests
from datetime import datetime
from anthropic import Anthropic

ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MY_TELEGRAM_ID = os.getenv("MY_TELEGRAM_ID")
CALORIES_FILE = "calories.json"
DAILY_LIMIT = 1800

calorie_client = Anthropic(api_key=ANTHROPIC_KEY)

def get_today():
    return datetime.now().strftime("%Y-%m-%d")

def load_calories():
    if os.path.exists(CALORIES_FILE):
        with open(CALORIES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") != get_today():
            return {"date": get_today(), "items": [], "total": {"calories": 0, "protein": 0, "fat": 0, "carbs": 0}}
        return data
    return {"date": get_today(), "items": [], "total": {"calories": 0, "protein": 0, "fat": 0, "carbs": 0}}

def save_calories(data):
    with open(CALORIES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def analyze_food(food_text):
    prompt = f"""Пользователь съел: {food_text}

Определи КБЖУ для каждого продукта отдельно.
Если указан вес — используй его. Если не указан — используй стандартную порцию.

Ответь ТОЛЬКО в формате JSON без пояснений:
{{"items": [{{"name": "название", "amount": "порция", "calories": число, "protein": число, "fat": число, "carbs": число}}]}}

Все числа — целые. Если один продукт — всё равно верни массив с одним элементом."""

    response = calorie_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text.strip()
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    return None

def add_food(food_text):
    data = load_calories()
    result = analyze_food(food_text)

    if not result or "items" not in result:
        return None, None, False

    items = result["items"]

    for item in items:
        data["items"].append(item)
        data["total"]["calories"] += item["calories"]
        data["total"]["protein"] += item["protein"]
        data["total"]["fat"] += item["fat"]
        data["total"]["carbs"] += item["carbs"]

    save_calories(data)

    over_limit = data["total"]["calories"] > DAILY_LIMIT
    return items, data["total"], over_limit

def get_today_summary():
    return load_calories()

def reset_calories():
    data = {"date": get_today(), "items": [], "total": {"calories": 0, "protein": 0, "fat": 0, "carbs": 0}}
    save_calories(data)
    return data

def send_calorie_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": MY_TELEGRAM_ID, "text": text})

def run_daily_reset():
    reset_calories()
    send_calorie_telegram("🌅 Новый день — счётчик калорий сброшен!\n\nЦель на сегодня: 1800 ккал 🎯")
