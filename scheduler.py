#!/usr/bin/env python3
import gzip
import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import jwt

BASE = Path(__file__).resolve().parent

HOST = "https://nq5u9n4tmv.re.qweatherapi.com"
KEY_ID = "CFGVU2N33T"
DEV_ID = "Q154F21609"
PROJ_ID = "3F2DHCW2QJ"
PRIVATE_KEY = (BASE / "ed25519-private.pem").read_text()

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


def make_token() -> str:
    now = int(time.time())
    payload = {
        "iss": DEV_ID,
        "sub": PROJ_ID,
        "iat": now - 30,
        "exp": now + 900,
    }
    return jwt.encode(payload, PRIVATE_KEY, algorithm="EdDSA", headers={"kid": KEY_ID})


run_all = len(sys.argv) > 1 and sys.argv[1] == "all"

now = datetime.now()
m = now.hour * 60 + now.minute

for period, name, path in TASKS:
    if run_all or m % period == 0:
        token = make_token()
        req = urllib.request.Request(HOST + path)
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept-Encoding", "gzip")

        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)

        data = json.loads(raw)
        out = BASE / "data" / f"{name}_{now:%Y%m%d_%H%M%S}.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{now:%F %T}] {name} -> {out}")
