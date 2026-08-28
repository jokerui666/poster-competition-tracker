import json
import os
import re
import time
from datetime import date
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


# ============================================================
# 設定
# ============================================================

BASE_URL = "https://www.posterterritory.com/"
START_PAGE = "https://www.posterterritory.com/"
CUTOFF_DATE = date(2026, 6, 1)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_PAGES = 40


# ============================================================
# Session
# ============================================================

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# 月份
# ============================================================

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


# ============================================================
# 基本工具
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_url(url):
    if not url:
        return ""

    return urljoin(
        BASE_URL,
        url
    ).split("#")[0].rstrip("/")


def same_domain(url):
    try:
        return urlparse(url).netloc in {
            "",
            "www.posterterritory.com",
            "posterterritory.com",
        }
    except Exception:
        return False


# ============================================================
# 日期解析
# ============================================================

def parse_date(text):

    text = clean_text(text)

    # --------------------------------------------------------
    # YYYY-MM-DD
    # --------------------------------------------------------

    match = re.search(
        r"\b(2026|2027)[-/](\d{1,2})[-/](\d{1,2})\b",
        text,
        re.IGNORECASE
    )

    if match:
        try:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))

            return date(
                year,
                month,
                day
            )

        except ValueError:
            pass

    # --------------------------------------------------------
    # August 31, 2026
    # --------------------------------------------------------

    pattern_1 = re.compile(
        r"\b"
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)"
        r"\s+"
        r"(\d{1,2})"
        r"(?:st|nd|rd|th)?"
        r"(?:,\s*|\s+)"
        r"(2026|2027)"
        r"\b",
        re.IGNORECASE
    )

    match = pattern_1.search(text)

    if match:
        try:

            month = MONTHS[
                match.group(1).lower()
            ]

            day = int(
                match.group(2)
            )

            year = int(
                match.group(3)
            )

            return date(
                year,
                month,
                day
            )

        except ValueError:
            pass

    # --------------------------------------------------------
    # 31 August 2026
    # --------------------------------------------------------

    pattern_2 = re.compile(
        r"\b"
        r"(\d{1,2})"
        r"(?:st|nd|rd|th)?"
        r"\s+"
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)"
        r"(?:,\s*|\s+)"
        r"(2026|2027)"
        r"\b",
        re.IGNORECASE
    )

    match = pattern_2.search(text)

    if match:
        try:

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
            )

        except ValueError:
            pass

    # --------------------------------------------------------
    # September 15, 2026
    # --------------------------------------------------------

    return None


# ============================================================
# 羅馬數字日期
# 例如：15 IX 2026
# ============================================================

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


