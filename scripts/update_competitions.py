import json
import os
import re
from datetime import date

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
        r"\b"
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)"
        r"\s+(\d{1,2})"
        r"(?:st|nd|rd|th)?"
        r"(?:,\s*|\s+)"
        r"(\d{4})\b",

        r"\b"
        r"(\d{1,2})"
        r"(?:st|nd|rd|th)?"
        r"\s+"
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)"
        r"(?:,\s*|\s+)"
        r"(\d{4})\b",
    ]

    for index, pattern in enumerate(patterns):

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if not match:
            continue

        if index == 0:
            month = MONTHS[match.group(1).lower()]
            day = int(match.group(2))
            year = int(match.group(3))
        else:
            day = int(match.group(1))
            month = MONTHS[match.group(2).lower()]
            year = int(match.group(3))

        try:
            return date(
                year,
                month,
                day
            ).isoformat()

        except ValueError:
            return ""

    return ""


def clean_title(title):
    """
    清理 PosterTerritory 標題中的網站雜訊。
    """

    title = clean_text(title)

    if not title:
        return ""


    # ---------------------------------------------
    # 移除 Categories 後面的分類資訊
    # ---------------------------------------------

    title = re.split(
        r"\bCategories\s*:",
        title,
        maxsplit=1,
        flags=re.IGNORECASE
    )[0]


    # ---------------------------------------------
    # 移除 Last Deadline 後面的內容
    # ---------------------------------------------

    title = re.split(
        r"\bLast\s+Deadline\b",
        title,
        maxsplit=1,
        flags=re.IGNORECASE
    )[0]


    # ---------------------------------------------
    # 移除 Deadline 後面的內容
    # ---------------------------------------------

    title = re.split(
        r"\bDeadline\b",
        title,
        maxsplit=1,
        flags=re.IGNORECASE
    )[0]


    # ---------------------------------------------
    # 移除 Brand Awards and Design Awards
    # ---------------------------------------------

    title = re.sub(
        r"\s+Brand Awards and Design Awards\.?",
        "",
        title,
        flags=re.IGNORECASE
    )


    # ---------------------------------------------
    # 移除最後單獨出現的 Last
    # ---------------------------------------------

    title = re.sub(
        r"\s+\bLast\b\s*$",
        "",
        title,
        flags=re.IGNORECASE
    )


    # ---------------------------------------------
    # 移除最後的標點符號
    # ---------------------------------------------

    title = title.strip(
        " \t\r\n-–—:;,.|"
    )

    return clean_text(title)


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


def extract_competitions(soup):

    elements = soup.find_all(
        [
            "h1",
            "h2",
            "h3",
            "h4",
            "p",
            "a",
        ]
    )

    print(
        "Scannable elements:",
        len(elements)
    )

    results = []

    pending_title = ""
    pending_deadline = ""

    for element in elements:

        text = clean_text(
            element.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue


        # =============================================
        # More 連結
        # =============================================

        if element.name == "a":

            if text.lower() != "more":
                continue

            url = clean_text(
                element.get(
                    "href",
                    ""
                )
            )

            if not url:
                continue

            if not pending_title:
                continue

            if not pending_deadline:
                continue

            title = clean_title(
                pending_title
            )

            if not title:
                pending_title = ""
                pending_deadline = ""
                continue

            item = {
                "title": title,
                "deadline": pending_deadline,
                "resultDate": "",
                "participating": False,
                "result": "pending",
                "url": url,
            }

            duplicate = False

            for old in results:

                if old["url"] == url:
                    duplicate = True
                    break

                if (
                    old["title"].lower()
                    == title.lower()
                ):
                    duplicate = True
                    break

            if not duplicate:

                results.append(item)

                print(
                    f"FOUND {len(results)}:"
                )

                print(
                    "  TITLE:",
                    title
                )

                print(
                    "  DEADLINE:",
                    pending_deadline
                )

                print(
                    "  URL:",
                    url
                )

                print("")

            pending_title = ""
            pending_deadline = ""

            continue


        # =============================================
        # Deadline
        # =============================================

        if re.search(
            r"\bdeadline\b",
            text,
            flags=re.IGNORECASE
        ):

            deadline = parse_date(
                text
            )

            if deadline:

                pending_deadline = deadline

                title_part = re.split(
                    r"\bDeadline\b",
                    text,
                    maxsplit=1,
                    flags=re.IGNORECASE
                )[0]

                title_part = clean_title(
                    title_part
                )

                if title_part:
                    pending_title = title_part

                continue


        # =============================================
        # 標題
        # =============================================

        if not pending_deadline:

            if is_noise(text):
                continue

            if len(text) > 300:
                continue

            candidate = clean_title(
                text
            )

            if not candidate:
                continue

            pending_title = candidate


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

    except Exception:
        pass

    return []


def preserve_old_user_data(
    new_items,
    old_items
):

    old_by_url = {}
    old_by_title = {}

    for item in old_items:

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
            old_by_url[url] = item

        if title:
            old_by_title[
                title.lower()
            ] = item


    for item in new_items:

        old = (
            old_by_url.get(
                item["url"]
            )
            or
            old_by_title.get(
                item["title"].lower()
            )
        )

        if old is None:
            continue

        item["participating"] = old.get(
            "participating",
            False
        )

        item["result"] = old.get(
            "result",
            "pending"
        )

        item["resultDate"] = old.get(
            "resultDate",
            ""
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
        "Downloading PosterTerritory..."
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
            future.append(item)

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

    # ---------------------------------------------
    # 安全保護
    # ---------------------------------------------

    if len(competitions) < 3:

        print(
            "ERROR: Too few competitions parsed."
        )

        print(
            "Refusing to overwrite competitions.json."
        )

        raise SystemExit(1)

    old_data = load_old_data()

    preserve_old_user_data(
        competitions,
        old_data
    )

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
