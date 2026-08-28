import json
import os
import re
from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


URL = "https://www.posterterritory.com/poster-competitions/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


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


def clean_text(text):
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def parse_date(text):

    text = clean_text(text)

    patterns = [

        # August 31, 2026
        re.compile(
            r"\b"
            r"(January|February|March|April|May|June|July|August|"
            r"September|October|November|December)"
            r"\s+(\d{1,2})"
            r"(?:st|nd|rd|th)?"
            r"(?:,\s*|\s+)"
            r"(\d{4})"
            r"\b",
            re.IGNORECASE,
        ),

        # 31 August 2026
        re.compile(
            r"\b"
            r"(\d{1,2})"
            r"(?:st|nd|rd|th)?"
            r"\s+"
            r"(January|February|March|April|May|June|July|August|"
            r"September|October|November|December)"
            r"(?:,\s*|\s+)"
            r"(\d{4})"
            r"\b",
            re.IGNORECASE,
        ),
    ]

    for index, pattern in enumerate(patterns):

        match = pattern.search(text)

        if not match:
            continue

        try:

            if index == 0:

                month = MONTHS[
                    match.group(1).lower()
                ]

                day = int(
                    match.group(2)
                )

                year = int(
                    match.group(3)
                )

            else:

                day = int(
                    match.group(1)
                )

                month = MONTHS[
                    match.group(2).lower()
                ]

                year = int(
                    match.group(3)
                )

            return date(
                year,
                month,
                day
            ).isoformat()

        except ValueError:

            return ""

    return ""


def clean_title(title):

    title = clean_text(title)

    if not title:
        return ""

    # Categories 後面全部不要
    title = re.split(
        r"\bCategories\s*:",
        title,
        maxsplit=1,
        flags=re.IGNORECASE
    )[0]

    # Deadline 後面不要
    title = re.split(
        r"\bDeadline\b",
        title,
        maxsplit=1,
        flags=re.IGNORECASE
    )[0]

    # Last Deadline 後面不要
    title = re.split(
        r"\bLast\s+Deadline\b",
        title,
        maxsplit=1,
        flags=re.IGNORECASE
    )[0]

    # 移除 Brand Awards and Design Awards
    title = re.sub(
        r"\s+Brand Awards and Design Awards\.?",
        "",
        title,
        flags=re.IGNORECASE
    )

    # 移除尾端 Last
    title = re.sub(
        r"\s+\bLast\b\s*$",
        "",
        title,
        flags=re.IGNORECASE
    )

    # 移除尾端 More
    title = re.sub(
        r"\s+\bMore\b\s*$",
        "",
        title,
        flags=re.IGNORECASE
    )

    return clean_text(
        title.strip(
            " \t\r\n-–—:;,.|"
        )
    )


def is_noise(text):

    text = clean_text(text)

    if not text:
        return True

    noise = {
        "more",
        "read more",
        "posterterritory",
        "poster competitions",
        "open calls",
        "submit",
        "submission",
        "discover",
        "learn more",
    }

    return text.lower() in noise


def is_valid_external_url(url):

    if not url:
        return False

    url = urljoin(
        URL,
        url
    )

    lowered = url.lower()

    # #content 這種頁內連結不要
    if "#" in lowered:
        return False

    # PosterTerritory 自己的首頁 / 分類頁不要
    if "posterterritory.com" in lowered:

        if (
            lowered.rstrip("/")
            == "https://www.posterterritory.com"
        ):
            return False

        if "/poster-competitions" in lowered:
            return False

    return True


