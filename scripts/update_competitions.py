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

    # -----------------------------------------
    # August 31, 2026
    # September 15, 2026
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

        day = int(match.group(2))
        year = int(match.group(3))

        try:
            return date(
                year,
                month,
                day
            ).isoformat()

        except ValueError:
            return ""


    # -----------------------------------------
    # 8 September 2026
    # 15 September 2026
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

        day = int(match.group(1))

        month = MONTHS[
            match.group(2).lower()
        ]

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


def get_title_from_block(text):

    text = clean_text(text)

    if not text:
        return ""

    # -----------------------------------------
    # 去掉 Deadline 後面的內容
    # -----------------------------------------

    text = re.split(
        r"\bdeadline\b",
        text,
        flags=re.IGNORECASE
    )[0]

    text = clean_text(text)

    return text


def extract_competitions(soup):

    # =====================================================
    # 重要：
    #
    # 不再用 parent / previous sibling 判斷結構。
    #
    # 直接按照 HTML 出現順序掃描文字。
    # =====================================================

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

    pending_title = ""
    pending_deadline = ""

    results = []

    for element in elements:

        text = clean_text(
            element.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue


        # =================================================
        # 1. More
        # =================================================

        if element.name == "a":

            if text.lower() != "more":
                continue

            url = element.get(
                "href",
                ""
            ).strip()

            # 沒有完整資料就跳過
            if not pending_title:
                continue

            if not pending_deadline:
                continue

            if not url:
                continue


            item = {
                "title": pending_title,
                "deadline": pending_deadline,
                "resultDate": "",
                "participating": False,
                "result": "pending",
                "url": url,
            }


            # ---------------------------------------------
            # 避免重複
            # ---------------------------------------------

            duplicate = False

            for old in results:

                if old["url"] == url:
                    duplicate = True
                    break

                if (
                    old["title"].lower()
                    == pending_title.lower()
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
                    pending_title
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


            # ---------------------------------------------
            # 清空目前競賽
            # ---------------------------------------------

            pending_title = ""
            pending_deadline = ""

            continue


        # =================================================
        # 2. Deadline
        # =================================================

        if re.search(
            r"\bdeadline\b",
            text,
            re.IGNORECASE
        ):

            deadline = parse_date(
                text
            )

            if deadline:

                pending_deadline = deadline

                print(
                    "DEADLINE FOUND:",
                    deadline
                )

                # -----------------------------------------
                # 如果這個文字本身包含 Deadline 前面的
                # 比賽名稱，直接取出
                # -----------------------------------------

                title = get_title_from_block(
                    text
                )

                if title:

                    pending_title = title

                continue


        # =================================================
        # 3. 普通標題 / 說明文字
        #
        # 只有在還沒有 deadline 的時候更新 title。
        # =================================================

        if not pending_deadline:

            lower = text.lower()

            # ---------------------------------------------
            # 排除網站大標題
            # ---------------------------------------------

            if lower in {
                "poster competitions",
                "design programs and summer schools",
                "open calls and platforms with no deadline",
                "posterterritory",
                "design for change",
            }:
                continue


            # ---------------------------------------------
            # 排除導航
            # ---------------------------------------------

            if lower in {
                "more",
                "read more",
                "discover today",
                "submission form",
            }:
                continue


            # ---------------------------------------------
            # 太短的不當標題
            # ---------------------------------------------

            if len(text) < 5:
                continue


            pending_title = text


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

        return []

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

    print("")


    # =====================================================
    # 解析
    # =====================================================

    competitions = extract_competitions(
        soup
    )


    print("")
    print(
        "Parsed competitions:",
        len(competitions)
    )


    # =====================================================
    # 只保留今天之後的項目
    #
    # 今天由 GitHub Actions 執行環境決定。
    # =====================================================

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


    # =====================================================
    # 排序
    # =====================================================

    competitions.sort(
        key=lambda item: (
            item["deadline"],
            item["title"].lower()
        )
    )


    print("")
    print(
        "Future competitions:",
        len(competitions)
    )


    # =====================================================
    # 安全保護
    #
    # 正常應該至少抓到數個未來競賽。
    #
    # 少於 3 筆就不覆蓋 JSON。
    # =====================================================

    if len(competitions) < 3:

        print(
            "ERROR: Too few competitions parsed."
        )

        print(
            "Refusing to overwrite competitions.json."
        )

        raise SystemExit(1)


    # =====================================================
    # 保留原本使用者資料
    # =====================================================

    old_data = load_old_data()

    preserve_old_user_data(
        competitions,
        old_data
    )


    # =====================================================
    # 寫入 competitions.json
    # =====================================================

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


    # =====================================================
    # 最終清單
    # =====================================================

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
