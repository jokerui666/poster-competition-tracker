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
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
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
# 官方網站判斷
# ============================================================

SOCIAL_DOMAINS = {
    "facebook.com", "instagram.com", "behance.net", "pinterest.com",
    "linkedin.com", "youtube.com", "youtu.be", "twitter.com",
    "x.com", "tiktok.com"
}

# 這些網域永遠不能被當成比賽官方網站
BLOCKED_OFFICIAL_DOMAINS = {
    "posterterritory.com",
    "www.posterterritory.com",
    "google.com",
    "googleusercontent.com",
    "translate.google.com",
    "facebook.com",
    "instagram.com",
    "behance.net",
    "pinterest.com",
    "linkedin.com",
    "youtube.com",
    "youtu.be",
    "twitter.com",
    "x.com",
    "tiktok.com",
}


def hostname(url):
    try:
        return (
            urlparse(url)
            .hostname
            or ""
        ).lower().removeprefix("www.")
    except Exception:
        return ""


def is_social(url):
    host = hostname(url)

    return any(
        host == domain
        or host.endswith("." + domain)
        for domain in SOCIAL_DOMAINS
    )


def is_blocked_official_domain(url):
    host = hostname(url)

    if not host:
        return True

    return (
        host in BLOCKED_OFFICIAL_DOMAINS
        or any(
            host.endswith("." + domain)
            for domain in BLOCKED_OFFICIAL_DOMAINS
        )
    )


def looks_like_real_webpage(url):
    """
    排除 mailto、javascript、圖片、PDF、下載檔與社群網址。
    """
    lowered = url.lower()

    if lowered.startswith(
        (
            "mailto:",
            "javascript:",
            "tel:",
            "data:",
        )
    ):
        return False

    if re.search(
        r"\.(pdf|jpg|jpeg|png|gif|webp|svg|zip|docx?|xlsx?)($|\?)",
        lowered
    ):
        return False

    return True


def anchor_context(anchor):
    """
    取得連結附近的文字。
    官方網站連結通常會出現在：
    Website / Official Website / Enter / Apply / Submission
    等文字附近。
    """
    parts = []

    text = clean_text(
        anchor.get_text(
            " ",
            strip=True
        )
    )

    if text:
        parts.append(text)

    parent = anchor.parent

    if parent:
        parent_text = clean_text(
            parent.get_text(
                " ",
                strip=True
            )
        )

        if parent_text:
            parts.append(parent_text)

    previous = anchor.find_previous(
        ["p", "li", "div", "td"]
    )

    if previous:
        previous_text = clean_text(
            previous.get_text(
                " ",
                strip=True
            )
        )

        if previous_text:
            parts.append(previous_text)

    return " ".join(parts).lower()


