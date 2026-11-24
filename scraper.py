#!/usr/bin/env python3
"""
網頁爬蟲 Terminal 工具
用法：
    python3 scraper.py                 # 互動式選單
    python3 scraper.py <網址>           # 直接抓取標題與摘要
    python3 scraper.py <網址> -s "h2"   # 用 CSS selector 抓取
    python3 scraper.py <網址> -l        # 列出所有連結
    python3 scraper.py <網址> -i        # 列出所有圖片
    加上 -o 結果.csv / 結果.json 可存檔
"""

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

# ── 終端機顏色 ─────────────────────────────────────────
C = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
    "red": "\033[31m", "green": "\033[32m", "yellow": "\033[33m",
    "blue": "\033[34m", "cyan": "\033[36m",
}


def color(text, *styles):
    if not sys.stdout.isatty():
        return str(text)
    return "".join(C[s] for s in styles) + str(text) + C["reset"]


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}
OUTPUT_DIR = Path(__file__).parent / "output"


# ── 核心功能 ───────────────────────────────────────────
def normalize_url(url: str) -> str:
    url = url.strip()
    if not urlparse(url).scheme:
        url = "https://" + url
    return url


def allowed_by_robots(url: str) -> bool:
    """檢查 robots.txt 是否允許爬取（讀不到就當作允許）。"""
    parts = urlparse(url)
    rp = RobotFileParser()
    rp.set_url(f"{parts.scheme}://{parts.netloc}/robots.txt")
    try:
        rp.read()
        return rp.can_fetch(HEADERS["User-Agent"], url)
    except Exception:
        return True


def fetch(url: str) -> BeautifulSoup:
    url = normalize_url(url)
    if not allowed_by_robots(url):
        print(color("⚠ 這個網站的 robots.txt 不允許爬取此頁面。", "yellow"))
        if input("仍要繼續嗎？(y/N) ").strip().lower() != "y":
            raise SystemExit(0)
    print(color(f"→ 正在抓取 {url} ...", "dim"))
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding
    soup = BeautifulSoup(resp.text, "html.parser")
    soup.base_url = resp.url  # 記錄最終網址，方便組合相對連結
    print(color(f"✓ HTTP {resp.status_code}，{len(resp.content):,} bytes", "green"))
    return soup


