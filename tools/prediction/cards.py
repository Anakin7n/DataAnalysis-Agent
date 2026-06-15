"""
飞书消息模板 — 纯文本版本。
原位于 Prediction-Bot/bot/cards.py，已内嵌到 Agent 项目中。
"""

from datetime import date as dt_date


def _day_of_week(date_str: str) -> str:
    parts = date_str.split(".")
    month, day = int(parts[0]), int(parts[1])
    d = dt_date(dt_date.today().year, month, day)
    names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return names[d.weekday()]


def ask_date():
    return "📅 请输入预测日期，格式如 6.15"


def ask_movies(date_str: str):
    return (
        f"🎬 预测日期: {date_str}\n\n"
        "请输入需要预测的影片名称及累计新增占比：\n"
        "格式: 片名:17.6%, 片名:0.147, 片名=5.6%\n\n"
        "支持: 小数/百分比，中英文冒号、等号、横线分隔，逗号、分号、顿号分隔多部\n"
        "无需加书名号，直接输入电影名称即可"
    )


def ask_dapan(date_str: str):
    return f"请输入 {date_str} 的大盘场次(D)（如 420000）"


def querying():
    return "🔍 收到，正在查询猫眼排片数据，请稍候..."


def result(date_str: str, movie_count: int, dapan: int):
    return (
        f"✅ 预测 Excel 已生成\n\n"
        f"📅 预测日期: {date_str}\n"
        f"🎬 影片数量: {movie_count} 部\n"
        f"🏟️ 大盘场次: {dapan:,} 场\n\n"
        f"📎 请查收下方 Excel 文件"
    )


def summary(date_str: str, movies: list[dict], dapan_total: int, total_show_count: int):
    weekday = _day_of_week(date_str)
    lines = [f"{weekday}落位："]
    remaining = dapan_total - total_show_count
    for m in movies:
        cum_share = m.get("cumulative_share", 0)
        show_count = m.get("show_count", 0)
        final_show = remaining * cum_share + show_count
        pct = final_show / dapan_total * 100 if dapan_total else 0
        pct = int(pct * 10) / 10
        s = f"{pct:.1f}"
        if s.endswith(".0"):
            s = s[:-2]
        lines.append(f"{m['name']}：{s}%")
    return "\n".join(lines)


def error(msg: str):
    return f"⚠️ 出错了: {msg}"


def welcome():
    return "👋 欢迎使用影片落位预测 Bot！请发送 /start 开始预测。"


def invalid_format(hint: str):
    return f"⚠️ {hint}"
