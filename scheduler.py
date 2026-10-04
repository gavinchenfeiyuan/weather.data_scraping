#!/usr/bin/env python3
import gzip
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
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

# 月相：每天抓一次（周期 1440 分钟），与 10 天预报对齐
# 每城需要循环 10 个日期各请求一次，不走 TASKS 通用循环
MOON_PERIOD = 1440
MOON_DAYS = 10


_token_cache = {"token": None, "exp": 0}


def make_token() -> str:
    now = int(time.time())
    if _token_cache["token"] and now < _token_cache["exp"]:
        return _token_cache["token"]
    payload = {"iss": DEV_ID, "sub": PROJ_ID, "iat": now - 30, "exp": now + 900}
    token = jwt.encode(payload, PRIVATE_KEY, algorithm="EdDSA", headers={"kid": KEY_ID})
    _token_cache["token"] = token
    _token_cache["exp"] = now + 840
    return token


def fetch(path: str, max_retries: int = 3) -> dict:
    last_err = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(HOST + path)
            req.add_header("Authorization", f"Bearer {make_token()}")
            req.add_header("Accept-Encoding", "gzip")

            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)

            return json.loads(raw)
        except urllib.error.HTTPError as e:
            last_err = e
            # 401/402 是鉴权或配额问题，重试没有意义
            if e.code in (401, 402):
                raise
            # 403 通常是限流，退避久一点
            sleep_s = (2 ** attempt) * (2 if e.code == 403 else 1)
            print(f"[fetch] HTTP {e.code} on {path}, retry in {sleep_s}s")
            time.sleep(sleep_s)
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            sleep_s = 2 ** attempt
            print(f"[fetch] network error on {path}: {e}, retry in {sleep_s}s")
            time.sleep(sleep_s)
    raise last_err


def fetch_moon_for_city(
    city: str, lon: float, lat: float, days: int = MOON_DAYS
) -> dict:
    """抓取某城未来 N 天月相（每城 N 个请求，取每日 12:00 值）

    月相接口一次只返回单日 24 小时数据，所以需要循环 N 天分别请求。
    返回结构：
      { updateTime, city, days: [{date, value, illumination, name, icon}, ...] }
    - value:        月相数值 0.00-1.00（0=新月，0.5=满月）
    - illumination: 照明度百分比 0-100
    - name:         中文名（如"残月"）
    - icon:         和风官方图标代码 800-807
    """
    today = datetime.now().date()
    rows = []

    for i in range(days):
        date_str = (today + timedelta(days=i)).strftime("%Y%m%d")
        path = f"/v7/astronomy/moon?location={lon},{lat}&date={date_str}"
        try:
            data = fetch(path)
            arr = data.get("moonPhase", [])
            # 取 12:00 那条作为当天代表值，找不到则取中间一条
            noon = next((p for p in arr if "T12:00" in p.get("fxTime", "")), None)
            rec = noon or (arr[len(arr) // 2] if arr else None)
            if rec:
                rows.append(
                    {
                        "date": date_str,
                        "value": float(rec.get("value", 0)),
                        "illumination": int(rec.get("illumination", 0)),
                        "name": rec.get("name", ""),
                        "icon": rec.get("icon", ""),
                    }
                )
            else:
                rows.append({"date": date_str, "error": "no data"})
        except Exception as e:
            rows.append({"date": date_str, "error": str(e)})

    return {
        "updateTime": datetime.now().isoformat(timespec="seconds"),
        "city": city,
        "days": rows,
    }


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

    # ---------- 月相（每城循环 10 天，单独处理） ----------
    # 不走 TASKS 通用循环：月相接口一次只返回单日数据，需按天循环
    if run_all or m % MOON_PERIOD == 10:
        for city, (lon, lat) in LOCATION.items():
            try:
                data = fetch_moon_for_city(city, lon, lat)
                text = json.dumps(data, ensure_ascii=False, indent=2)

                # 历史文件（带时间戳）
                history = HISTORY_DIR / city / f"moon_phase_{now:%Y%m%d_%H%M%S}.json"
                history.parent.mkdir(parents=True, exist_ok=True)
                history.write_text(text, encoding="utf-8")

                # 最新副本（覆盖式，无时间戳）
                latest = LATEST_DIR / city / "moon_phase.json"
                latest.parent.mkdir(parents=True, exist_ok=True)
                latest.write_text(text, encoding="utf-8")

                print(f"[{now:%F %T}] {city} moon_phase -> {history} | {latest}")
            except Exception as e:
                print(f"[{now:%F %T}] {city} moon_phase 失败: {e}")

    try:
        git_sync(now)
    except subprocess.TimeoutExpired as e:
        print(f"[{now:%F %T}] git timeout: {e}")


if __name__ == "__main__":
    main()
