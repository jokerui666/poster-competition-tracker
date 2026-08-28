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


def clean_text(text):
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def parse_date(text):
    """
    支援：

    August 31, 2026
    31 August 2026
    August 31
    8 September 2026
    Deadline: September 15, 2026
    """

    text = clean_text(text)

    # --------------------------------------------------
    # Month Day, Year
    # --------------------------------------------------

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


    # --------------------------------------------------
    # Day Month Year
    # --------------------------------------------------

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


    # --------------------------------------------------
    # Month Day without year
    # --------------------------------------------------

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
            return date(
                TODAY.year,
                month,
                day
            ).isoformat()
        except ValueError:
            return ""


    return ""


def find_deadline(text):
    """
    從單一比賽區塊中找 Deadline。
    """

    text = clean_text(text)

    patterns = [
        r"New submission deadline\s*:?\s*(.*)",
        r"Last deadline\s*:?\s*(.*)",
        r"Deadline\s*:?\s*(.*)",
    ]

    for pattern in patterns:

        m = re.search(
            pattern,
            text,
            re.I
        )

        if m:

            deadline = parse_date(
                m.group(1)
            )

            if deadline:
                return deadline

    return ""


def looks_like_deadline(text):
    lower = text.lower()

    return (
        "deadline" in lower
        or "last deadline" in lower
        or "new submission deadline" in lower
    )


def clean_title(text):
    """
    清理比賽標題。
    """

    text = clean_text(text)

    # 移除 Deadline 後面的內容
    text = re.split(
        r"\b(?:deadline|last deadline|new submission deadline)\b",
        text,
        flags=re.I
    )[0]

    # 移除 More
    text = re.sub(
        r"\bMore\b.*$",
        "",
        text,
        flags=re.I
    )

    text = clean_text(text)

    # 過濾網站分類標題
    bad = [
        "Poster Competitions",
        "Design programs and Summer Schools",
        "Open calls and platforms with no deadline",
    ]

    for item in bad:

        if text.lower() == item.lower():
            return ""

    return text