def parse_roman_date(text):

    match = re.search(
        r"\b(\d{1,2})\s+"
        r"(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)"
        r"\s+(2026|2027)\b",
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    try:

        day = int(
            match.group(1)
        )

        month = ROMAN_MONTHS[
            match.group(2).upper()
        ]

        year = int(
            match.group(3)
        )

        return date(
            year,
            month,
            day
        )

    except ValueError:
        return None


def find_deadline(text):

    text = clean_text(text)

    # --------------------------------------------------------
    # 優先找 Deadline 附近的日期
    # --------------------------------------------------------

    deadline_patterns = [
        r"deadline.{0,100}",
        r"last deadline.{0,100}",
        r"submission deadline.{0,100}",
        r"closing date.{0,100}",
        r"entries close.{0,100}",
        r"submit.{0,100}",
    ]

    for pattern in deadline_patterns:

        matches = re.findall(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        for chunk in matches:

            result = parse_date(
                chunk
            )

            if result:
                return result

            result = parse_roman_date(
                chunk
            )

            if result:
                return result

    # --------------------------------------------------------
    # 整段文字搜尋
    # --------------------------------------------------------

    result = parse_date(
        text
    )

    if result:
        return result

    result = parse_roman_date(
        text
    )

    return result


# ============================================================
# 判斷是不是海報相關競賽
# ============================================================

POSTER_KEYWORDS = [
    "poster",
    "posters",
    "biennale",
    "biennial",
    "poster competition",
    "poster contest",
    "poster call",
    "open call",
    "poster festival",
    "poster award",
    "poster exhibition",
    "graphic design competition",
    "typography competition",
    "visual competition",
    "call for posters",
    "call for entries",
]


EXCLUDE_KEYWORDS = [
    "design programs",
    "summer schools",
    "residency",
    "conference",
    "frontline features",
    "poster recipe",
    "poster recipes",
    "read more",
    "dear friends",
    "donation",
]


def looks_like_poster_competition(
    title,
    text
):

    combined = (
        clean_text(title)
        + " "
        + clean_text(text)
    ).lower()

    # 明確排除
    for keyword in EXCLUDE_KEYWORDS:

        if keyword in combined:
            return False

    # 明確是海報
    for keyword in POSTER_KEYWORDS:

        if keyword in combined:
            return True

    return False


# ============================================================
# 標題清理
# ============================================================

def clean_title(title):

    title = clean_text(
        title
    )

    if not title:
        return ""

    # 移除多餘的 More
    title = re.sub(
        r"\s+\bMore\b\s*$",
        "",
        title,
        flags=re.IGNORECASE
    )

    # 移除 Last Deadline 後面不應該存在的內容
    title = re.split(
        r"\bLast\s+Deadline\b",
        title,
        maxsplit=1,
        flags=re.IGNORECASE
    )[0]

    # 移除 Categories 後面內容
    title = re.split(
        r"\bCategories\s*:",
        title,
        maxsplit=1,
        flags=re.IGNORECASE
    )[0]

    # 如果標題後面接 Deadline
    title = re.split(
        r"\bDeadline\b",
        title,
        maxsplit=1,
        flags=re.IGNORECASE
    )[0]

    return clean_text(
        title.strip(
            " \t\r\n-–—:;,.|"
        )
    )


# ============================================================
# 下載頁面
# ============================================================

def download(url):

    print(
        f"Downloading: {url}"
    )

    response = session.get(
        url,
        timeout=30
    )

    print(
        "HTTP:",
        response.status_code,
        "Bytes:",
        len(response.content)
    )

    response.raise_for_status()

    return response.text


# ============================================================
# 取得文章列表
# ============================================================

def extract_posts(
    soup,
    page_url
):

    posts = []

    # --------------------------------------------------------
    # WordPress 通常使用 article
    # --------------------------------------------------------

    articles = soup.find_all(
        "article"
    )

    if articles:

        for article in articles:

            title_element = (
                article.find(
                    [
                        "h1",
                        "h2",
                        "h3",
                        "h4"
                    ]
                )
            )

            if not title_element:
                continue

            title = clean_text(
                title_element.get_text(
                    " ",
                    strip=True
                )
            )

            if not title:
                continue

            link_element = (
                title_element.find(
                    "a"
                )
            )

            if not link_element:

                link_element = (
                    article.find(
                        "a",
                        href=True
                    )
                )

            if not link_element:
                continue

            url = normalize_url(
                link_element.get(
                    "href",
                    ""
                )
            )

            if not url:
                continue

            text = clean_text(
                article.get_text(
                    " ",
                    strip=True
                )
            )

            posts.append(
                {
                    "title": title,
                    "url": url,
                    "text": text,
                }
            )

        return posts

    # --------------------------------------------------------
    # fallback
    # --------------------------------------------------------

    headings = soup.find_all(
        [
            "h1",
            "h2",
            "h3",
            "h4"
        ]
    )

    for heading in headings:

        title = clean_text(
            heading.get_text(
                " ",
                strip=True
            )
        )

        if not title:
            continue

        link = heading.find(
            "a",
            href=True
        )

        if not link:
            continue

        url = normalize_url(
            link.get(
                "href",
                ""
            )
        )

        if not url:
            continue

        parent = heading.parent

        text = clean_text(
            parent.get_text(
                " ",
                strip=True
            )
        )

        posts.append(
            {
                "title": title,
                "url": url,
                "text": text,
            }
        )

    return posts


# ============================================================
# 逐頁搜尋
# ============================================================

def collect_listing_posts():

    all_posts = {}

    for page_number in range(
        1,
        MAX_PAGES + 1
    ):

        if page_number == 1:

            url = START_PAGE

        else:

            url = (
                BASE_URL
                + f"page/{page_number}/"
            )

        print("")
        print(
            "======================================"
        )

        print(
            f"Scanning listing page {page_number}"
        )

        print(
            url
        )

        try:

            html = download(
                url
            )

        except Exception as error:

            print(
                "Unable to download page:",
                error
            )

            continue

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        posts = extract_posts(
            soup,
            url
        )

        print(
            "Posts found:",
            len(posts)
        )

        if not posts:
            print(
                "No posts found. Stopping pagination."
            )
            break

        for post in posts:

            post_url = post[
                "url"
            ]

            if (
                not post_url
                or not same_domain(post_url)
            ):
                continue

            all_posts[
                post_url
            ] = post

        # 避免請求過快
        time.sleep(0.4)

    print("")
    print(
        "Total unique posts:",
        len(all_posts)
    )

    return list(
        all_posts.values()
    )


# ============================================================
# 建立 competition
# ============================================================

def build_competitions(
    posts
):

    results = []

    seen_urls = set()
    seen_titles = set()

    for index, post in enumerate(
        posts,
        start=1
    ):

        title = clean_title(
            post["title"]
        )

        text = post["text"]
        url = post["url"]

        if not title:
            continue

        # ----------------------------------------------------
        # 只看可能是海報競賽的內容
        # ----------------------------------------------------

        if not looks_like_poster_competition(
            title,
            text
        ):
            continue

        # ----------------------------------------------------
        # 找 Deadline
        # ----------------------------------------------------

        deadline = find_deadline(
            text
        )

        # 有些列表摘要沒有日期，
        # 再進入文章頁面找一次
        if deadline is None:

            try:

                print(
                    "Checking article:",
                    title
                )

                article_html = download(
                    url
                )

                article_soup = (
                    BeautifulSoup(
                        article_html,
                        "html.parser"
                    )
                )

                article_text = clean_text(
                    article_soup.get_text(
                        " ",
                        strip=True
                    )
                )

                deadline = find_deadline(
                    article_text
                )

                if deadline:

                    text = article_text

                time.sleep(0.3)

            except Exception as error:

                print(
                    "Article download failed:",
                    error
                )

        if deadline is None:

            print(
                "SKIP - no deadline:",
                title
            )

            continue

        # ----------------------------------------------------
        # 只保留 2026/06/01 之後
        # ----------------------------------------------------

        if deadline < CUTOFF_DATE:

            continue

        # ----------------------------------------------------
        # URL / title 去重
        # ----------------------------------------------------

        url_key = url.lower()

        title_key = title.lower()

        if url_key in seen_urls:
            continue

        if title_key in seen_titles:
            continue

        seen_urls.add(
            url_key
        )

        seen_titles.add(
            title_key
        )

        item = {
            "title": title,
            "deadline": deadline.isoformat(),
            "resultDate": "",
            "participating": False,
            "result": "pending",
            "url": url,
        }

        results.append(
            item
        )

        print("")
        print(
            "FOUND:",
            title
        )

        print(
            "DEADLINE:",
            deadline.isoformat()
        )

        print(
            "URL:",
            url
        )

    # --------------------------------------------------------
    # Deadline 排序
    # --------------------------------------------------------

    results.sort(
        key=lambda x: (
            x["deadline"],
            x["title"].lower()
        )
    )

    return results


# ============================================================
# 讀取舊 competitions.json
# ============================================================

def load_old_data():

    filename = (
        "competitions.json"
    )

    if not os.path.exists(
        filename
    ):
        return []

    try:

        with open(
            filename,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(
                f
            )

        if isinstance(
            data,
            list
        ):
            return data

    except Exception as error:

        print(
            "Could not read old data:",
            error
        )

    return []


# ============================================================
# 保留使用者資料
# ============================================================

def preserve_user_data(
    new_items,
    old_items
):

    by_url = {}
    by_title = {}

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

            by_url[
                normalize_url(url).lower()
            ] = item

        if title:

            by_title[
                title.lower()
            ] = item

    preserved = 0

    for item in new_items:

        old = (
            by_url.get(
                normalize_url(
                    item["url"]
                ).lower()
            )
            or
            by_title.get(
                item["title"].lower()
            )
        )

        if not old:
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
        "Preserved user records:",
        preserved
    )


# ============================================================
# 儲存 JSON
# ============================================================

def save_json(
    items
):

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

        f.write(
            "\n"
        )


# ============================================================
# 主程式
# ============================================================

def main():

    print("")
    print(
        "======================================"
    )

    print(
        "PosterTerritory Competition Updater"
    )

    print(
        "Cutoff date:",
        CUTOFF_DATE.isoformat()
    )

    print(
        "======================================"
    )

    # --------------------------------------------------------
    # 取得所有文章
    # --------------------------------------------------------

    posts = collect_listing_posts()

    print("")
    print(
        "Collected posts:",
        len(posts)
    )

    # --------------------------------------------------------
    # 建立 competitions
    # --------------------------------------------------------

    competitions = build_competitions(
        posts
    )

    print("")
    print(
        "======================================"
    )

    print(
        "FINAL COMPETITIONS:",
        len(competitions)
    )

    print(
        "======================================"
    )

    for number, item in enumerate(
        competitions,
        start=1
    ):

        print(
            f"{number}. "
            f"{item['deadline']} | "
            f"{item['title']}"
        )

    # --------------------------------------------------------
    # 安全機制
    # --------------------------------------------------------

    if len(competitions) < 5:

        print("")
        print(
            "ERROR: Too few competitions found."
        )

        print(
            "Refusing to overwrite competitions.json."
        )

        raise SystemExit(1)

    # --------------------------------------------------------
    # 保留舊資料
    # --------------------------------------------------------

    old_data = load_old_data()

    preserve_user_data(
        competitions,
        old_data
    )

    # --------------------------------------------------------
    # 寫入
    # --------------------------------------------------------

    save_json(
        competitions
    )

    print("")
    print(
        "======================================"
    )

    print(
        "SUCCESS"
    )

    print(
        "competitions.json updated."
    )

    print(
        "Total competitions:",
        len(competitions)
    )

    print(
        "======================================"
    )


if __name__ == "__main__":
    main()
