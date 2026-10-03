#!/usr/bin/env python3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent

TASKS = [
    (30, "job_realtime_weather.py"),  # 实时天气, 30分钟
    (60, "job_hourly_forecast.py"),  # 逐小时天气预报, 60分钟
    (360, "job_daily_forecast.py"),  # 逐天天气预报, 6小时
    (20, "job_weather_alert.py"),  # 天气预警, 20分钟
    (720, "job_weather_index.py"),  # 天气指数, 12小时
    (10, "job_minutely_precip.py"),  # 分钟降水, 10分钟
    (60, "job_realtime_aqi.py"),  # 实时空气质量, 60分钟
    (720, "job_daily_aqi_forecast.py"),  # 空气质量逐天预报, 12小时
]

run_all = len(sys.argv) > 1 and sys.argv[1] == "all"

now = datetime.now()
m = now.hour * 60 + now.minute

for period, script in TASKS:
    if run_all or m % period == 0:
        print(f"[{now:%F %T}] run {script}")
        # subprocess.Popen(["python3", str(BASE / script)])