def get_best_container(link):
    """
    找到「單一比賽」的 HTML 區塊。

    不使用 h1/h2/h3/h4。
    以 More 連結為中心向上尋找，
    找到同時包含 Deadline 的最小容器。
    """

    current = link

    candidates = []

    for _ in range(8):

        current = current.parent

        if current is None:
            break

        text = clean_text(
            current.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        # 太大的容器直接不要
        if len(text) > 1200:
            continue

        if looks_like_deadline(text):

            candidates.append(
                (
                    len(text),
                    current
                )
            )

    if not candidates:
        return None

    # 最小的符合條件容器
    candidates.sort(
        key=lambda x: x[0]
    )

    return candidates[0][1]


def extract_title_from_container(container):
    """
    從單一比賽區塊中取得標題。
    """

    # --------------------------------------------------
    # 先找文字節點
    # --------------------------------------------------

    lines = []

    for element in container.find_all(
        ["h1", "h2", "h3", "h4", "p", "div", "span"],
    ):

        text = clean_text(
            element.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        if text in lines:
            continue

        lines.append(text)

    # --------------------------------------------------
    # 找 Deadline 前面的文字
    # --------------------------------------------------

    deadline_index = None

    for i, line in enumerate(lines):

        if looks_like_deadline(line):

            deadline_index = i
            break

    if deadline_index is not None:

        before = lines[
            :deadline_index
        ]

        # 從最後面開始找最合理的標題
        for line in reversed(before):

            title = clean_title(
                line
            )

            if (
                title
                and len(title) >= 5
                and "more" not in title.lower()
            ):
                return title

    # --------------------------------------------------
    # 備用：直接從整個區塊文字判斷
    # --------------------------------------------------

    full_text = clean_text(
        container.get_text(
            " ",
            strip=True
        )
    )

    # Deadline 前面就是標題
    m = re.search(
        r"^(.*?)"
        r"(?=(?:New submission deadline|Last deadline|Deadline))",
        full_text,
        re.I
    )

    if m:

        title = clean_title(
            m.group(1)
        )

        if title:
            return title

    return ""


def scrape_competitions(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    print(
        "Page downloaded."
    )

    # --------------------------------------------------
    # 找所有 More 連結
    # --------------------------------------------------

    more_links = []

    for link in soup.find_all(
        "a",
        href=True
    ):

        text = clean_text(
            link.get_text(
                " ",
                strip=True
            )
        )

        if text.lower() == "more":

            more_links.append(
                link
            )

    print(
        "More links found:",
        len(more_links)
    )

    items = []

    # --------------------------------------------------
    # 一個 More = 一個比賽
    # --------------------------------------------------

    for link in more_links:

        container = get_best_container(
            link
        )

        if container is None:
            continue

        container_text = clean_text(
            container.get_text(
                " ",
                strip=True
            )
        )

        deadline = find_deadline(
            container_text
        )

        if not deadline:
            continue

        # --------------------------------------------------
        # 只保留未來比賽
        # --------------------------------------------------

        try:

            deadline_date = date.fromisoformat(
                deadline
            )

        except ValueError:

            continue

        if deadline_date < TODAY:
            continue

        # --------------------------------------------------
        # 標題
        # --------------------------------------------------

        title = extract_title_from_container(
            container
        )

        if not title:
            continue

        # --------------------------------------------------
        # URL
        # --------------------------------------------------

        url = link.get(
            "href",
            ""
        ).strip()

        if not url:
            continue

        # --------------------------------------------------
        # 排除分類區塊
        # --------------------------------------------------

        bad_words = [
            "design programs",
            "summer schools",
            "open calls and platforms",
            "stand with ukraine",
        ]

        if any(
            word in title.lower()
            for word in bad_words
        ):
            continue

        # --------------------------------------------------
        # 去除重複
        # --------------------------------------------------

        duplicate = False

        for item in items:

            if (
                item["url"] == url
                or item["title"].lower()
                == title.lower()
            ):

                duplicate = True
                break

        if duplicate:
            continue

        item = {
            "title": title,
            "deadline": deadline,
            "resultDate": "",
            "participating": False,
            "result": "pending",
            "url": url,
        }

        items.append(
            item
        )

        print(
            "FOUND:",
            deadline,
            "|",
            title,
            "|",
            url
        )

    # --------------------------------------------------
    # 排序
    # --------------------------------------------------

    items.sort(
        key=lambda x: (
            x["deadline"],
            x["title"].lower()
        )
    )

    return items


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

            return json.load(f)

    except Exception:

        return []


def preserve_user_data(
    new_items,
    old_items
):

    old_map = {}

    for item in old_items:

        title = clean_text(
            item.get(
                "title",
                ""
            )
        )

        url = clean_text(
            item.get(
                "url",
                ""
            )
        )

        if title:
            old_map[
                title.lower()
            ] = item

        if url:
            old_map[
                url
            ] = item

    for item in new_items:

        old = (
            old_map.get(
                item["title"].lower()
            )
            or old_map.get(
                item["url"]
            )
        )

        if old:

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


def save_data(items):

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
        timeout=30,
        headers=HEADERS
    )

    response.raise_for_status()

    print(
        "HTTP:",
        response.status_code
    )

    print(
        "Bytes:",
        len(response.content)
    )

    # --------------------------------------------------
    # 抓取
    # --------------------------------------------------

    items = scrape_competitions(
        response.text
    )

    print("")
    print(
        "Future competitions:",
        len(items)
    )

    # --------------------------------------------------
    # 安全機制
    # --------------------------------------------------

    if len(items) == 0:

        raise SystemExit(
            "No future competitions parsed; "
            "refusing to overwrite competitions.json"
        )

    # --------------------------------------------------
    # 舊資料
    # --------------------------------------------------

    old_items = load_old_data()

    preserve_user_data(
        items,
        old_items
    )

    # --------------------------------------------------
    # 寫入
    # --------------------------------------------------

    save_data(
        items
    )

    print("")
    print(
        "Updated",
        len(items),
        "competitions."
    )

    print("")
    print(
        "========== FINAL LIST =========="
    )

    for item in items:

        print(
            item["deadline"],
            "|",
            item["title"]
        )

        print(
            "URL:",
            item["url"]
        )

    print(
        "================================"
    )


if __name__ == "__main__":
    main()
