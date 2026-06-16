"""
猫眼排片数据客户端。
原位于 Prediction-Bot/scraper/maoyan.py，已内嵌到 Agent 项目中。
"""
import logging
import re
from datetime import date as dt_date

import requests
from config import MAOYAN_DASHBOARD_URL

logger = logging.getLogger(__name__)


class MaoyanClient:
    def __init__(self):
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Referer": "https://piaofang.maoyan.com/dashboard",
        }

    def _fetch_raw(self) -> dict:
        try:
            r = requests.get(MAOYAN_DASHBOARD_URL, headers=self._headers, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            raise RuntimeError(f"猫眼 API 请求失败: {e}")

    def fetch_movies(self) -> list[dict]:
        data = self._fetch_raw()
        movies_raw = data.get("movieList", {}).get("data", {}).get("list", [])
        result = []
        for m in movies_raw:
            info = m.get("movieInfo", {})
            result.append({
                "name": info.get("movieName", ""),
                "show_count": m.get("showCount", 0),
                "box_rate": m.get("boxRate", "0%"),
                "movie_id": info.get("movieId", 0),
            })
        return result

    def get_total_show_count(self) -> int:
        data = self._fetch_raw()
        desc = data.get("movieList", {}).get("data", {}).get("nationBoxInfo", {}).get("showCountDesc", "")
        return _parse_show_count_desc(desc)

    def fetch_movies_for_date(self, date_str: str) -> list[str]:
        """获取目标日期的侧边栏完整影片名列表（含未上映电影）。

        用于 _resolve_movie_names 的候选列表，解决未上映电影不在
        fetch_movies() 返回的今日大盘列表中的问题。
        """
        from playwright.sync_api import sync_playwright

        today_movies = self.fetch_movies()
        first_id = today_movies[0]["movie_id"] if today_movies else 0
        if not first_id:
            return [m["name"] for m in today_movies]

        api_date_no_dash = _to_api_date(date_str).replace("-", "")
        first_url = f"https://piaofang.maoyan.com/i/dashboard/movie?movieId={first_id}&date={api_date_no_dash}"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 375, "height": 812})
            try:
                page.goto(first_url, wait_until="networkidle", timeout=15000)
                page.wait_for_timeout(2000)
                # 多种方式提取侧边栏影片名
                names = page.evaluate("""() => {
                    const results = new Set();
                    // 方式1: a 标签含 movieId 的链接（侧边栏导航链接）
                    document.querySelectorAll('a[href*="movieId"]').forEach(a => {
                        const t = a.textContent.trim();
                        if (t && t.length >= 2 && t.length <= 40) results.add(t);
                    });
                    if (results.size >= 3) return [...results];
                    // 方式2: class 含 movie/film 的元素
                    document.querySelectorAll('[class*="movie" i], [class*="film" i]').forEach(el => {
                        const t = el.textContent.trim();
                        if (t && t.length >= 2 && t.length <= 40) results.add(t);
                    });
                    if (results.size >= 3) return [...results];
                    // 方式3: 侧边栏区域（左侧 40%）的叶子文本
                    document.querySelectorAll('*').forEach(el => {
                        if (el.children.length === 0) {
                            const r = el.getBoundingClientRect();
                            if (r.left < window.innerWidth * 0.4 && r.width > 0) {
                                const t = el.textContent.trim();
                                if (t && t.length >= 2 && t.length <= 40) results.add(t);
                            }
                        }
                    });
                    return [...results];
                }""")
                unique = [n for n in names if n and len(n) >= 2 and not n.isdigit()]
            except Exception:
                unique = []
            browser.close()

        # 过滤非影片名的噪音（上映天数、票房数字、类型标签等）
        movie_names = _filter_movie_names(unique)
        return movie_names if movie_names else [m["name"] for m in today_movies]

    def fetch_by_date(self, user_names: list[str], date_str: str) -> tuple[list[dict], int]:
        from playwright.sync_api import sync_playwright

        all_movies = self.fetch_movies()
        name_to_id = {m["name"]: m["movie_id"] for m in all_movies}

        api_date = _to_api_date(date_str)
        api_date_no_dash = api_date.replace("-", "")
        results = []
        total_show_count = 0
        known = []
        unknown = []

        logger.info("今日大盘共 %d 部电影，用户输入 %d 部", len(all_movies), len(user_names))
        for uname in user_names:
            uname = uname.strip()
            mid = name_to_id.get(uname)
            if mid:
                known.append((uname, mid))
                logger.info("  [匹配] \"%s\" -> movieId=%s", uname, mid)
            else:
                unknown.append(uname)
                logger.warning("  [未匹配] \"%s\" 不在今日大盘列表中，将尝试侧边栏查找", uname)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # Process known movies via direct detail page (reuse single page)
            if known:
                page = browser.new_page(viewport={"width": 375, "height": 812})
                for uname, mid in known:
                    sc, page_total = _scrape_detail(page, mid, api_date)
                    if total_show_count == 0:
                        total_show_count = page_total
                    results.append({"name": uname, "show_count": sc, "box_rate": "N/A", "movie_id": mid})
                    logger.info("  [详情页] \"%s\" show_count=%s, total=%s", uname, sc, page_total)
                page.close()

            # Process unknown movies by clicking through the sidebar
            if unknown and known:
                first_id = known[0][1]
            elif unknown:
                first_id = all_movies[0]["movie_id"] if all_movies else 0
            else:
                first_id = 0

            if unknown and first_id:
                first_url = f"https://piaofang.maoyan.com/i/dashboard/movie?movieId={first_id}&date={api_date_no_dash}"
                page = browser.new_page(viewport={"width": 375, "height": 812})
                page.goto(first_url, wait_until="networkidle", timeout=15000)
                page.wait_for_timeout(2000)

                for uname in unknown:
                    sc = 0
                    movie_id = 0
                    logger.info("  [侧边栏] 尝试查找 \"%s\"...", uname)
                    try:
                        el = page.locator(f"text={uname}").first
                        el.click(timeout=5000)
                        page.wait_for_timeout(2000)
                        logger.info("  [侧边栏] \"%s\" 点击成功，当前URL: %s", uname, page.url)

                        url = page.url
                        mid = re.search(r'movieId=(\d+)', url)
                        if mid:
                            movie_id = int(mid.group(1))
                            logger.info("  [侧边栏] \"%s\" 提取到 movieId=%s", uname, movie_id)
                        else:
                            logger.warning("  [侧边栏] \"%s\" URL中未找到movieId: %s", uname, url)

                        text = page.inner_text("body")
                        m = re.search(r'当日排片场次\s*\n\s*([\d,]+)', text)
                        if m:
                            sc = int(m.group(1).replace(",", ""))
                            logger.info("  [侧边栏] \"%s\" 场次=%s", uname, sc)
                        else:
                            logger.warning("  [侧边栏] \"%s\" 页面中未匹配到「当日排片场次」", uname)

                        if total_show_count == 0:
                            tm = re.search(r'总场次[：:]\s*([\d,.]+)\s*(万|场)?', text)
                            if tm:
                                num = float(tm.group(1).replace(',', ''))
                                total_show_count = int(num * 10000) if tm.group(2) == '万' else int(num)

                        # 重新加载侧边栏页面（不能用 go_back，SPA 不会重新渲染）
                        page.goto(first_url, wait_until="networkidle", timeout=15000)
                        page.wait_for_timeout(2000)
                    except Exception as e:
                        logger.warning("  [侧边栏] \"%s\" 失败: %s", uname, e)
                        # 失败后也重新加载侧边栏页面
                        try:
                            page.goto(first_url, wait_until="networkidle", timeout=15000)
                            page.wait_for_timeout(2000)
                        except Exception:
                            pass

                    results.append({"name": uname, "show_count": sc, "box_rate": "N/A", "movie_id": movie_id})

                page.close()

            browser.close()

        return results, total_show_count


