import json
import os
import re
import requests
from datetime import date
from bs4 import BeautifulSoup


URL = "https://www.posterterritory.com/poster-competitions/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    )
}

TODAY = date.today()
CURRENT_YEAR = TODAY.year

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

ROMAN_MONTHS = {
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


# =========================================================
# 文字清理
# =========================================================

def clean_text(text):
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# =========================================================
# 日期解析
# =========================================================

def parse_date(text):
    if not text:
        return ""

    text = clean_text(text)

    # -----------------------------------------------------
    # August 31, 2026
    # September 15 2026
    # -----------------------------------------------------

    m = re.search(
        r"\b("
        r"January|February|March|April|May|June|July|August|"
        r"September|October|November|December"
        r")\s+"
        r"(\d{1,2})(?:st|nd|rd|th)?"
        r"(?:,\s*|\s+)"
        r"(\d{4})\b",
        text,
        re.I,
    )

    if m:
        month = MONTHS[m.group(1).lower()]
        day = int(m.group(2))
        year = int(m.group(3))

        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return ""

    # -----------------------------------------------------
    # 31 August 2026
    # 15 September 2026
    # -----------------------------------------------------

    m = re.search(
        r"\b"
        r"(\d{1,2})(?:st|nd|rd|th)?\s+"
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)"
        r"(?:,\s*|\s+)"
        r"(\d{4})\b",
        text,
        re.I,
    )

    if m:
        day = int(m.group(1))
        month = MONTHS[m.group(2).lower()]
        year = int(m.group(3))

        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return ""

    # -----------------------------------------------------
    # August 18
    # September 15
    #
    # 如果沒有年份，就使用目前年份。
    # -----------------------------------------------------

    m = re.search(
        r"\b("
        r"January|February|March|April|May|June|July|August|"
        r"September|October|November|December"
        r")\s+"
        r"(\d{1,2})(?:st|nd|rd|th)?\b",
        text,
        re.I,
    )

    if m:
        month = MONTHS[m.group(1).lower()]
        day = int(m.group(2))

        try:
            return date(CURRENT_YEAR, month, day).isoformat()
        except ValueError:
            return ""

    # -----------------------------------------------------
    # 15 IX 2026
    # -----------------------------------------------------

    m = re.search(
        r"\b"
        r"(\d{1,2})\s+"
        r"(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)"
        r"\s+(\d{4})\b",
        text,
        re.I,
    )

    if m:
        day = int(m.group(1))
        roman = m.group(2).upper()
        year = int(m.group(3))

        try:
            return date(
                year,
                ROMAN_MONTHS[roman],
                day
            ).isoformat()
        except ValueError:
            return ""

    return ""


# =========================================================
# 從一個比賽區塊取得 Deadline
# =========================================================

def extract_deadline(text):

    text = clean_text(text)

    # 只看 Deadline 後面的內容
    m = re.search(
        r"(?:"
        r"new\s+submission\s+deadline|"
        r"last\s+deadline|"
        r"submission\s+deadline|"
        r"deadline"
        r")"
        r"\s*[:\-]?\s*"
        r"(.{0,120})",
        text,
        re.I,
    )

    if not m:
        return ""

    chunk = m.group(1)

    return parse_date(chunk)


# =========================================================
# 取得 URL
# =========================================================

def get_url_from_block(block):

    for link in block.find_all("a", href=True):

        href = link.get("href", "").strip()

        if (
            href.startswith("http")
            and "posterterritory.com" not in href
        ):
            return href

    # 如果沒有外部網址，使用 PosterTerritory 自己的文章網址
    for link in block.find_all("a", href=True):

        href = link.get("href", "").strip()

        if href.startswith("http"):
            return href

    return ""


# =========================================================
# 判斷是不是分類標題
# =========================================================

def is_excluded_title(title):

    t = clean_text(title).lower()

    excluded = [
        "poster competitions",
        "design programs and summer schools",
        "open calls and platforms with no deadline",
    ]

    if t in excluded:
        return True

    return False


# =========================================================
# 從頁面取得每一個競賽
# =========================================================