def find_official_url(article_url):
    """
    從「該場 PosterTerritory 文章」尋找該場比賽自己的官方網站。

    重要原則：
    1. 永遠排除 PosterTerritory。
    2. 永遠排除社群網站。
    3. 優先選擇連結文字/附近文字明確指出
       Official Website / Website / Apply / Enter 等的網址。
    4. 如果頁面只有一般外部連結，寧可回傳空字串，
       也不要把共同導覽網址誤判成官方網站。
    """
    try:
        html = download(article_url)
        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        candidates = []

        strong_words = (
            "official website",
            "official site",
            "visit website",
            "visit the website",
            "website",
            "web site",
            "visit site",
            "apply",
            "enter now",
            "enter competition",
            "submission",
            "submit",
            "call for entries",
            "register",
        )

        weak_words = (
            "competition",
            "contest",
            "poster",
            "biennale",
            "biennial",
            "festival",
            "award",
            "design",
            "graphic",
        )

        for anchor in soup.find_all(
            "a",
            href=True
        ):

            raw_href = clean_text(
                anchor.get(
                    "href",
                    ""
                )
            )

            if not raw_href:
                continue

            # 不接受 javascript / mailto 等
            if not looks_like_real_webpage(
                raw_href
            ):
                continue

            href = normalize_url(
                raw_href
            )

            if not href:
                continue

            host = hostname(href)

            # 絕不使用 PosterTerritory
            if same_domain(href):
                continue

            # 絕不使用社群
            if is_social(href):
                continue

            # 絕不使用明確封鎖網域
            if is_blocked_official_domain(
                href
            ):
                continue

            context = anchor_context(
                anchor
            )

            label = clean_text(
                anchor.get_text(
                    " ",
                    strip=True
                )
            ).lower()

            score = 0

            # ----------------------------------------------
            # 最重要：連結文字
            # ----------------------------------------------

            if any(
                word in label
                for word in strong_words
            ):
                score += 100

            # ----------------------------------------------
            # 連結附近的上下文
            # ----------------------------------------------

            if any(
                word in context
                for word in strong_words
            ):
                score += 50

            if any(
                word in context
                for word in weak_words
            ):
                score += 10

            # ----------------------------------------------
            # URL / domain 本身
            # ----------------------------------------------

            if any(
                word in host
                for word in weak_words
            ):
                score += 5

            # ----------------------------------------------
            # 排除明顯不是官方網站的常見連結
            # ----------------------------------------------

            if (
                "posterterritory"
                in host
            ):
                continue

            # 沒有任何官方網站訊號的外部網址，
            # 不直接採用。
            if score < 50:
                continue

            candidates.append(
                {
                    "score": score,
                    "url": href,
                    "host": host,
                    "label": label,
                }
            )

        if not candidates:
            print(
                "Official website: NOT FOUND"
            )
            return ""

        # 分數最高優先；同分時網址排序保持穩定
        candidates.sort(
            key=lambda item: (
                -item["score"],
                item["host"],
                item["url"],
            )
        )

        best = candidates[0]

        print(
            "Official website:",
            best["url"]
        )

        return best["url"]

    except Exception as error:

        print(
            "Official website lookup failed:",
            error
        )

        return ""


# ============================================================
# 繁體中文翻譯
# ============================================================

TRANSLATION_URL = (
    "https://api.mymemory.translated.net/get"
)


def translate_title_zh(title):
    """
    將英文比賽名稱翻成繁體中文。
    翻譯失敗時回傳空字串，不影響整個 Action。
    """
    try:
        response = session.get(
            TRANSLATION_URL,
            params={
                "q": title,
                "langpair": "en|zh-TW",
            },
            timeout=20
        )

        response.raise_for_status()

        payload = response.json()

        translated = clean_text(
            payload
            .get("responseData", {})
            .get("translatedText", "")
        )

        if translated:
            return translated

    except Exception as error:
        print(
            "Translation failed:",
            error
        )

    return ""


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
        r"(January|Jan|February|Feb|March|Mar|April|Apr|May|June|Jun|"
        r"July|Jul|August|Aug|September|Sep|Sept|October|Oct|"
        r"November|Nov|December|Dec)"
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
        r"(January|Jan|February|Feb|March|Mar|April|Apr|May|June|Jun|"
        r"July|Jul|August|Aug|September|Sep|Sept|October|Oct|"
        r"November|Nov|December|Dec)"
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


def find_publication_date(text):
    """
    Fallback date for items without an explicit Deadline.
    Prefer a 2026/2027 date because the tracker is currently focused on
    those competition years. This date is marked with * in the output.
    """
    text = clean_text(text)

    month_names = (
        "January|Jan|February|Feb|March|Mar|April|Apr|May|"
        "June|Jun|July|Jul|August|Aug|September|Sep|Sept|"
        "October|Oct|November|Nov|December|Dec"
    )

    patterns = [
        re.compile(
            rf"\b({month_names})\s+"
            r"(\d{1,2})(?:st|nd|rd|th)?"
            r"(?:,\s*|\s+)(2026|2027)\b",
            re.IGNORECASE,
        ),
        re.compile(
            rf"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
            rf"({month_names})(?:,\s*|\s+)(2026|2027)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(2026|2027)[-/](\d{1,2})[-/](\d{1,2})\b",
            re.IGNORECASE,
        ),
    ]

    for index, pattern in enumerate(patterns):
        match = pattern.search(text)
        if not match:
            continue

        try:
            groups = match.groups()

            if index == 0:
                month = MONTHS[groups[0].lower()]
                day = int(groups[1])
                year = int(groups[2])
                return date(year, month, day)

            if index == 1:
                day = int(groups[0])
                month = MONTHS[groups[1].lower()]
                year = int(groups[2])
                return date(year, month, day)

            return date(
                int(groups[0]),
                int(groups[1]),
                int(groups[2]),
            )

        except (ValueError, KeyError):
            continue

    return None



