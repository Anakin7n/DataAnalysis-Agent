"""
猫眼排片数据客户端。
原位于 Prediction-Bot/scraper/maoyan.py，已内嵌到 Agent 项目中。
"""
import re
from datetime import date as dt_date

import requests
from config import MAOYAN_DASHBOARD_URL


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

        for uname in user_names:
            uname = uname.strip()
            mid = name_to_id.get(uname)
            if mid:
                known.append((uname, mid))
            else:
                unknown.append(uname)

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
                page.close()

            # Process unknown movies by clicking through the sidebar
            if unknown and known:
                first_id = known[0][1]
            elif unknown:
                first_id = all_movies[0]["movie_id"] if all_movies else 0
            else:
                first_id = 0

            if unknown and first_id:
                page = browser.new_page(viewport={"width": 375, "height": 812})
                page.goto(
                    f"https://piaofang.maoyan.com/i/dashboard/movie?movieId={first_id}&date={api_date_no_dash}",
                    wait_until="domcontentloaded", timeout=15000,
                )
                page.wait_for_timeout(2000)

                for uname in unknown:
                    sc = 0
                    movie_id = 0
                    try:
                        el = page.locator(f"text={uname}").first
                        el.click(timeout=5000)
                        page.wait_for_timeout(2000)

                        url = page.url
                        mid = re.search(r'movieId=(\d+)', url)
                        if mid:
                            movie_id = int(mid.group(1))

                        text = page.inner_text("body")
                        m = re.search(r'当日排片场次\s*\n\s*([\d,]+)', text)
                        if m:
                            sc = int(m.group(1).replace(",", ""))

                        if total_show_count == 0:
                            tm = re.search(r'总场次[：:]\s*([\d.]+)万', text)
                            if tm:
                                total_show_count = int(float(tm.group(1)) * 10000)

                        page.go_back()
                        page.wait_for_timeout(1000)
                    except Exception:
                        pass

                    results.append({"name": uname, "show_count": sc, "box_rate": "N/A", "movie_id": movie_id})

                page.close()

            browser.close()

        return results, total_show_count


def _scrape_detail(page, movie_id: int, api_date: str) -> tuple[int, int]:
    url = f"https://piaofang.maoyan.com/i/dashboard/movie?movieId={movie_id}&date={api_date}"
    page.goto(url, wait_until="domcontentloaded", timeout=15000)
    try:
        page.wait_for_selector("text=当日排片场次", timeout=8000)
    except Exception:
        pass
    text = page.inner_text("body")
    m = re.search(r'当日排片场次\s*\n\s*([\d,]+)', text)
    sc = int(m.group(1).replace(",", "")) if m else 0
    tm = re.search(r'总场次[：:]\s*([\d.]+)万', text)
    total = int(float(tm.group(1)) * 10000) if tm else 0
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
