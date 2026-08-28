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


# ---------------------------------------------------------
# 基本文字清理
# ---------------------------------------------------------

def clean_text(text):
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ---------------------------------------------------------
# 解析日期
# ---------------------------------------------------------

def parse_date(text):
    """
    只解析明確的 deadline 日期。

    支援：
    August 31, 2026
    31 August 2026
    September 15, 2026
    15 September 2026
    15 IX 2026
    15 IX 2026
    """

    if not text:
        return ""

    text = clean_text(text)

    # ---------------------------------------------
    # Month Day, Year
    # 例如：
    # August 31, 2026
    # September 15 2026
    # ---------------------------------------------

    pattern1 = re.compile(
        r"\b("
        r"January|February|March|April|May|June|July|August|"
        r"September|October|November|December"
        r")\s+"
        r"(\d{1,2})(?:st|nd|rd|th)?"
        r"(?:,\s*|\s+)"
        r"(\d{4})\b",
        re.I,
    )

    match = pattern1.search(text)

    if match:
        month_name = match.group(1).lower()
        day = int(match.group(2))
        year = int(match.group(3))

        try:
            d = date(year, MONTHS[month_name], day)
            return d.isoformat()
        except ValueError:
            return ""

    # ---------------------------------------------
    # Day Month Year
    # 例如：
    # 31 August 2026
    # 15 September 2026
    # ---------------------------------------------

    pattern2 = re.compile(
        r"\b"
        r"(\d{1,2})(?:st|nd|rd|th)?"
        r"\s+("
        r"January|February|March|April|May|June|July|August|"
        r"September|October|November|December"
        r")"
        r"(?:\s*,?\s*)(\d{4})\b",
        re.I,
    )

    match = pattern2.search(text)

    if match:
        day = int(match.group(1))
        month_name = match.group(2).lower()
        year = int(match.group(3))

        try:
            d = date(year, MONTHS[month_name], day)
            return d.isoformat()
        except ValueError:
            return ""

    # ---------------------------------------------
    # Roman numeral month
    #
    # 15 IX 2026
    # 1 XI 2026
    # ---------------------------------------------

    pattern3 = re.compile(
        r"\b(\d{1,2})\s+"
        r"(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)"
        r"\s+(\d{4})\b",
        re.I,
    )

    match = pattern3.search(text)

    if match:
        day = int(match.group(1))
        roman = match.group(2).upper()
        year = int(match.group(3))

        try:
            d = date(year, ROMAN_MONTHS[roman], day)
            return d.isoformat()
        except ValueError:
            return ""

    return ""


# ---------------------------------------------------------
# 取得 deadline
# ---------------------------------------------------------

def extract_deadline(text):
    """
    只在 Deadline / Last Deadline / Submission Deadline
    附近找日期。

    不會直接掃描整篇文章的所有日期。
    """

    if not text:
        return ""

    text = clean_text(text)

    # -----------------------------------------------------
    # 先找 Deadline 後面的文字
    # -----------------------------------------------------

    deadline_pattern = re.compile(
        r"(?:"
        r"deadline|"
        r"last\s+deadline|"
        r"submission\s+deadline|"
        r"submission\s+date|"
        r"entries\s+close|"
        r"closing\s+date"
        r")"
        r"\s*[:\-]?\s*"
        r"(.{0,100})",
        re.I,
    )

    matches = deadline_pattern.findall(text)

    for chunk in matches:
        chunk = clean_text(chunk)

        parsed = parse_date(chunk)

        if parsed:
            return parsed

        # 有時候 deadline 後面會出現：
        # 15 IX 2026
        # July 31, 2026
        # 等格式
        parsed = parse_date(chunk[:100])

        if parsed:
            return parsed

    return ""


# ---------------------------------------------------------
# 取得標題
# ---------------------------------------------------------

def get_title(element):
    """
    優先使用 h1/h2/h3/h4。
    """

    for tag in element.find_all(
        ["h1", "h2", "h3", "h4"],
        limit=5
    ):
        title = clean_text(tag.get_text(" ", strip=True))

        if title:
            return title

    # 如果沒有標題元素，嘗試連結文字
    for link in element.find_all("a"):
        title = clean_text(link.get_text(" ", strip=True))

        if title and len(title) >= 5:
            return title

    return ""


# ---------------------------------------------------------
# 取得連結
# ---------------------------------------------------------

