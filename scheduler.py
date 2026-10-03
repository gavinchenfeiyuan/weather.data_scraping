#!/usr/bin/env python3
import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
TOKEN = "f572ba067544457b9050079432345cfe"
HOST = "https://nq5u9n4tmv.re.qweatherapi.com"

TASKS = [
    (30, "realtime_weather", "/weather/v1/current/39.92/116.41"),
    # (60, "hourly_forecast", "/weather/v1/hourly/39.92/116.41"),
    # (360, "daily_forecast", "/weather/v1/daily/39.92/116.41"),
    # (20, "weather_alert", "/weather/v1/alert/39.92/116.41"),
    # (720, "weather_index", "/weather/v1/index/39.92/116.41"),
    # (10, "minutely_precip", "/weather/v1/minutely/39.92/116.41"),
    # (60, "realtime_aqi", "/air/v1/current/39.92/116.41"),
    # (720, "daily_aqi_forecast", "/air/v1/daily/39.92/116.41"),
]

run_all = len(sys.argv) > 1 and sys.argv[1] == "all"

now = datetime.now()
m = now.hour * 60 + now.minute

for period, name, path in TASKS:
    if run_all or m % period == 0:
        req = urllib.request.Request(HOST + path)
        req.add_header("Authorization", f"Bearer {TOKEN}")
        data = json.loads(urllib.request.urlopen(req, timeout=30).read())
        out = BASE / "data" / f"{name}_{now:%Y%m%d_%H%M%S}.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{now:%F %T}] {name} -> {out}")