def find_deadline(text):
    """
    找比賽截止日期。

    重要原則：
    1. 優先且嚴格解析 Deadline / Last Deadline / Submission Deadline
       等關鍵字「後面」的日期。
    2. 支援完整月份與英文縮寫，例如 September / Sep / Sept。
    3. 如果文章明確有 Deadline 關鍵字但關鍵字後沒有可解析日期，
       不用文章發布日期或其他無關日期冒充 Deadline。
    4. 只有完全沒有 Deadline 類關鍵字時，才退回整篇文字搜尋。
    """

    text = clean_text(text)

    deadline_patterns = [
        r"last\s+deadline",
        r"submission\s+deadline",
        r"closing\s+date",
        r"entries\s+close",
        r"deadline",
        r"submit",
    ]

    date_patterns = [
        re.compile(r"\b(2026|2027)[-/](\d{1,2})[-/](\d{1,2})\b"),
        re.compile(
            r"\b(January|Jan|February|Feb|March|Mar|April|Apr|May|June|Jun|"
            r"July|Jul|August|Aug|September|Sep|Sept|October|Oct|"
            r"November|Nov|December|Dec)\s+(\d{1,2})(?:st|nd|rd|th)?"
            r"(?:,\s*|\s+)(2026|2027)\b", re.I
        ),
        re.compile(
            r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
            r"(January|Jan|February|Feb|March|Mar|April|Apr|May|June|Jun|"
            r"July|Jul|August|Aug|September|Sep|Sept|October|Oct|"
            r"November|Nov|December|Dec)(?:,\s*|\s+)(2026|2027)\b", re.I
        ),
        re.compile(
            r"\b(January|Jan|February|Feb|March|Mar|April|Apr|May|June|Jun|"
            r"July|Jul|August|Aug|September|Sep|Sept|October|Oct|"
            r"November|Nov|December|Dec)\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I
        ),
        re.compile(
            r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
            r"(January|Jan|February|Feb|March|Mar|April|Apr|May|June|Jun|"
            r"July|Jul|August|Aug|September|Sep|Sept|October|Oct|"
            r"November|Nov|December|Dec)\b", re.I
        ),
    ]

    def parse_date_from_chunk(chunk):
        candidates = []

        for pattern in date_patterns:
            for match in pattern.finditer(chunk):
                try:
                    groups = match.groups()

                    if match.lastindex == 3:
                        if groups[0].isdigit() and len(groups[0]) == 4:
                            parsed = date(
                                int(groups[0]),
                                int(groups[1]),
                                int(groups[2]),
                            )
                        elif groups[0].isdigit():
                            parsed = date(
                                int(groups[2]),
                                MONTHS[groups[1].lower()],
                                int(groups[0]),
                            )
                        else:
                            parsed = date(
                                int(groups[2]),
                                MONTHS[groups[0].lower()],
                                int(groups[1]),
                            )
                    else:
                        if groups[0].isdigit():
                            parsed = date(
                                2026,
                                MONTHS[groups[1].lower()],
                                int(groups[0]),
                            )
                        else:
                            parsed = date(
                                2026,
                                MONTHS[groups[0].lower()],
                                int(groups[1]),
                            )

                    candidates.append((match.start(), parsed))

                except (ValueError, KeyError):
                    continue

        if candidates:
            # The first date after the Deadline keyword wins.
            candidates.sort(key=lambda item: item[0])
            return candidates[0][1]

        roman = parse_roman_date(chunk)
        return roman if roman else None

    found_deadline_keyword = False

    # 只解析關鍵字後面的區域，避免抓到文章發布日期。
    for pattern in deadline_patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            found_deadline_keyword = True
            chunk = text[match.end():match.end() + 140]
            result = parse_date_from_chunk(chunk)
            if result:
                return result

    # 沒有 Deadline 類關鍵字時，不用文章中的其他日期冒充截止日。
    # 例如文章發布日 August 28, 2026 不得被當成 Deadline。
    return None


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
    text,
    from_competition_listing=False
):

    if from_competition_listing:
        return True

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
    page_url,
    from_competition_listing=False
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
                    "from_competition_listing": from_competition_listing,
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

    competition_listing_url = BASE_URL + "poster-competitions/"

    try:
        print("Scanning dedicated competition listing:", competition_listing_url)
        html = download(competition_listing_url)
        soup = BeautifulSoup(html, "html.parser")
        posts = extract_posts(
            soup,
            competition_listing_url,
            from_competition_listing=True,
        )
        print("Competition-listing posts found:", len(posts))
        for post in posts:
            if post["url"] and same_domain(post["url"]):
                all_posts[post["url"]] = post
    except Exception as error:
        print("Unable to download competition listing:", error)

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
            url,
            from_competition_listing=False,
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

            existing = all_posts.get(post_url)
            if existing and existing.get("from_competition_listing", False):
                post["from_competition_listing"] = True
            all_posts[post_url] = post

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
            text,
            from_competition_listing=post.get(
                "from_competition_listing",
                False
            ),
        ):
            print("SKIP - not poster competition:", title)
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

        date_type = "deadline"

        if deadline is None:
            # No explicit Deadline: keep the item sortable using the
            # publication date, and mark the visible date with *.
            publication_date = find_publication_date(text)

            if publication_date is None:
                print(
                    "SKIP - no deadline or publication date:",
                    title
                )
                continue

            deadline = publication_date
            date_type = "published"

        # ----------------------------------------------------
        # 只保留 2026/06/01 之後
        # ----------------------------------------------------

        if deadline < CUTOFF_DATE:

            print(
                "SKIP - before cutoff:",
                title,
                deadline.isoformat()
            )

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

        print(
            "Finding official website..."
        )

        official_url = find_official_url(url)

        time.sleep(0.3)

        print(
            "Translating title..."
        )

        title_zh = translate_title_zh(title)

        time.sleep(0.5)

        item = {
            "title": title,
            "titleZh": title_zh,
            "deadline": (
                deadline.isoformat()
                + ("*" if date_type == "published" else "")
            ),
            "resultDate": "",
            "participating": False,
            "result": "pending",

            # 官方比賽網站；找不到時保持空白
            "officialUrl": official_url,

            # PosterTerritory 原始資料頁
            "sourceUrl": url,

            # 保留舊欄位相容性：
            # 前端新版會優先使用 officialUrl
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
            deadline.isoformat(),
            "(publication date)" if date_type == "published" else ""
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
                    item.get("url", "")
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

        if not item.get("titleZh"):
            item["titleZh"] = old.get(
                "titleZh",
                ""
            ) or ""

        if not item.get("officialUrl"):
            item["officialUrl"] = old.get(
                "officialUrl",
                ""
            ) or ""

        if not item.get("sourceUrl"):
            item["sourceUrl"] = old.get(
                "sourceUrl",
                item.get("url", "")
            ) or item.get("url", "")

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

    official_count = sum(
        1 for item in competitions
        if item.get("officialUrl")
    )

    translated_count = sum(
        1 for item in competitions
        if item.get("titleZh")
    )

    print(
        "Official websites:",
        official_count
    )

    print(
        "Traditional Chinese titles:",
        translated_count
    )

    print(
        "======================================"
    )


if __name__ == "__main__":
    main()
