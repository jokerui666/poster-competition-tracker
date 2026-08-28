import json
import os
import re
from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


URL = "https://www.posterterritory.com/poster-competitions/"

BASE_URL = "https://www.posterterritory.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
        re.compile(
            r"\b"
            r"(January|February|March|April|May|June|July|August|"
            r"September|October|November|December)"
            r"\s+"
            r"(\d{1,2})"
            r"(?:st|nd|rd|th)?"
            r"(?:,\s*|\s+)"
            r"(\d{4})"
            r"\b",
            re.IGNORECASE,
        ),
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

    # 移除 Categories 後面的內容
    title = re.split(
        r"\bCategories\s*:",
        title,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]

    # 移除 Deadline 後面的內容
    title = re.split(
        r"\bDeadline\b",
        title,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]

    # 移除 Last Deadline 後面的內容
    title = re.split(
        r"\bLast\s+Deadline\b",
        title,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]

    # 移除網站常見尾巴
    title = re.sub(
        r"\s+Brand Awards and Design Awards\.?",
        "",
        title,
        flags=re.IGNORECASE,
    )

    title = re.sub(
        r"\s+\bLast\b\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    )

    title = re.sub(
        r"\s+\bMore\b\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    )

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
        "deadline",
    }

    return text.lower() in noise


def is_competition_url(url):
    if not url:
        return False

    absolute = urljoin(
        BASE_URL,
        url
    )

    lowered = absolute.lower()

    if "posterterritory.com" not in lowered:
        return False

    if lowered.rstrip("/") == BASE_URL.lower():
        return False

    if "/poster-competitions/" in lowered:
        return False

    if "/category/" in lowered:
        return False

    if "/author/" in lowered:
        return False

    if "/page/" in lowered:
        return False

    return True


def find_container(anchor):
    """
    從 More / competition link 往上找可能包含
    標題與 Deadline 的區塊。
    """

    current = anchor

    for _ in range(8):

        if current is None:
            break

        text = clean_text(
            current.get_text(
                " ",
                strip=True
            )
        )

        if (
            text
            and "deadline" in text.lower()
            and len(text) <= 1200
        ):
            return current

        current = current.parent

    return anchor.parent


def extract_title_from_container(container):
    """
    優先找標題元素。
    如果沒有，再從文字中清理。
    """

    headings = container.find_all(
        [
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        ]
    )

    for heading in headings:

        text = clean_text(
            heading.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        title = clean_title(text)

        if (
            title
            and len(title) >= 4
            and not is_noise(title)
        ):
            return title

    # 如果沒有 heading，
    # 嘗試尋找較像標題的連結文字

    links = container.find_all("a")

    candidates = []

    for link in links:

        text = clean_text(
            link.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        if text.lower() == "more":
            continue

        if is_noise(text):
            continue

        if len(text) > 300:
            continue

        candidates.append(text)

    if candidates:

        candidates.sort(
            key=len,
            reverse=True
        )

        title = clean_title(
            candidates[0]
        )

        if title:
            return title

    # 最後才從整個 container 文字處理

    text = clean_text(
        container.get_text(
            " ",
            strip=True
        )
    )

    if not text:
        return ""

    title = re.split(
        r"\bDeadline\b",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]

    return clean_title(title)


def extract_competitions(soup):

    print(
        "Searching competition blocks..."
    )

    results = []

    anchors = soup.find_all("a")

    print(
        "Total links:",
        len(anchors)
    )

    processed_urls = set()

    for anchor in anchors:

        href = clean_text(
            anchor.get(
                "href",
                ""
            )
        )

        text = clean_text(
            anchor.get_text(
                " ",
                strip=True
            )
        )

        # -----------------------------------------
        # 只處理 More 或可能是比賽頁面的連結
        # -----------------------------------------

        is_more = (
            text.lower() == "more"
        )

        if not is_more and not is_competition_url(href):
            continue

        absolute_url = urljoin(
            BASE_URL,
            href
        )

        if absolute_url in processed_urls:
            continue

        container = find_container(
            anchor
        )

        if container is None:
            continue

        container_text = clean_text(
            container.get_text(
                " ",
                strip=True
            )
        )

        if not container_text:
            continue

        deadline = parse_date(
            container_text
        )

        if not deadline:
            continue

        title = extract_title_from_container(
            container
        )

        if not title:
            continue

        # -----------------------------------------
        # 過濾明顯不是比賽的內容
        # -----------------------------------------

        if is_noise(title):
            continue

        if len(title) < 4:
            continue

        if len(title) > 250:
            continue

        # -----------------------------------------
        # URL
        # -----------------------------------------

        if is_more:

            # More 本身沒有 href 時，
            # 往 container 找其他連結

            candidate_url = ""

            for link in container.find_all("a"):

                candidate = clean_text(
                    link.get(
                        "href",
                        ""
                    )
                )

                if not candidate:
                    continue

                candidate_absolute = urljoin(
                    BASE_URL,
                    candidate
                )

                if is_competition_url(
                    candidate_absolute
                ):

                    candidate_url = (
                        candidate_absolute
                    )

                    break

            if candidate_url:
                absolute_url = candidate_url

        if not is_competition_url(
            absolute_url
        ):
            continue

        processed_urls.add(
            absolute_url
        )

        item = {
            "title": title,
            "deadline": deadline,
            "resultDate": "",
            "participating": False,
            "result": "pending",
            "url": absolute_url,
        }

        duplicate = False

        for old in results:

            if (
                old["url"].lower()
                == absolute_url.lower()
            ):
                duplicate = True
                break

            if (
                old["title"].lower()
                == title.lower()
            ):
                duplicate = True
                break

        if duplicate:
            continue

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
            deadline
        )

        print(
            "  URL:",
            absolute_url
        )

        print("")

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
            "Warning: unable to read old competitions.json:",
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

    preserved = 0

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

        preserved += 1

    print(
        "Preserved existing user data:",
        preserved
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

    # -----------------------------------------
    # 只保留今天或未來的比賽
    # -----------------------------------------

    today = date.today()

    future = []

    for item in competitions:

        try:

            deadline = date.fromisoformat(
                item["deadline"]
            )

        except (
            ValueError,
            TypeError
        ):
            continue

        if deadline >= today:
            future.append(
                item
            )

    competitions = future

    # -----------------------------------------
    # 排序
    # -----------------------------------------

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

    # -----------------------------------------
    # 安全保護
    #
    # 如果網站突然改版，
    # 不允許把 competitions.json
    # 覆蓋成空檔案。
    # -----------------------------------------

    MINIMUM_COMPETITIONS = 3

    if len(competitions) < MINIMUM_COMPETITIONS:

        print("")
        print(
            "ERROR: Too few competitions parsed."
        )

        print(
            f"Found only {len(competitions)} "
            f"future competitions."
        )

        print(
            "Refusing to overwrite competitions.json."
        )

        raise SystemExit(1)

    # -----------------------------------------
    # 保留原本使用者資料
    # -----------------------------------------

    old_data = load_old_data()

    preserve_old_user_data(
        competitions,
        old_data
    )

    # -----------------------------------------
    # 寫入 JSON
    # -----------------------------------------

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
        "Total competitions:",
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
