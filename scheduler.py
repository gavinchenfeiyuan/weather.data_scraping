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

LOCATION = {
    "上海": [121.49, 31.12],
    "莆田": [119.09, 25.45],
    "厦门": [118.25, 24.62],
}

TASKS = [
    # 实时天气, 30分钟
    (30, "realtime_weather", "/weather/v1/current/{lat}/{lon}"),
    # 逐小时天气预报, 60分钟
    (60, "hourly_forecast", "/weather/v1/hourly/{lat}/{lon}?hours=72"),
    # 逐天天气预报, 6小时
    (360, "daily_forecast", "/weather/v1/daily/{lat}/{lon}?days=10"),
    # 天气预警, 20分钟
    (20, "weather_alert", "/weatheralert/v1/current/{lat}/{lon}"),
    # 天气指数, 12小时
    (720, "weather_index", "/v7/indices/3d?type=0&location={lon},{lat}"),
    # 分钟降水, 10分钟
    (10, "minutely_precip", "/v7/minutely/5m?location={lon},{lat}"),
    # 实时空气质量, 60分钟
    (60, "realtime_aqi", "/airquality/v1/current/{lat}/{lon}"),
    # 空气质量逐天预报, 12小时
    (720, "daily_aqi_forecast", "/airquality/v1/daily/{lat}/{lon}"),
]


def make_token() -> str:
    now = int(time.time())
    payload = {"iss": DEV_ID, "sub": PROJ_ID, "iat": now - 30, "exp": now + 900}
    return jwt.encode(payload, PRIVATE_KEY, algorithm="EdDSA", headers={"kid": KEY_ID})


run_all = len(sys.argv) > 1 and sys.argv[1] == "all"

now = datetime.now()
m = now.hour * 60 + now.minute

for period, name, tmpl in TASKS:
    if run_all or m % period == 0:
        for city, (lon, lat) in LOCATION.items():
            path = tmpl.format(lat=lat, lon=lon)
            try:
                req = urllib.request.Request(HOST + path)
                req.add_header("Authorization", f"Bearer {make_token()}")
                req.add_header("Accept-Encoding", "gzip")

                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read()
                    if resp.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)

                data = json.loads(raw)
                out = BASE / "data" / city / f"{name}_{now:%Y%m%d_%H%M%S}.json"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(f"[{now:%F %T}] {city} {name} -> {out}")
            except Exception as e:
                print(f"[{now:%F %T}] {city} {name} 失败: {e}")
