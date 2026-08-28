import json
import os
import re
import requests
from bs4 import BeautifulSoup

URL = "https://www.posterterritory.com/poster-competitions/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    )
}

MONTHS = {
    "january": "01",
    "february": "02",
    "march": "03",
    "april": "04",
    "may": "05",
    "june": "06",
    "july": "07",
    "august": "08",
    "september": "09",
    "october": "10",
    "november": "11",
    "december": "12",
}


def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def parse_date(text):
    text = clean_text(text)

    patterns = [
        # September 15, 2026
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s*(2026)\b",

        # 15 September 2026
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(2026)\b",

        # September 15
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(\d{1,2})(?:st|nd|rd|th)?\b",

        # 15 IX 2026
        r"\b(\d{1,2})\s+(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)\s*(2026)?\b",
    ]

    for i, pattern in enumerate(patterns):
        match = re.search(pattern, text, re.I)

        if not match:
            continue

        if i == 0:
            month = match.group(1).lower()
            day = int(match.group(2))
            year = int(match.group(3))

        elif i == 1:
            day = int(match.group(1))
            month = match.group(2).lower()
            year = int(match.group(3))

        elif i == 2:
            month = match.group(1).lower()
            day = int(match.group(2))
            year = 2026

        else:
            day = int(match.group(1))
            roman = match.group(2).upper()
            year = int(match.group(3)) if match.group(3) else 2026

            roman_months = {
                "I": 1,
                "II": 2,
                "III": 3,
                "IV": 4,
                "V": 5,
                "VI": 6,
                "VII": 7,
                "VIII": 8,
                "IX": 9,
                "X": 10,
                "XI": 11,
                "XII": 12,
            }

            return f"{year:04d}-{roman_months[roman]:02d}-{day:02d}"

        return f"{year:04d}-{MONTHS[month]:02d}-{day:02d}"

    return ""


def get_title(element):
    # 優先使用標題元素
    for tag in element.find_all(["h1", "h2", "h3", "h4"], limit=3):
        title = clean_text(tag.get_text(" ", strip=True))
        if title:
            return title

    # 找連結文字
    for link in element.find_all("a"):
        title = clean_text(link.get_text(" ", strip=True))
        if len(title) >= 5 and title.lower() not in {"more", "read more"}:
            return title

    return ""


def main():
    response = requests.get(
        URL,
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # 取得主要內容區域
    main_area = (
        soup.find("main")
        or soup.find("article")
        or soup.body
    )

    if not main_area:
        raise SystemExit("Unable to locate PosterTerritory content")

    items = []

    # 找出所有含有 Deadline 的內容區塊
    for element in main_area.find_all(["article", "section", "div", "li"]):

        text = clean_text(element.get_text(" ", strip=True))

        if "deadline" not in text.lower():
            continue

        # 排除整個分類區塊
        if len(text) > 1200:
            continue

        title = get_title(element)

        if not title:
            continue

        if title.lower() in {
            "poster competitions",
            "design programs and summer schools",
            "open calls and platforms with no deadline",
        }:
            continue

        deadline = parse_date(text)

        if not deadline:
            continue

        items.append({
            "title": title,
            "deadline": deadline,
            "resultDate": "",
            "participating": False,
            "result": "pending"
        })

    # 備援：直接從文字節點附近尋找比賽名稱
    if not items:
        text = clean_text(main_area.get_text(" ", strip=True))

        chunks = re.split(
            r"\b(?:More|Read more)\b",
            text,
            flags=re.I
        )

        for chunk in chunks:
            if "deadline" not in chunk.lower():
                continue

            deadline = parse_date(chunk)

            if not deadline:
                continue

            lines = [
                clean_text(x)
                for x in re.split(r"\n|•", chunk)
                if clean_text(x)
            ]

            title = ""

            for line in lines:
                lower = line.lower()

                if (
                    "deadline" not in lower
                    and len(line) >= 5
                    and len(line) <= 180
                ):
                    title = line
                    break

            if title:
                items.append({
                    "title": title,
                    "deadline": deadline,
                    "resultDate": "",
                    "participating": False,
                    "result": "pending"
                })

    # 去除重複
    unique = {}

    for item in items:
        key = item["title"].strip().lower()

        if key not in unique:
            unique[key] = item

    items = list(unique.values())

    if not items:
        raise SystemExit(
            "No competitions parsed; refusing to overwrite competitions.json"
        )

    # 讀取舊資料
    old = []

    if os.path.exists("competitions.json"):
        with open(
            "competitions.json",
            "r",
            encoding="utf-8"
        ) as f:
            old = json.load(f)

    old_map = {
        item.get("title", "").strip().lower(): item
        for item in old
        if item.get("title")
    }

    # 保留使用者自己的資料
    for item in items:
        old_item = old_map.get(item["title"].strip().lower())

        if old_item:
            item["participating"] = old_item.get(
                "participating",
                False
            )

            item["result"] = old_item.get(
                "result",
                "pending"
            )

            item["resultDate"] = old_item.get(
                "resultDate",
                ""
            )

    # 依截止日期排序
    items.sort(
        key=lambda x: (
            x.get("deadline") or "9999-12-31",
            x.get("title", "")
        )
    )

    with open(
        "competitions.json",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            items,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(
        f"Updated {len(items)} competitions"
    )


if __name__ == "__main__":
    main()
