"""天气 + 工作日查询 — 为早晚消息提供上下文

天气: wttr.in (免费, 无需API密钥)
工作日: 周一至周五 (法定节假日需手动更新)
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta

# 西安未央区
CITY = "Xi'an+Weiyang"

# 2026年中国法定节假日 (月-日格式)
# 可更新此列表以适配最新假期安排
HOLIDAYS_2026 = {
    # 元旦
    "01-01", "01-02", "01-03",
    # 春节 (假设1月28日-2月3日)
    "01-28", "01-29", "01-30", "01-31", "02-01", "02-02", "02-03",
    # 清明 (假设4月5日)
    "04-04", "04-05", "04-06",
    # 劳动节 (假设5月1日-5月5日)
    "05-01", "05-02", "05-03", "05-04", "05-05",
    # 端午 (假设6月19日-6月21日)
    "06-19", "06-20", "06-21",
    # 中秋+国庆 (假设10月1日-10月7日)
    "10-01", "10-02", "10-03", "10-04", "10-05", "10-06", "10-07",
}

# 调休上班日 (周末但需要上班)
WORKDAYS_OVERRIDE = {
    # 示例: "01-26", "02-07" 等调休日
}


def get_weather(city=CITY):
    """获取天气信息"""
    try:
        url = f"https://wttr.in/{city}?format=j1&lang=zh"
        req = urllib.request.Request(url, headers={"User-Agent": "Muse/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        current = data.get("current_condition", [{}])[0]
        today_weather = data.get("weather", [{}])[0] if data.get("weather") else {}
        tomorrow_weather = data.get("weather", [{}])[1] if len(data.get("weather", [])) > 1 else {}

        result = {
            "current": {
                "temp": current.get("temp_C", ""),
                "feels_like": current.get("FeelsLikeC", ""),
                "desc": current.get("lang_zh", [{}])[0].get("value", current.get("weatherDesc", [{}])[0].get("value", "")),
                "humidity": current.get("humidity", ""),
                "wind": current.get("windspeedKmph", ""),
            },
            "today": _parse_weather_day(today_weather),
            "tomorrow": _parse_weather_day(tomorrow_weather),
        }
        return result
    except Exception as e:
        return {"error": str(e)}


def _parse_weather_day(day_data):
    """解析单日天气"""
    if not day_data:
        return {}
    hourly = day_data.get("hourly", [])
    # 取中午12点的天气作为代表
    noon = hourly[4] if len(hourly) > 4 else (hourly[0] if hourly else {})
    return {
        "max_temp": day_data.get("maxtempC", ""),
        "min_temp": day_data.get("mintempC", ""),
        "desc": noon.get("lang_zh", [{}])[0].get("value", noon.get("weatherDesc", [{}])[0].get("value", "")),
        "rain_chance": noon.get("chanceofrain", "0"),
    }


def is_workday(date=None):
    """判断是否是工作日

    Returns:
        (bool, str): (是否工作日, 说明)
    """
    if date is None:
        date = datetime.now()

    date_key = date.strftime("%m-%d")
    weekday = date.weekday()  # 0=周一, 6=周日

    # 调休上班日优先
    if date_key in WORKDAYS_OVERRIDE:
        return True, "调休上班日"

    # 法定节假日
    if date_key in HOLIDAYS_2026:
        return False, "法定节假日"

    # 周末
    if weekday >= 5:
        return False, "周末"

    return True, "工作日"


def get_weather_summary(city=CITY):
    """生成天气摘要（供 prompt 注入）"""
    weather = get_weather(city)

    if "error" in weather:
        return f"天气查询失败: {weather['error']}"

    now = datetime.now()
    tomorrow = now + timedelta(days=1)
    is_work, work_desc = is_workday(tomorrow)

    today_w = weather.get("today", {})
    tomorrow_w = weather.get("tomorrow", {})
    current = weather.get("current", {})

    lines = []

    # 当前天气
    if current.get("temp"):
        lines.append(f"现在: {current['temp']}°C, {current['desc']}")

    # 今天天气
    if today_w.get("max_temp"):
        lines.append(f"今天: {today_w['min_temp']}~{today_w['max_temp']}°C, {today_w['desc']}")
        if today_w.get("rain_chance", "0") != "0":
            lines.append(f"  降雨概率: {today_w['rain_chance']}%")

    # 明天天气
    if tomorrow_w.get("max_temp"):
        weekday_cn = ["周一","周二","周三","周四","周五","周六","周日"][tomorrow.weekday()]
        lines.append(f"明天({weekday_cn}): {tomorrow_w['min_temp']}~{tomorrow_w['max_temp']}°C, {tomorrow_w['desc']}")
        if tomorrow_w.get("rain_chance", "0") != "0":
            lines.append(f"  降雨概率: {tomorrow_w['rain_chance']}%")

    # 工作日
    lines.append(f"明天: {'工作日' if is_work else '休息日'}（{work_desc}）")

    return "\n".join(lines)


if __name__ == "__main__":
    print(get_weather_summary())
