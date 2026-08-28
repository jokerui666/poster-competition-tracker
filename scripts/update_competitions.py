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


    # 8 September 2026
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


    # August 31
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


def extract_deadline(text):
    """
    從文字中尋找 Deadline。
    """

    text = clean_text(text)

    patterns = [
        r"New submission deadline\s*:?\s*(.+)",
        r"Last Deadline\s*:?\s*(.+)",
        r"Last deadline\s*:?\s*(.+)",
        r"Deadline\s*:?\s*(.+)",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.I
        )

        if match:

            result = parse_date(
                match.group(1)
            )

            if result:
                return result

    return ""


def clean_title(text):

    text = clean_text(text)

    # 移除多餘分類資訊
    text = re.sub(
        r"^Categories?:.*$",
        "",
        text,
        flags=re.I
    )

    text = clean_text(text)

    return text


def get_page_blocks(soup):

    """
    將頁面中的文字元素按照實際出現順序整理。

    只處理主要內容區，不使用整個 body。
    """

    elements = []

    for element in soup.find_all(
        ["h1", "h2", "h3", "h4", "p", "div", "a"]
    ):

        text = clean_text(
            element.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        elements.append(
            {
                "element": element,
                "text": text,
            }
        )

    return elements


def find_more_links(soup):

    links = []

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

            links.append(link)

    return links


def get_previous_texts(more_link, limit=8):

    """
    從 More 往前找文字。
    """

    texts = []

    current = more_link

    for _ in range(limit):

        previous = current.find_previous(
            ["h1", "h2", "h3", "h4", "p", "div"]
        )

        if previous is None:
            break

        text = clean_text(
            previous.get_text(
                " ",
                strip=True
            )
        )

        if text and text not in texts:

            texts.append(text)

        current = previous

    return texts


def extract_from_page(soup):

    more_links = find_more_links(
        soup
    )

    print(
        "More links found:",
        len(more_links)
    )

    results = []

    for more_link in more_links:

        url = more_link.get(
            "href",
            ""
        ).strip()

        if not url:
            continue

        # --------------------------------------------
        # 往 More 前面找最近的文字
        # --------------------------------------------

        previous_texts = get_previous_texts(
            more_link,
            limit=10
        )

        deadline = ""

        title = ""

        # --------------------------------------------
        # 找 Deadline
        # --------------------------------------------

        for text in previous_texts:

            found_date = extract_deadline(
                text
            )

            if found_date:

                deadline = found_date
                break

        if not deadline:
            continue

        # --------------------------------------------
        # 找標題
        # --------------------------------------------

        deadline_index = None

        for i, text in enumerate(
            previous_texts
        ):

            if extract_deadline(text):

                deadline_index = i
                break

        if deadline_index is not None:

            for text in previous_texts[
                deadline_index + 1:
            ]:

                candidate = clean_title(
                    text
                )

                if not candidate:
                    continue

                if (
                    len(candidate) < 5
                ):
                    continue

                if (
                    "deadline" in candidate.lower()
                ):
                    continue

                title = candidate
                break

        # --------------------------------------------
        # 如果上面的順序沒找到
        # 再從所有 previous texts 找
        # --------------------------------------------

        if not title:

            for text in previous_texts:

                candidate = clean_title(
                    text
                )

                if not candidate:
                    continue

                if len(candidate) < 5:
                    continue

                if "deadline" in candidate.lower():
                    continue

                if candidate.lower() == "more":
                    continue

                title = candidate
                break

        if not title:
            continue

        # --------------------------------------------
        # 排除分類頁
        # --------------------------------------------

        bad_titles = [
            "design programs",
            "summer schools",
            "open calls and platforms",
            "stand with ukraine",
            "poster call",
        ]

        if any(
            bad in title.lower()
            for bad in bad_titles
        ):
            continue

        # --------------------------------------------
        # 只保留未來日期
        # --------------------------------------------

        try:

            deadline_date = date.fromisoformat(
                deadline
            )

        except ValueError:

            continue

        if deadline_date < TODAY:
            continue

        # --------------------------------------------
        # 去重
        # --------------------------------------------

        duplicate = False

        for item in results:

            if item["url"] == url:
                duplicate = True

            if (
                item["title"].lower()
                == title.lower()
            ):
                duplicate = True

        if duplicate:
            continue

        results.append(
            {
                "title": title,
                "deadline": deadline,
                "resultDate": "",
                "participating": False,
                "result": "pending",
                "url": url,
            }
        )

        print(
            "FOUND:",
            deadline,
            "|",
            title,
            "|",
            url
        )

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

            return json.load(f)

    except Exception:

        return []


def preserve_user_data(
    new_items,
    old_items
):

    old_by_title = {}
    old_by_url = {}

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
            old_by_title[
                title.lower()
            ] = item

        if url:
            old_by_url[
                url
            ] = item

    for item in new_items:

        old = (
            old_by_url.get(
                item["url"]
            )
            or old_by_title.get(
                item["title"].lower()
            )
        )

        if not old:
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
        headers=HEADERS,
        timeout=30
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

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    print(
        "Page downloaded."
    )

    items = extract_from_page(
        soup
    )

    # --------------------------------------------
    # 排序
    # --------------------------------------------

    items.sort(
        key=lambda x: (
            x["deadline"],
            x["title"].lower()
        )
    )

    print("")
    print(
        "Future competitions:",
        len(items)
    )

    # --------------------------------------------
    # 安全保護
    # --------------------------------------------

    if len(items) == 0:

        raise SystemExit(
            "No future competitions parsed; "
            "refusing to overwrite competitions.json"
        )

    # --------------------------------------------
    # 保留使用者資料
    # --------------------------------------------

    old_items = load_old_data()

    preserve_user_data(
        items,
        old_items
    )

    # --------------------------------------------
    # 儲存
    # --------------------------------------------

    save_data(
        items
    )

    print("")
    print(
        "Updated competitions.json"
    )

    print(
        "Total:",
        len(items)
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