def scrape_summary(soup):
    title = soup.title.get_text(strip=True) if soup.title else ""
    desc_tag = soup.find("meta", attrs={"name": "description"}) or \
        soup.find("meta", attrs={"property": "og:description"})
    desc = desc_tag.get("content", "").strip() if desc_tag else ""
    headings = [h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2", "h3"])]
    return [{"類型": "標題", "內容": title},
            {"類型": "描述", "內容": desc}] + \
           [{"類型": "小標", "內容": h} for h in headings if h]


def scrape_links(soup):
    seen, rows = set(), []
    for a in soup.find_all("a", href=True):
        href = urljoin(soup.base_url, a["href"])
        if href.startswith(("http://", "https://")) and href not in seen:
            seen.add(href)
            rows.append({"文字": a.get_text(" ", strip=True)[:80], "網址": href})
    return rows


def scrape_images(soup):
    seen, rows = set(), []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if not src:
            continue
        src = urljoin(soup.base_url, src)
        if src not in seen:
            seen.add(src)
            rows.append({"說明": img.get("alt", "").strip()[:80], "網址": src})
    return rows


def scrape_selector(soup, selector):
    rows = []
    for el in soup.select(selector):
        row = {"文字": el.get_text(" ", strip=True)}
        if el.get("href"):
            row["網址"] = urljoin(soup.base_url, el["href"])
        if el.get("src"):
            row["網址"] = urljoin(soup.base_url, el["src"])
        rows.append(row)
    return rows


# ── 輸出 ───────────────────────────────────────────────
def show(rows, limit=50):
    if not rows:
        print(color("（沒有找到任何資料）", "yellow"))
        return
    for i, row in enumerate(rows[:limit], 1):
        parts = [f"{color(k, 'cyan')}: {v}" for k, v in row.items() if v]
        print(f"{color(f'{i:>3}.', 'bold')} " + "  |  ".join(parts))
    if len(rows) > limit:
        print(color(f"... 還有 {len(rows) - limit} 筆未顯示（存檔可看全部）", "dim"))
    print(color(f"共 {len(rows)} 筆", "green"))


def save(rows, path: str):
    if not rows:
        print(color("沒有資料可以存。", "yellow"))
        return
    p = Path(path)
    if not p.is_absolute():
        OUTPUT_DIR.mkdir(exist_ok=True)
        p = OUTPUT_DIR / p
    if p.suffix.lower() == ".json":
        p.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        if p.suffix.lower() != ".csv":
            p = p.with_suffix(".csv")
        keys = list(dict.fromkeys(k for r in rows for k in r))
        with p.open("w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig 讓 Excel 正確顯示中文
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
    print(color(f"💾 已儲存到 {p}", "green"))


# ── 互動式選單 ─────────────────────────────────────────
BANNER = r"""
 ╔══════════════════════════════════╗
 ║      🕷  網頁爬蟲 Terminal 🕷       ║
 ╚══════════════════════════════════╝
"""

MENU = """
  1) 標題與摘要
  2) 所有連結
  3) 所有圖片
  4) 自訂 CSS selector（例：h2、.title、a.link）
  5) 儲存上次結果（CSV / JSON）
  6) 換一個網址
  0) 離開
"""


def interactive():
    print(color(BANNER, "cyan", "bold"))
    soup, rows = None, []
    while soup is None:
        url = input(color("請輸入網址：", "bold")).strip()
        if not url:
            continue
        try:
            soup = fetch(url)
        except requests.RequestException as e:
            print(color(f"✗ 抓取失敗：{e}", "red"))

    while True:
        print(MENU)
        choice = input(color("選擇功能 > ", "bold")).strip()
        try:
            if choice == "1":
                rows = scrape_summary(soup)
            elif choice == "2":
                rows = scrape_links(soup)
            elif choice == "3":
                rows = scrape_images(soup)
            elif choice == "4":
                sel = input("CSS selector：").strip()
                if not sel:
                    continue
                rows = scrape_selector(soup, sel)
            elif choice == "5":
                default = f"result_{datetime.now():%Y%m%d_%H%M%S}.csv"
                name = input(f"檔名（.csv 或 .json，預設 {default}）：").strip() or default
                save(rows, name)
                continue
            elif choice == "6":
                url = input(color("新網址：", "bold")).strip()
                if url:
                    soup = fetch(url)
                continue
            elif choice == "0":
                print("掰掰 👋")
                return
            else:
                print(color("請輸入 0-6", "yellow"))
                continue
            show(rows)
        except requests.RequestException as e:
            print(color(f"✗ 抓取失敗：{e}", "red"))
        except Exception as e:
            print(color(f"✗ 發生錯誤：{e}", "red"))


# ── 命令列模式 ─────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="網頁爬蟲 Terminal 工具")
    ap.add_argument("url", nargs="?", help="要抓取的網址（不填則進入互動模式）")
    ap.add_argument("-s", "--selector", help="CSS selector")
    ap.add_argument("-l", "--links", action="store_true", help="列出所有連結")
    ap.add_argument("-i", "--images", action="store_true", help="列出所有圖片")
    ap.add_argument("-o", "--output", help="存檔路徑（.csv 或 .json）")
    args = ap.parse_args()

    if not args.url:
        try:
            interactive()
        except (KeyboardInterrupt, EOFError):
            print("\n掰掰 👋")
        return

    try:
        soup = fetch(args.url)
    except requests.RequestException as e:
        print(color(f"✗ 抓取失敗：{e}", "red"))
        sys.exit(1)

    if args.selector:
        rows = scrape_selector(soup, args.selector)
    elif args.links:
        rows = scrape_links(soup)
    elif args.images:
        rows = scrape_images(soup)
    else:
        rows = scrape_summary(soup)
    show(rows)
    if args.output:
        save(rows, args.output)


if __name__ == "__main__":
    main()
