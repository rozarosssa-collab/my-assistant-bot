import os
import json
import requests
from datetime import datetime
from anthropic import Anthropic

ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MY_TELEGRAM_ID = os.getenv("MY_TELEGRAM_ID")
CALORIES_FILE = "calories.json"
DAILY_LIMIT = 1800

client = Anthropic(api_key=ANTHROPIC_KEY)

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

Определи КБЖУ (калории, белки, жиры, углеводы) для этого продукта/блюда.
Если указан вес — используй его. Если не указан — используй стандартную порцию.

Ответь ТОЛЬКО в формате JSON без пояснений:
{{"name": "название продукта", "calories": число, "protein": число, "fat": число, "carbs": число, "amount": "количество/порция"}}

Все числа — целые, без десятичных."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )
    
    import re
    text = response.content[0].text.strip()
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    return None

def add_food(food_text):
    data = load_calories()
    food = analyze_food(food_text)
    
    if not food:
        return None, None
    
    data["items"].append(food)
    data["total"]["calories"] += food["calories"]
    data["total"]["protein"] += food["protein"]
    data["total"]["fat"] += food["fat"]
    data["total"]["carbs"] += food["carbs"]
    save_calories(data)
    
    over_limit = data["total"]["calories"] > DAILY_LIMIT
    return food, data["total"], over_limit

def get_today_summary():
    data = load_calories()
    return data

def reset_calories():
    data = {"date": get_today(), "items": [], "total": {"calories": 0, "protein": 0, "fat": 0, "carbs": 0}}
    save_calories(data)
    return data

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": MY_TELEGRAM_ID, "text": text})

def run_daily_reset():
    reset_calories()
    send_telegram("🌅 Новый день — счётчик калорий сброшен!\n\nЦель на сегодня: 1800 ккал 🎯")
