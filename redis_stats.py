import os
import json
import requests
from datetime import datetime

REDIS_URL = os.getenv("UPSTASH_REDIS_REST_URL")
REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN")

INPUT_PRICE_PER_M = 3.0
OUTPUT_PRICE_PER_M = 15.0
WHISPER_PRICE_PER_MIN = 0.006

def redis_get(key):
    try:
        r = requests.get(
            f"{REDIS_URL}/get/{key}",
            headers={"Authorization": f"Bearer {REDIS_TOKEN}"}
        )
        result = r.json().get("result")
        if result:
            return json.loads(result)
        return None
    except Exception:
        return None

def redis_set(key, value):
    try:
        requests.post(
            REDIS_URL,
            headers={
                "Authorization": f"Bearer {REDIS_TOKEN}",
                "Content-Type": "application/json"
            },
            json=["SET", key, json.dumps(value)]
        )
    except Exception:
        pass

def get_month_key():
    now = datetime.now()
    return f"stats_{now.year}_{now.month}"

def get_day_key():
    now = datetime.now()
    return f"day_{now.year}_{now.month}_{now.day}"

def calculate_cost(input_tokens, output_tokens):
    return (input_tokens / 1_000_000) * INPUT_PRICE_PER_M + (output_tokens / 1_000_000) * OUTPUT_PRICE_PER_M

def update_tg_stats(input_tokens, output_tokens):
    cost = calculate_cost(input_tokens, output_tokens)

    month_key = get_month_key()
    current = redis_get(month_key) or {
        "web_cost": 0, "tg_cost": 0, "web_messages": 0,
        "tg_messages": 0, "whisper_cost": 0, "input_tokens": 0, "output_tokens": 0
    }
    current["tg_cost"] = current.get("tg_cost", 0) + cost
    current["tg_messages"] = current.get("tg_messages", 0) + 1
    current["input_tokens"] = current.get("input_tokens", 0) + input_tokens
    current["output_tokens"] = current.get("output_tokens", 0) + output_tokens
    redis_set(month_key, current)

    day_key = get_day_key()
    day = redis_get(day_key) or {"web_cost": 0, "tg_cost": 0, "messages": 0}
    day["tg_cost"] = day.get("tg_cost", 0) + cost
    day["messages"] = day.get("messages", 0) + 1
    redis_set(day_key, day)

def update_whisper_stats(duration_seconds):
    cost = (duration_seconds / 60) * WHISPER_PRICE_PER_MIN

    month_key = get_month_key()
    current = redis_get(month_key) or {
        "web_cost": 0, "tg_cost": 0, "web_messages": 0,
        "tg_messages": 0, "whisper_cost": 0, "input_tokens": 0, "output_tokens": 0
    }
    current["whisper_cost"] = current.get("whisper_cost", 0) + cost
    redis_set(month_key, current)