def _scrape_detail(page, movie_id: int, api_date: str) -> tuple[int, int]:
    url = f"https://piaofang.maoyan.com/i/dashboard/movie?movieId={movie_id}&date={api_date}"
    page.goto(url, wait_until="networkidle", timeout=15000)
    page.wait_for_timeout(2000)
    text = page.inner_text("body")
    m = re.search(r'当日排片场次\s*\n\s*([\d,]+)', text)
    sc = int(m.group(1).replace(",", "")) if m else 0
    if not m:
        logger.warning("  [详情页] movieId=%s date=%s 未匹配到「当日排片场次」", movie_id, api_date)
    tm = re.search(r'总场次[：:]\s*([\d,.]+)\s*(万|场)?', text)
    if tm:
        num = float(tm.group(1).replace(',', ''))
        total = int(num * 10000) if tm.group(2) == '万' else int(num)
    else:
        total = 0
    return sc, total


def _to_api_date(date_str: str) -> str:
    parts = date_str.strip().split(".")
    month = int(parts[0])
    day = int(parts[1])
    return f"{dt_date.today().year}-{month:02d}-{day:02d}"


def _parse_show_count_desc(desc: str) -> int:
    m = re.match(r"([\d.]+)万", desc)
    if m:
        return int(float(m.group(1)) * 10000)
    return 0


def _filter_movie_names(raw: list[str]) -> list[str]:
    """过滤侧边栏提取结果中的非影片名噪音。"""
    # 噪音特征
    noise = re.compile(
        r'上映|点映|'
        r'\d+天|'               # "51天"
        r'\d+\.?\d*亿|'         # "17.53亿"
        r'\d+\.?\d*万|'         # "936.9万"
        r'^\d+[.,\d]*\s*$|'    # 纯数字
        r'^[\d零一二三四五六七八九十百千万亿]+$|'  # 纯中文数字
        r'剧情[、,，]|喜剧|动作|爱情|科幻|恐怖|动画|'
        r'纪录片|短片|惊悚|悬疑|奇幻|冒险|战争|'
        r'历史|家庭|犯罪|音乐|歌舞|武侠|传记|'
        r'灾难|西部|运动|黑色电影|'
        r'^影片\s*[（(]'          # "影片 (点击..."
    )
    seen = set()
    result = []
    for name in raw:
        name = name.strip()
        if not name or len(name) < 2 or len(name) > 30:
            continue
        if noise.search(name):
            continue
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result
