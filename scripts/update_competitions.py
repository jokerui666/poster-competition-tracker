import json
import os
import re
import requests
from bs4 import BeautifulSoup

API_URL = "https://www.posterterritory.com/wp-json/wp/v2/posts"

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

MONTHS_SHORT = {
    "jan": "01",
    "feb": "02",
    "mar": "03",
    "apr": "04",
    "may": "05",
    "jun": "06",
    "jul": "07",
    "aug": "08",
    "sep": "09",
    "sept": "09",
    "oct": "10",
    "nov": "11",
    "dec": "12",
}


def clean_text(text):
    text = re.sub(r"\s+", " ", text or "")
    return text.strip()


def parse_date(text):
    """
    將常見 Deadline 日期轉成 YYYY-MM-DD。
    """

    if not text:
        return ""

    text = clean_text(text)

    # 例如：
    # September 15, 2026
    # September 15 2026
    # Sep 15, 2026
    # Sep 15 2026
    pattern = re.compile(
        r"\b"
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|"
        r"Sep|Sept|Oct|Nov|Dec)"
        r"\s+"
        r"(\d{1,2})"
        r"(?:st|nd|rd|th)?"
        r"(?:,\s*|\s+)"
        r"(20\d{2})"
        r"\b",
        re.I,
    )

    match = pattern.search(text)

    if match:
        month = MONTHS.get(match.group(1).lower())
        if not month:
            month = MONTHS_SHORT.get(match.group(1).lower())

        if month:
            day = int(match.group(2))
            year = int(match.group(3))
            return f"{year:04d}-{month}-{day:02d}"

    # 例如：
    # 15 September 2026
    # 15 Sep 2026
    pattern2 = re.compile(
        r"\b"
        r"(\d{1,2})"
        r"(?:st|nd|rd|th)?"
        r"\s+"
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|"
        r"Sep|Sept|Oct|Nov|Dec)"
        r"\s+"
        r"(20\d{2})"
        r"\b",
        re.I,
    )

    match = pattern2.search(text)

    if match:
        day = int(match.group(1))
        month = MONTHS.get(match.group(2).lower())

        if not month:
            month = MONTHS_SHORT.get(match.group(2).lower())

        if month:
            year = int(match.group(3))
            return f"{year:04d}-{month}-{day:02d}"

    return ""


def extract_deadline(content):
    """
    從文章內容找 Deadline。
    """

    text = clean_text(content)

    # 優先找 Deadline 附近的日期
    deadline_patterns = [
        r"Deadline\s*[:\-]?\s*([^.;|]{0,100})",
        r"Last Deadline\s*[:\-]?\s*([^.;|]{0,100})",
        r"Submission Deadline\s*[:\-]?\s*([^.;|]{0,100})",
        r"New submission deadline\s*[:\-]?\s*([^.;|]{0,100})",
        r"Submission deadline\s*[:\-]?\s*([^.;|]{0,100})",
    ]

    for pattern in deadline_patterns:
        match = re.search(pattern, text, re.I)

        if match:
            date = parse_date(match.group(1))

            if date:
                return date

    # 如果 Deadline 前後格式比較特殊，再直接全文找日期
    date = parse_date(text)

    return date


def fetch_posts():
    posts = []

    for page in range(1, 10):

        params = {
            "per_page": 100,
            "page": page,
            "orderby": "date",
            "order": "desc",
        }

        response = requests.get(
            API_URL,
            params=params,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
        )

        if response.status_code == 400:
            break

        response.raise_for_status()

        batch = response.json()

        if not batch:
            break

        posts.extend(batch)

        if len(batch) < 100:
            break

    return posts


def main():

    print("Fetching PosterTerritory posts...")

    posts = fetch_posts()

    print(f"Fetched {len(posts)} posts")

    items = []

    excluded_titles = {
        "Poster Competitions",
        "Design programs and Summer Schools",
        "Open calls and platforms with no deadline",
    }

    for post in posts:

        title = clean_text(
            BeautifulSoup(
                post.get("title", {}).get("rendered", ""),
                "html.parser"
            ).get_text(" ", strip=True)
        )

        if not title:
            continue

        if title in excluded_titles:
            continue

        content_html = post.get("content", {}).get("rendered", "")

        content_text = BeautifulSoup(
            content_html,
            "html.parser"
        ).get_text(" ", strip=True)

        content_text = clean_text(content_text)

        deadline = extract_deadline(content_text)

        if not deadline:
            continue

        link = post.get("link", "")

        item = {
            "title": title,
            "deadline": deadline,
            "resultDate": "",
            "participating": False,
            "result": "pending",
            "url": link,
        }

        items.append(item)

    # 去除重複標題
    unique = {}

    for item in items:
        unique[item["title"]] = item

    items = list(unique.values())

    print(f"Parsed {len(items)} competitions")

    if not items:
        raise SystemExit(
            "No competitions parsed; refusing to overwrite competitions.json"
        )

    # 保留原本 competitions.json 中的參賽與結果資料
    old = []

    if os.path.exists("competitions.json"):

        try:
            with open(
                "competitions.json",
                "r",
                encoding="utf-8"
            ) as f:
                old = json.load(f)

        except Exception:
            old = []

    old_map = {
        item.get("title"): item
        for item in old
        if isinstance(item, dict)
    }

    for item in items:

        old_item = old_map.get(item["title"])

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
        key=lambda x: x.get("deadline", "")
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
