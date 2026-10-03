#!/usr/bin/env python3
import gzip
import json
import os
import subprocess
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

# 历史数据目录（带时间戳）
HISTORY_DIR = BASE / "data"

# 最新数据副本目录（文件名不带时间戳，覆盖式）
LATEST_DIR = BASE.parent / "weather.yuanping.fun" / "data"

# git 仓库根目录
GIT_DIR = LATEST_DIR.parent

# 夜间休眠区间：00:00 - 06:00
NIGHT_START = 0
NIGHT_END = 6

# 城市 -> [经度, 纬度]
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


def fetch(path: str) -> dict:
    req = urllib.request.Request(HOST + path)
    req.add_header("Authorization", f"Bearer {make_token()}")
    req.add_header("Accept-Encoding", "gzip")

    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)

    return json.loads(raw)


def git_sync(now: datetime) -> None:
    """提交并推送最新数据"""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=GIT_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )

    run("add", "-A")

    # 没有变化就跳过
    diff = run("diff", "--cached", "--quiet")
    if diff.returncode == 0:
        print(f"[{now:%F %T}] git: 无变化，跳过 commit")
        return

    msg = f"data update {now:%Y-%m-%d %H:%M:%S}"
    c = run("commit", "-m", msg)
    if c.returncode != 0:
        print(f"[{now:%F %T}] git commit 失败: {c.stderr.strip()}")
        return

    # 拉取远端最新
    f = run("fetch")
    if f.returncode != 0:
        print(f"[{now:%F %T}] git fetch 失败: {f.stderr.strip()}")
        return

    # 把本地 commit 重放到远端之上
    r = run("pull", "--rebase")
    if r.returncode != 0:
        print(f"[{now:%F %T}] git pull --rebase 失败: {r.stderr.strip()}")
        run("rebase", "--abort")  # 避免仓库卡在 rebase 中间状态
        return

    p = run("push")
    if p.returncode != 0:
        print(f"[{now:%F %T}] git push 失败: {p.stderr.strip()}")
        return

    print(f"[{now:%F %T}] git: 已提交并推送 ({msg})")


def main() -> None:
    run_all = len(sys.argv) > 1 and sys.argv[1] == "all"

    now = datetime.now()

    # 夜间休眠：定时触发时跳过；手动 all 不受限
    if not run_all and NIGHT_START <= now.hour < NIGHT_END:
        print(f"[{now:%F %T}] 夜间 {NIGHT_START:02d}:00-{NIGHT_END:02d}:00，跳过")
        return

    m = now.hour * 60 + now.minute

    for period, name, tmpl in TASKS:
        if not (run_all or m % period == 0):
            continue

        for city, (lon, lat) in LOCATION.items():
            path = tmpl.format(lat=lat, lon=lon)
            try:
                data = fetch(path)
                text = json.dumps(data, ensure_ascii=False, indent=2)

                # 历史文件（带时间戳）
                history = HISTORY_DIR / city / f"{name}_{now:%Y%m%d_%H%M%S}.json"
                history.parent.mkdir(parents=True, exist_ok=True)
                history.write_text(text, encoding="utf-8")

                # 最新副本（覆盖式，无时间戳）
                latest = LATEST_DIR / city / f"{name}.json"
                latest.parent.mkdir(parents=True, exist_ok=True)
                latest.write_text(text, encoding="utf-8")

                print(f"[{now:%F %T}] {city} {name} -> {history} | {latest}")
            except Exception as e:
                print(f"[{now:%F %T}] {city} {name} 失败: {e}")

    git_sync(now)


if __name__ == "__main__":
    main()