def scrape_competitions(soup):

    items = []

    # -----------------------------------------------------
    # PosterTerritory 目前使用標題元素排列內容
    # -----------------------------------------------------

    headings = soup.find_all(
        ["h2", "h3", "h4"]
    )

    print(
        "Found headings:",
        len(headings)
    )

    for i, heading in enumerate(headings):

        title = clean_text(
            heading.get_text(
                " ",
                strip=True
            )
        )

        if not title:
            continue

        if is_excluded_title(title):
            continue

        # -------------------------------------------------
        # 往後收集內容
        # 直到下一個標題
        # -------------------------------------------------

        parts = []

        current = heading

        while True:

            current = current.find_next()

            if not current:
                break

            # 遇到下一個標題
            if (
                current.name in
                ["h1", "h2", "h3", "h4"]
            ):
                break

            text = clean_text(
                current.get_text(
                    " ",
                    strip=True
                )
            )

            if text:
                parts.append(text)

            # 防止一次跑太遠
            if len(parts) > 30:
                break

        block_text = clean_text(
            title + " " + " ".join(parts)
        )

        # -------------------------------------------------
        # 必須有 Deadline
        # -------------------------------------------------

        if "deadline" not in block_text.lower():
            continue

        deadline = extract_deadline(
            block_text
        )

        if not deadline:
            print(
                "No deadline:",
                title
            )
            continue

        # -------------------------------------------------
        # 排除已經過期的比賽
        # -------------------------------------------------

        try:
            deadline_date = date.fromisoformat(
                deadline
            )
        except ValueError:
            continue

        if deadline_date < TODAY:
            print(
                "Expired:",
                title,
                deadline
            )
            continue

        # -------------------------------------------------
        # 找這個標題後面的連結
        # -------------------------------------------------

        links = []

        current = heading

        for _ in range(20):

            current = current.find_next()

            if not current:
                break

            if current.name in [
                "h1",
                "h2",
                "h3",
                "h4"
            ]:
                break

            if current.name == "a":
                href = current.get(
                    "href",
                    ""
                ).strip()

                if href.startswith("http"):
                    links.append(href)

        if not links:
            print(
                "No URL:",
                title
            )
            continue

        # -------------------------------------------------
        # 優先選 More 連結
        # -------------------------------------------------

        url = links[0]

        # -------------------------------------------------
        # 去重
        # -------------------------------------------------

        duplicate = False

        for old in items:

            if (
                old["title"].lower()
                == title.lower()
            ):
                duplicate = True
                break

        if duplicate:
            continue

        items.append(
            {
                "title": title,
                "deadline": deadline,
                "resultDate": "",
                "participating": False,
                "result": "pending",
                "url": url,
            }
        )

    return items


# =========================================================
# 主程式
# =========================================================

def main():

    print(
        "Downloading PosterTerritory..."
    )

    response = requests.get(
        URL,
        timeout=30,
        headers=HEADERS
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    items = scrape_competitions(
        soup
    )

    print(
        "Future competitions:",
        len(items)
    )

    # -----------------------------------------------------
    # 安全機制
    # -----------------------------------------------------

    if not items:

        raise SystemExit(
            "No future competitions parsed; "
            "refusing to overwrite competitions.json"
        )

    # -----------------------------------------------------
    # 讀取原本資料
    # -----------------------------------------------------

    old = []

    if os.path.exists(
        "competitions.json"
    ):

        try:

            with open(
                "competitions.json",
                "r",
                encoding="utf-8"
            ) as f:

                old = json.load(f)

        except Exception:

            old = []

    old_map = {}

    for item in old:

        title = clean_text(
            item.get(
                "title",
                ""
            )
        )

        if title:

            old_map[
                title.lower()
            ] = item

    # -----------------------------------------------------
    # 保留參賽 / 結果資料
    # -----------------------------------------------------

    for item in items:

        old_item = old_map.get(
            item["title"].lower()
        )

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

    # -----------------------------------------------------
    # 依截止日期排序
    # -----------------------------------------------------

    items.sort(
        key=lambda x: (
            x["deadline"],
            x["title"].lower()
        )
    )

    # -----------------------------------------------------
    # 寫入 competitions.json
    # -----------------------------------------------------

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

        f.write("\n")

    print(
        "Updated",
        len(items),
        "competitions"
    )

    print("")
    print("========== RESULTS ==========")

    for item in items:

        print(
            item["deadline"],
            "|",
            item["title"]
        )

    print(
        "=============================="
    )


if __name__ == "__main__":
    main()
