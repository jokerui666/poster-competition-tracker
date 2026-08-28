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


def clean_text(text):
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def parse_date(text):

    text = clean_text(text)

    # August 31, 2026
    m = re.search(
        r"\b"
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)"
        r"\s+"
        r"(\d{1,2})"
        r"(?:st|nd|rd|th)?"
        r"(?:,\s*|\s+)"
        r"(\d{4})"
        r"\b",
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


    # 31 August 2026
    m = re.search(
        r"\b"
        r"(\d{1,2})"
        r"(?:st|nd|rd|th)?"
        r"\s+"
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)"
        r"(?:,\s*|\s+)"
        r"(\d{4})"
        r"\b",
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


    # August 31  (沒有年份)
    m = re.search(
        r"\b"
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)"
        r"\s+"
        r"(\d{1,2})"
        r"(?:st|nd|rd|th)?"
        r"\b",
        text,
        re.I,
    )

    if m:

        month = MONTHS[m.group(1).lower()]
        day = int(m.group(2))

        try:
            return date(TODAY.year, month, day).isoformat()
        except ValueError:
            return ""


    # 15 IX 2026
    m = re.search(
        r"\b"
        r"(\d{1,2})\s+"
        r"(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)"
        r"\s+"
        r"(\d{4})"
        r"\b",
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


def extract_deadline(text):

    text = clean_text(text)

    patterns = [
        r"(?:New submission deadline)\s*[:\-]?\s*(.{0,120})",
        r"(?:Last deadline)\s*[:\-]?\s*(.{0,120})",
        r"(?:Deadline)\s*[:\-]?\s*(.{0,120})",
    ]

    for pattern in patterns:

        m = re.search(
            pattern,
            text,
            re.I
        )

        if m:

            result = parse_date(
                m.group(1)
            )

            if result:
                return result

    return ""


def get_title_from_text(text):

    lines = []

    for line in text.splitlines():

        line = clean_text(line)

        if not line:
            continue

        lines.append(line)

    for line in lines:

        lower = line.lower()

        if (
            "deadline" not in lower
            and "more" not in lower
            and len(line) > 4
        ):
            return line

    return ""


def scrape_page(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    # -----------------------------------------------------
    # 取得主要內容區
    # -----------------------------------------------------

    main = (
        soup.find("main")
        or soup.find(
            "div",
            class_=re.compile(
                r"content|main|entry",
                re.I
            )
        )
        or soup.body
    )

    if not main:
        return []

    # -----------------------------------------------------
    # 取得所有文字
    # -----------------------------------------------------

    text = main.get_text(
        "\n",
        strip=True
    )

    text = clean_text(
        text.replace("\n", " ")
    )

    print(
        "Page text length:",
        len(text)
    )

    # -----------------------------------------------------
    # 以 Deadline 當作每筆資料的中心
    # -----------------------------------------------------

    matches = list(
        re.finditer(
            r"(?:New submission deadline|"
            r"Last deadline|"
            r"Deadline)"
            r"\s*[:\-]?",
            text,
            re.I
        )
    )

    print(
        "Deadline markers:",
        len(matches)
    )

    items = []

    for i, match in enumerate(matches):

        start = max(
            0,
            match.start() - 600
        )

        end = min(
            len(text),
            match.end() + 180
        )

        chunk = text[start:end]

        deadline = extract_deadline(
            chunk
        )

        if not deadline:
            continue

        try:
            d = date.fromisoformat(
                deadline
            )
        except ValueError:
            continue

        if d < TODAY:
            continue

        # -------------------------------------------------
        # 從 Deadline 前面尋找標題
        # -------------------------------------------------

        before = text[
            start:match.start()
        ]

        before_parts = [
            clean_text(x)
            for x in re.split(
                r"\s{2,}|(?=[A-Z“\"])",
                before
            )
            if clean_text(x)
        ]

        title = ""

        # 先找最接近 Deadline 的合理文字
        words = before.split()

        if words:

            # 從後往前找一個合理長度的標題
            candidate = ""

            for j in range(
                max(0, len(words) - 20),
                len(words)
            ):

                candidate += (
                    (" " if candidate else "")
                    + words[j]
                )

            candidate = clean_text(
                candidate
            )

            if candidate:
                title = candidate

        # -------------------------------------------------
        # 如果上面抓得太長，再從附近文字判斷
        # -------------------------------------------------

        if len(title) > 180:

            title = title[-180:]

            if "More" in title:

                title = title.split(
                    "More"
                )[-1].strip()

        # -------------------------------------------------
        # 清理常見雜訊
        # -------------------------------------------------

        title = re.sub(
            r"^(Categories?:.*?)(?=[A-Z])",
            "",
            title,
            flags=re.I
        )

        title = clean_text(
            title
        )

        if not title:
            continue

        # -------------------------------------------------
        # 找附近的網址
        # -------------------------------------------------

        url = ""

        for link in main.find_all(
            "a",
            href=True
        ):

            href = link.get(
                "href",
                ""
            ).strip()

            link_text = clean_text(
                link.get_text(
                    " ",
                    strip=True
                )
            )

            if (
                link_text.lower()
                == "more"
                and href.startswith("http")
            ):
                url = href
                break

        # -------------------------------------------------
        # 去除明顯不是比賽的標題
        # -------------------------------------------------

        bad_titles = [
            "poster competitions",
            "design programs",
            "summer schools",
            "open calls",
            "platforms",
        ]

        if any(
            x in title.lower()
            for x in bad_titles
        ):
            continue

        # -------------------------------------------------
        # 去重
        # -------------------------------------------------

        exists = False

        for old in items:

            if (
                old["title"].lower()
                == title.lower()
            ):
                exists = True
                break

        if exists:
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

    print(
        "HTTP status:",
        response.status_code
    )

    print(
        "Downloaded bytes:",
        len(response.content)
    )

    items = scrape_page(
        response.text
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
    # 讀取舊資料
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
    # 保留參賽狀態
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
    # 日期排序
    # -----------------------------------------------------

    items.sort(
        key=lambda x: (
            x["deadline"],
            x["title"].lower()
        )
    )

    # -----------------------------------------------------
    # 寫入 JSON
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

    print("")
    print(
        "Updated",
        len(items),
        "competitions"
    )

    print("")
    print(
        "========== RESULTS =========="
    )

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