def extract_competitions(soup):

    print(
        "Scanning page structure..."
    )

    # ------------------------------------------------
    # 只按照真正的內容順序讀取
    # ------------------------------------------------

    elements = soup.find_all(
        [
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "p",
            "a",
        ]
    )

    print(
        "Content elements:",
        len(elements)
    )

    results = []

    current_title = ""
    current_deadline = ""

    # 最近一次找到的 More
    # 用來建立完整項目

    for element in elements:

        text = clean_text(
            element.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        # ==================================================
        # ① More
        # ==================================================

        if element.name == "a":

            if text.lower() != "more":
                continue

            href = clean_text(
                element.get(
                    "href",
                    ""
                )
            )

            # 沒有標題或 deadline，
            # 不能建立比賽
            if not current_title:
                continue

            if not current_deadline:
                continue

            if not is_valid_external_url(
                href
            ):
                continue

            url = urljoin(
                URL,
                href
            )

            title = clean_title(
                current_title
            )

            if not title:
                continue

            if is_noise(title):
                continue

            item = {
                "title": title,
                "deadline": current_deadline,
                "resultDate": "",
                "participating": False,
                "result": "pending",
                "url": url,
            }

            # 去重
            duplicate = False

            for old in results:

                if (
                    old["url"].lower()
                    == url.lower()
                ):
                    duplicate = True
                    break

                if (
                    old["title"].lower()
                    == title.lower()
                ):
                    duplicate = True
                    break

            if not duplicate:

                results.append(
                    item
                )

                print(
                    f"FOUND {len(results)}:"
                )

                print(
                    "  TITLE:",
                    title
                )

                print(
                    "  DEADLINE:",
                    current_deadline
                )

                print(
                    "  URL:",
                    url
                )

                print("")

            # 一個 competition 完成
            current_title = ""
            current_deadline = ""

            continue

        # ==================================================
        # ② Deadline
        # ==================================================

        parsed = parse_date(
            text
        )

        if (
            parsed
            and re.search(
                r"\bdeadline\b",
                text,
                re.IGNORECASE
            )
        ):

            current_deadline = parsed

            # Deadline 前面的文字可能就是標題
            before = re.split(
                r"\bdeadline\b",
                text,
                maxsplit=1,
                flags=re.IGNORECASE
            )[0]

            before = clean_title(
                before
            )

            if before:

                # 如果這一段本身包含真正標題
                current_title = before

            continue

        # ==================================================
        # ③ 標題
        # ==================================================

        # 如果目前還沒有 deadline，
        # 才把內容當成可能的標題
        if not current_deadline:

            if is_noise(text):
                continue

            # 太長通常是整段網站介紹，不是比賽名稱
            if len(text) > 250:
                continue

            candidate = clean_title(
                text
            )

            if not candidate:
                continue

            # 排除網站區塊標題
            blocked = {
                "poster competitions",
                "design programs and summer schools",
                "open calls and platforms with no deadline",
                "design for change",
            }

            if candidate.lower() in blocked:
                continue

            current_title = candidate

    return results


def load_old_data():

    if not os.path.exists(
        "competitions.json"
    ):
        return []

    try:

        with open(
            "competitions.json",
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        if isinstance(data, list):
            return data

    except Exception as error:

        print(
            "Warning:",
            error
        )

    return []


def preserve_old_user_data(
    new_items,
    old_items
):

    old_by_url = {}
    old_by_title = {}

    for item in old_items:

        if not isinstance(
            item,
            dict
        ):
            continue

        url = clean_text(
            item.get(
                "url",
                ""
            )
        )

        title = clean_text(
            item.get(
                "title",
                ""
            )
        )

        if url:
            old_by_url[
                url.lower()
            ] = item

        if title:
            old_by_title[
                title.lower()
            ] = item

    count = 0

    for item in new_items:

        old = (
            old_by_url.get(
                item["url"].lower()
            )
            or
            old_by_title.get(
                item["title"].lower()
            )
        )

        if old is None:
            continue

        item["participating"] = bool(
            old.get(
                "participating",
                False
            )
        )

        item["result"] = (
            old.get(
                "result",
                "pending"
            )
            or "pending"
        )

        item["resultDate"] = (
            old.get(
                "resultDate",
                ""
            )
            or ""
        )

        count += 1

    print(
        "Preserved existing user data:",
        count
    )


def save_json(items):

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


def main():

    print(
        "======================================"
    )

    print(
        "Downloading PosterTerritory..."
    )

    print(
        "======================================"
    )

    response = requests.get(
        URL,
        headers=HEADERS,
        timeout=30
    )

    print(
        "HTTP:",
        response.status_code
    )

    print(
        "Bytes:",
        len(response.content)
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    print(
        "Page downloaded."
    )

    print("")

    competitions = extract_competitions(
        soup
    )

    print("")
    print(
        "Parsed competitions:",
        len(competitions)
    )

    # ------------------------------------------------
    # 只保留今天及未來
    # ------------------------------------------------

    today = date.today()

    future = []

    for item in competitions:

        try:

            deadline = date.fromisoformat(
                item["deadline"]
            )

        except ValueError:

            continue

        if deadline >= today:

            future.append(
                item
            )

    competitions = future

    competitions.sort(
        key=lambda item: (
            item["deadline"],
            item["title"].lower()
        )
    )

    print(
        "Future competitions:",
        len(competitions)
    )

    # ------------------------------------------------
    # 安全保護
    # ------------------------------------------------

    if len(competitions) < 3:

        print("")
        print(
            "ERROR: Too few competitions parsed."
        )

        print(
            "Refusing to overwrite competitions.json."
        )

        raise SystemExit(1)

    # ------------------------------------------------
    # 保留舊資料
    # ------------------------------------------------

    old_data = load_old_data()

    preserve_old_user_data(
        competitions,
        old_data
    )

    # ------------------------------------------------
    # 儲存
    # ------------------------------------------------

    save_json(
        competitions
    )

    print("")
    print(
        "======================================"
    )

    print(
        "competitions.json updated successfully."
    )

    print(
        "Total:",
        len(competitions)
    )

    print(
        "======================================"
    )

    print("")

    for number, item in enumerate(
        competitions,
        start=1
    ):

        print(
            f"{number}. "
            f"{item['deadline']} | "
            f"{item['title']}"
        )

        print(
            f"   {item['url']}"
        )


if __name__ == "__main__":
    main()