def get_url(element):
    for link in element.find_all("a", href=True):
        href = link.get("href", "").strip()

        if href.startswith("http"):
            if "posterterritory.com" in href:
                return href

    return ""


# ---------------------------------------------------------
# 判斷是否是「真正的比賽」
# ---------------------------------------------------------

def is_valid_competition(title, text):
    title_lower = title.lower()
    text_lower = text.lower()

    # 排除網站的分類標題
    excluded_titles = {
        "poster competitions",
        "design programs and summer schools",
        "open calls and platforms with no deadline",
    }

    if title_lower in excluded_titles:
        return False

    # 明確排除教育課程
    education_words = [
        "summer school",
        "design program",
        "design programmes",
        "residency program",
    ]

    for word in education_words:
        if word in title_lower:
            return False

    # 必須具有 deadline
    if "deadline" not in text_lower:
        return False

    return True


# ---------------------------------------------------------
# 找出比賽卡片 / 文章區塊
# ---------------------------------------------------------

def get_competition_elements(soup):
    """
    PosterTerritory 的首頁結構可能改變，
    因此不依賴單一 class。

    先尋找包含 Deadline 的標題元素，
    再向上尋找合理的文章容器。
    """

    elements = []

    # -----------------------------------------------------
    # 方法 1：尋找 article
    # -----------------------------------------------------

    for article in soup.find_all("article"):
        text = clean_text(article.get_text(" ", strip=True))

        if "deadline" in text.lower():
            elements.append(article)

    if elements:
        return elements

    # -----------------------------------------------------
    # 方法 2：尋找 h2/h3/h4，
    # 往父層尋找包含 deadline 的容器
    # -----------------------------------------------------

    seen = set()

    for heading in soup.find_all(["h2", "h3", "h4"]):

        title = clean_text(
            heading.get_text(" ", strip=True)
        )

        if not title:
            continue

        parent = heading.parent

        for _ in range(5):

            if not parent:
                break

            text = clean_text(
                parent.get_text(" ", strip=True)
            )

            if "deadline" in text.lower():

                key = id(parent)

                if key not in seen:
                    seen.add(key)
                    elements.append(parent)

                break

            parent = parent.parent

    return elements


# ---------------------------------------------------------
# 主程式
# ---------------------------------------------------------

def main():

    print("Downloading PosterTerritory...")

    response = requests.get(
        URL,
        timeout=30,
        headers=HEADERS,
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    elements = get_competition_elements(soup)

    print("Candidate elements:", len(elements))

    items = []

    seen_titles = set()

    for element in elements:

        title = get_title(element)

        if not title:
            continue

        text = clean_text(
            element.get_text(" ", strip=True)
        )

        if not is_valid_competition(title, text):
            continue

        deadline = extract_deadline(text)

        if not deadline:
            print("Skipping - no deadline:", title)
            continue

        # -------------------------------------------------
        # 只保留今年及未來的 deadline
        #
        # 2026-08-31 之後
        # 以及未來年份
        # -------------------------------------------------

        try:
            deadline_date = date.fromisoformat(deadline)
        except ValueError:
            continue

        if deadline_date < TODAY:
            print(
                "Skipping expired:",
                title,
                deadline
            )
            continue

        # -------------------------------------------------
        # 去除重複
        # -------------------------------------------------

        title_key = re.sub(
            r"\s+",
            " ",
            title.lower()
        ).strip()

        if title_key in seen_titles:
            continue

        seen_titles.add(title_key)

        url = get_url(element)

        if not url:
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

    # -----------------------------------------------------
    # 如果完全抓不到資料
    # 絕對不能覆蓋現有 competitions.json
    # -----------------------------------------------------

    if not items:
        raise SystemExit(
            "No valid future competitions parsed; "
            "refusing to overwrite competitions.json"
        )

    # -----------------------------------------------------
    # 讀取舊資料
    # -----------------------------------------------------

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

    old_map = {}

    for item in old:

        title = item.get("title", "").strip()

        if title:
            old_map[title.lower()] = item

    # -----------------------------------------------------
    # 保留使用者原本的參賽狀態
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
    # 排序
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

    print(
        "Updated",
        len(items),
        "future competitions"
    )

    # -----------------------------------------------------
    # 顯示前幾筆，方便 GitHub Actions log 檢查
    # -----------------------------------------------------

    print("")
    print("First competitions:")

    for item in items[:10]:

        print(
            "-",
            item["title"],
            "|",
            item["deadline"]
        )


if __name__ == "__main__":
    main()
