"""
文案生成器。
从 feishu-bot/main.py 提取的 build_message 及相关辅助函数。
"""


def calc_deadline(extract_date: str, extract_hour: int) -> str:
    deadline_hour = 10 if extract_hour < 12 else 16
    parts = extract_date.split("-")
    return f"{int(parts[1])}月{int(parts[2])}日{deadline_hour}点"


def format_mon_date(date_str: str) -> str:
    parts = date_str.split(" ")[0].split("-")
    return f"{int(parts[1])}月{int(parts[2])}日"


def format_mon_day(date_str: str) -> str:
    return f"{int(date_str.split(' ')[0].split('-')[2])}日"


def build_message(entries: list[dict]) -> tuple[str, str]:
    movie = entries[0]["movie"]
    last = entries[-1]
    deadline = calc_deadline(last["extract_date"], last["extract_hour"])
    date_range = f"{format_mon_date(entries[0]['mon_start'])}-{format_mon_date(entries[-1]['mon_start'])}"

    has_cmp = any(e.get("cmp_movie") for e in entries)
    cmp_movie = entries[0].get("cmp_movie", "") if has_cmp else ""

    if has_cmp:
        first_line = f"1）优先推进已开预售未开《{movie}》的影城，攻克劣势影城，加速影城开场进度"
    else:
        first_line = f"1）优先推进已开预售未开《{movie}》的影城，攻克劣势影城"

    lines = [
        "辛苦同步",
        first_line,
        "2）目标进度低于均值的小伙伴们继续加油",
        "",
        f"截止至{deadline}，【{movie}】{date_range}开场数据如上",
    ]

    def _format_pp(val):
        if isinstance(val, (int, float)) and val < 1:
            return round(val * 100, 2)
        return val

    def _hb_text(d):
        parts = []
        if "影片距离满足红包场次数差1场影城数" in d:
            parts.append(f"排片红包差值1场影院:{int(d['影片距离满足红包场次数差1场影城数'])}家")
        if "影片距离满足红包场次数差2场影城数" in d:
            parts.append(f"排片红包差值2场影院:{int(d['影片距离满足红包场次数差2场影城数'])}家")
        return "，".join(parts)

    n = 1
    for entry in entries:
        day_label = format_mon_day(entry["mon_start"])
        d = entry["data"]
        cc = int(d["场次数"])
        ls = int(d["劣势影城数"])
        pp = _format_pp(d["排片占比"])

        line = f"{n}）{day_label}《{movie}》已开{cc}场，未排《{movie}》的有{ls}家，排片占比{pp}%"
        hb = _hb_text(d)
        if hb:
            line += "，" + hb
        lines.append(line)
        n += 1

        if has_cmp and entry.get("cmp_data"):
            cd = entry["cmp_data"]
            ccc = int(cd["场次数"])
            cpp = _format_pp(cd["排片占比"])
            diff = cd.get("主影片与当前影片排片占比差值")
            if diff is None and isinstance(d["排片占比"], (int, float)) and isinstance(cd["排片占比"], (int, float)):
                diff = round((_format_pp(d["排片占比"]) - _format_pp(cd["排片占比"])), 2)
            elif isinstance(diff, (int, float)) and diff < 1 and diff != 0:
                diff = round(diff * 100, 2)

            cmp_line = f"{n}）{day_label}《{cmp_movie}》已开{ccc}场，排片占比{cpp}%"
            if diff is not None:
                cmp_line += f"，{movie}与{cmp_movie}大盘差值为{diff}%"
            lines.append(cmp_line)
            n += 1

        lines.append("")

    main_message = "\n".join(lines)

    summary_message = f"以上为截止{deadline}，《{movie}》{date_range}开场情况，辛苦大家参考跟进。"

    return main_message, summary_message
