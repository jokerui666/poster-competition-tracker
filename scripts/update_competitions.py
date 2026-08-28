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


BAD_HEADINGS = {
    "poster competitions",
    "design programs and summer schools",
    "open calls and platforms with no deadline",
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
    September 15, 2026
    8 September 2026
    November 1, 2026
    """

    text = clean_text(text)

    # -----------------------------------------
    # Month Day, Year
    # -----------------------------------------

    match = re.search(
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
        re.IGNORECASE,
    )

    if match:

        month = MONTHS[
            match.group(1).lower()
        ]

        day = int(
            match.group(2)
        )

        year = int(
            match.group(3)
        )

        try:
            return date(
                year,
                month,
                day
            ).isoformat()

        except ValueError:
            return ""


    # -----------------------------------------
    # Day Month Year
    # -----------------------------------------

    match = re.search(
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
        re.IGNORECASE,
    )

    if match:

        day = int(
            match.group(1)
        )

        month = MONTHS[
            match.group(2).lower()
        ]

        year = int(
            match.group(3)
        )

        try:
            return date(
                year,
                month,
                day
            ).isoformat()

        except ValueError:
            return ""


    return ""


def extract_deadline(text):
    """
    從一個文字區塊尋找截止日期。
    """

    text = clean_text(text)

    if not re.search(
        r"deadline",
        text,
        re.IGNORECASE
    ):
        return ""

    return parse_date(text)


def is_more_link(tag):
    """
    判斷是否為 More 連結。
    """

    if tag.name != "a":
        return False

    text = clean_text(
        tag.get_text(
            " ",
            strip=True
        )
    )

    return text.lower() == "more"


def get_content_blocks(soup):
    """
    取得頁面主要文字區塊。

    只使用：

    h1/h2/h3/h4/p

    避免 div 巢狀結構造成同一段文字
    被重複抓取。
    """

    blocks = []

    for tag in soup.find_all(
        ["h1", "h2", "h3", "h4", "p"]
    ):

        text = clean_text(
            tag.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        blocks.append(
            {
                "tag": tag,
                "text": text,
            }
        )

    return blocks


def find_block_index(blocks, tag):
    """
    找出某個 More 連結附近的文字位置。
    """

    # 找 More 所在的父元素
    parent = tag.parent

    if parent is None:
        return None

    # 找 More 前面的文字元素
    previous = []

    for candidate in parent.find_all_previous(
        ["h1", "h2", "h3", "h4", "p"],
        limit=20
    ):

        text = clean_text(
            candidate.get_text(
                " ",
                strip=True
            )
        )

        if text:
            previous.append(
                candidate
            )

    if not previous:
        return None

    # find_all_previous 是反方向
    previous.reverse()

    # 找最後一個出現在 More 前的 block
    last = previous[-1]

    for i, block in enumerate(blocks):

        if block["tag"] is last:
            return i

    return None


def extract_competitions(soup):
    """
    核心解析器。

    頁面結構：

        標題
        補充文字
        Deadline
        More

        標題
        補充文字
        Deadline
        More

    每遇到一個 More，
    就把它之前尚未處理的文字視為一個競賽區塊。
    """

    blocks = get_content_blocks(
        soup
    )

    more_links = [
        a
        for a in soup.find_all("a")
        if is_more_link(a)
    ]

    print(
        "Content blocks:",
        len(blocks)
    )

    print(
        "More links:",
        len(more_links)
    )

    results = []

    block_position = 0


    for more_number, more in enumerate(
        more_links,
        start=1
    ):

        # -----------------------------------------
        # 找 More 對應的最後一個文字 block
        # -----------------------------------------

        end_index = find_block_index(
            blocks,
            more
        )

        if end_index is None:
            continue

        if end_index < block_position:
            continue

        # -----------------------------------------
        # 取得這一個競賽的文字區塊
        # -----------------------------------------

        chunk = blocks[
            block_position:
            end_index + 1
        ]

        block_position = end_index + 1

        texts = [
            item["text"]
            for item in chunk
        ]

        if not texts:
            continue

        # -----------------------------------------
        # 找 Deadline
        # -----------------------------------------

        deadline = ""

        deadline_index = None

        for i, text in enumerate(texts):

            found = extract_deadline(
                text
            )

            if found:

                deadline = found
                deadline_index = i

                break

        if not deadline:
            continue

        # -----------------------------------------
        # 找標題
        #
        # Deadline 前面的第一個有效文字
        # 通常就是比賽名稱。
        # -----------------------------------------

        title = ""

        for text in texts[
            :deadline_index
        ]:

            candidate = clean_text(
                text
            )

            if not candidate:
                continue

            if candidate.lower() in BAD_HEADINGS:
                continue

            if len(candidate) < 5:
                continue

            title = candidate

        # -----------------------------------------
        # 如果沒有找到標題
        # 嘗試 Deadline 後面的文字
        # -----------------------------------------

        if not title:

            for text in texts:

                candidate = clean_text(
                    text
                )

                if not candidate:
                    continue

                if re.search(
                    r"deadline",
                    candidate,
                    re.IGNORECASE
                ):
                    continue

                if candidate.lower() in BAD_HEADINGS:
                    continue

                if len(candidate) < 5:
                    continue

                title = candidate
                break

        if not title:
            continue

        # -----------------------------------------
        # 取得 More 的網址
        # -----------------------------------------

        url = more.get(
            "href",
            ""
        ).strip()

        if not url:
            continue

        # -----------------------------------------
        # 只保留今天以後的競賽
        # -----------------------------------------

        try:

            deadline_date = date.fromisoformat(
                deadline
            )

        except ValueError:

            continue

        if deadline_date < TODAY:
            continue

        # -----------------------------------------
        # 去除明顯不是競賽的項目
        # -----------------------------------------

        lower_title = title.lower()

        if lower_title in BAD_HEADINGS:
            continue

        if (
            "design programs" in lower_title
            or "summer schools" in lower_title
        ):
            continue

        if (
            "open calls and platforms" in lower_title
        ):
            continue

        # -----------------------------------------
        # 避免重複
        # -----------------------------------------

        duplicate = False

        for item in results:

            if item["url"] == url:
                duplicate = True
                break

            if (
                item["title"].lower()
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

        results.append(
            item
        )

        print(
            f"FOUND {len(results)}:",
            deadline,
            "|",
            title
        )

        print(
            "URL:",
            url
        )


    return results


def load_old_data():
    """
    讀取舊資料。
    """

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


def preserve_user_data(
    new_items,
    old_items
):
    """
    保留使用者原本的：

    participating
    result
    resultDate
    """

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
            old_by_url[
                url
            ] = item

        if title:
            old_by_title[
                title.lower()
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

    # -----------------------------------------
    # 解析
    # -----------------------------------------

    items = extract_competitions(
        soup
    )

    # -----------------------------------------
    # 排序
    # -----------------------------------------

    items.sort(
        key=lambda item: (
            item["deadline"],
            item["title"].lower()
        )
    )

    print("")
    print(
        "Future competitions:",
        len(items)
    )

    # -----------------------------------------
    # 非常重要的安全機制
    #
    # 如果少於 3 筆：
    # 不允許覆蓋 competitions.json
    # -----------------------------------------

    if len(items) < 3:

        print(
            "ERROR: Too few competitions parsed."
        )

        print(
            "Refusing to overwrite competitions.json."
        )

        raise SystemExit(1)

    # -----------------------------------------
    # 讀取舊資料
    # -----------------------------------------

    old_items = load_old_data()

    preserve_user_data(
        items,
        old_items
    )

    # -----------------------------------------
    # 儲存
    # -----------------------------------------

    save_data(
        items
    )

    print("")
    print(
        "Updated competitions.json"
    )

    print(
        "Total competitions:",
        len(items)
    )

    print("")
    print(
        "========== FINAL LIST =========="
    )

    for index, item in enumerate(
        items,
        start=1
    ):

        print(
            f"{index}.",
            item["deadline"],
            "|",
            item["title"]
        )

        print(
            "   ",
            item["url"]
        )

    print(
        "================================"
    )


if __name__ == "__main__":
    main()
