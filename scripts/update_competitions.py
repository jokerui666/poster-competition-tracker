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
CUTOFF_DATE = date(2026, 5, 1)

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
    Return a valid 2026/2027 deadline following a Deadline-like keyword.

    A yearless date such as "Deadline: August 31" is interpreted as 2026.
    A date explicitly belonging to another year, such as 2016, is rejected
    and will later fall back to the publication date with '*'.
    """
    text = clean_text(text)

    deadline_keywords = [
        r"last\s+deadline",
        r"submission\s+deadline",
        r"closing\s+date",
        r"entries\s+close",
        r"deadline",
        r"submit",
    ]

    month_pattern = (
        r"January|Jan|February|Feb|March|Mar|April|Apr|May|"
        r"June|Jun|July|Jul|August|Aug|September|Sep|Sept|"
        r"October|Oct|November|Nov|December|Dec"
    )

    full_patterns = [
        re.compile(
            r"\b(2026|2027)[-/](\d{1,2})[-/](\d{1,2})\b"
        ),
        re.compile(
            rf"\b({month_pattern})\s+(\d{{1,2}})(?:st|nd|rd|th)?"
            r"(?:,\s*|\s+)(2026|2027)\b",
            re.IGNORECASE,
        ),
        re.compile(
            rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_pattern})"
            r"(?:,\s*|\s+)(2026|2027)\b",
            re.IGNORECASE,
        ),
    ]

    yearless_patterns = [
        re.compile(
            rf"\b({month_pattern})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b",
            re.IGNORECASE,
        ),
        re.compile(
            rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_pattern})\b",
            re.IGNORECASE,
        ),
    ]

    def parse_chunk(chunk):
        candidates = []

        # Prefer explicitly-year-stamped dates.
        for pattern in full_patterns:
            for match in pattern.finditer(chunk):
                try:
                    groups = match.groups()

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

                    candidates.append(
                        (match.start(), parsed)
                    )

                except (ValueError, KeyError):
                    continue

        if candidates:
            candidates.sort(key=lambda item: item[0])
            return candidates[0][1]

        # Yearless form, e.g. "August 31".
        for pattern in yearless_patterns:
            for match in pattern.finditer(chunk):
                following = chunk[
                    match.end():
                    match.end() + 12
                ]

                # "August 31, 2016" is NOT a yearless 2026 date.
                if re.match(
                    r"\s*,?\s*(?:19|20)\d{2}\b",
                    following,
                ):
                    continue

                try:
                    groups = match.groups()

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

                    return parsed

                except (ValueError, KeyError):
                    continue

        roman = parse_roman_date(chunk)
        return roman if roman else None

    for keyword in deadline_keywords:
        for match in re.finditer(
            keyword,
            text,
            flags=re.IGNORECASE,
        ):
            chunk = text[
                match.end():
                match.end() + 160
            ]

            result = parse_chunk(chunk)

            if result:
                return result

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

def parse_publication_datetime_value(value):
    """Parse common WordPress date/time attributes into a date."""
    if not value:
        return None

    value = clean_text(value)

    # ISO datetime/date, e.g. 2026-08-28T10:20:00+00:00
    match = re.search(r"\b(2026|2027)-(\d{1,2})-(\d{1,2})\b", value)
    if match:
        try:
            return date(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
            )
        except ValueError:
            pass

    return parse_publication_date_text(value)


def parse_publication_date_text(text):
    """
    Parse a publication date from visible page/listing text.
    Only 2026/2027 are relevant to this tracker.
    """
    text = clean_text(text)

    patterns = [
        re.compile(
            r"\b(January|Jan|February|Feb|March|Mar|April|Apr|May|"
            r"June|Jun|July|Jul|August|Aug|September|Sep|Sept|"
            r"October|Oct|November|Nov|December|Dec)\s+"
            r"(\d{1,2})(?:st|nd|rd|th)?(?:,\s*|\s+)(2026|2027)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
            r"(January|Jan|February|Feb|March|Mar|April|Apr|May|"
            r"June|Jun|July|Jul|August|Aug|September|Sep|Sept|"
            r"October|Oct|November|Nov|December|Dec)(?:,\s*|\s+)"
            r"(2026|2027)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(2026|2027)[-/](\d{1,2})[-/](\d{1,2})\b"
        ),
    ]

    for index, pattern in enumerate(patterns):
        match = pattern.search(text)
        if not match:
            continue

        try:
            groups = match.groups()

            if index == 0:
                return date(
                    int(groups[2]),
                    MONTHS[groups[0].lower()],
                    int(groups[1]),
                )

            if index == 1:
                return date(
                    int(groups[2]),
                    MONTHS[groups[1].lower()],
                    int(groups[0]),
                )

            return date(
                int(groups[0]),
                int(groups[1]),
                int(groups[2]),
            )

        except (ValueError, KeyError):
            continue

    return None


def extract_publication_date(container):
    """
    Prefer WordPress's explicit <time> element. Fall back to visible text.
    """
    time_element = container.find("time")

    if time_element:
        for attr in ("datetime", "dateTime", "content"):
            parsed = parse_publication_datetime_value(
                time_element.get(attr, "")
            )
            if parsed:
                return parsed

        parsed = parse_publication_datetime_value(
            time_element.get_text(" ", strip=True)
        )
        if parsed:
            return parsed

    # WordPress listing pages often expose the publication date near the card.
    candidates = [
        container.find(
            class_=re.compile(
                r"(entry-date|published|post-date|posted)",
                re.IGNORECASE,
            )
        ),
        container.find(
            attrs={
                "itemprop": "datePublished"
            }
        ),
    ]

    for candidate in candidates:
        if not candidate:
            continue

        parsed = parse_publication_datetime_value(
            candidate.get("datetime", "")
        )
        if parsed:
            return parsed

        parsed = parse_publication_date_text(
            candidate.get_text(" ", strip=True)
        )
        if parsed:
            return parsed

    return parse_publication_date_text(
        container.get_text(" ", strip=True)
    )


def extract_posts(
    soup,
    page_url
):

    posts = []

    articles = soup.find_all("article")

    if articles:
        for article in articles:
            title_element = article.find(
                ["h1", "h2", "h3", "h4"]
            )

            if not title_element:
                continue

            title = clean_text(
                title_element.get_text(" ", strip=True)
            )

            if not title:
                continue

            link_element = title_element.find("a")

            if not link_element:
                link_element = article.find("a", href=True)

            if not link_element:
                continue

            url = normalize_url(
                link_element.get("href", "")
            )

            if not url:
                continue

            text = clean_text(
                article.get_text(" ", strip=True)
            )

            posts.append(
                {
                    "title": title,
                    "url": url,
                    "text": text,
                    "publication_date": extract_publication_date(article),
                }
            )

        return posts

    # Fallback for non-article layouts.
    headings = soup.find_all(
        ["h1", "h2", "h3", "h4"]
    )

    for heading in headings:
        title = clean_text(
            heading.get_text(" ", strip=True)
        )

        if not title:
            continue

        link = heading.find("a", href=True)

        if not link:
            continue

        url = normalize_url(
            link.get("href", "")
        )

        if not url:
            continue

        parent = heading.parent
        text = clean_text(
            parent.get_text(" ", strip=True)
        )

        posts.append(
            {
                "title": title,
                "url": url,
                "text": text,
                "publication_date": extract_publication_date(parent),
            }
        )

    return posts


# ============================================================
# Poster Competitions 專頁
# ============================================================

def extract_curated_competition_entries(soup):
    """
    Extract only entries belonging to the "Poster Competitions" section.

    The current page has:
      # Poster Competitions
      ...
      # Design programs and Summer Schools
      ...
      # Open calls and platforms with no deadline
    We stop before the next section so unrelated programs/platforms are not
    accidentally treated as competitions.
    """
    results = []

    heading = None
    for candidate in soup.find_all(
        ["h1", "h2", "h3"]
    ):
        if clean_text(
            candidate.get_text(" ", strip=True)
        ).lower() == "poster competitions":
            heading = candidate
            break

    if not heading:
        return results

    stop_titles = {
        "design programs and summer schools",
        "open calls and platforms with no deadline",
    }

    current = heading.find_next_sibling()

    while current:
        if current.name in {"h1", "h2", "h3"}:
            title = clean_text(
                current.get_text(" ", strip=True)
            ).lower()

            if title in stop_titles:
                break

        for anchor in current.find_all(
            "a",
            href=True
        ):
            label = clean_text(
                anchor.get_text(" ", strip=True)
            ).lower()

            if label != "more":
                continue

            container = anchor.parent
            for _ in range(4):
                if not container:
                    break

                block_text = clean_text(
                    container.get_text(" ", strip=True)
                )

                if 10 <= len(block_text) <= 700:
                    break

                container = container.parent

            if not container:
                continue

            # Use text immediately before More. The curated list is simple:
            # title + optional description/deadline + More.
            block_text = clean_text(
                container.get_text(" ", strip=True)
            )

            block_text = re.sub(
                r"\s+More\s*$",
                "",
                block_text,
                flags=re.IGNORECASE,
            )

            if not block_text:
                continue

            # Strip common metadata prefixes and choose a clean first segment.
            lines = [
                clean_text(x)
                for x in re.split(r"\s{2,}|\n", block_text)
                if clean_text(x)
            ]

            title_text = ""

            if lines:
                for candidate in lines:
                    lowered = candidate.lower()
                    if lowered.startswith(
                        (
                            "deadline",
                            "last deadline",
                            "categories",
                            "theme:",
                        )
                    ):
                        continue
                    title_text = candidate
                    break

            if not title_text:
                title_text = block_text

            title_text = re.sub(
                r"\bLast Deadline\b.*$",
                "",
                title_text,
                flags=re.IGNORECASE,
            ).strip()

            if not title_text:
                continue

            results.append(
                {
                    "title": clean_title(title_text),
                    "text": block_text,
                    "officialUrlHint": normalize_url(
                        anchor.get("href", "")
                    ),
                    "from_curated_listing": True,
                }
            )

        current = current.find_next_sibling()

    # De-duplicate titles while preserving order.
    unique = []
    seen = set()

    for item in results:
        key = item["title"].lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)

    return unique


def resolve_posterterritory_article_url(title):
    """
    Resolve a curated competition title to its PosterTerritory article.
    WordPress REST search is preferred; the site's own search page is fallback.
    """
    try:
        response = session.get(
            BASE_URL + "wp-json/wp/v2/search",
            params={
                "search": title,
                "per_page": 5,
                "subtype": "post",
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()

        if isinstance(payload, list):
            for item in payload:
                url = normalize_url(item.get("url", ""))
                if url and same_domain(url):
                    return url

    except Exception as error:
        print(
            "WordPress search failed:",
            error
        )

    try:
        response = session.get(
            BASE_URL,
            params={"s": title},
            timeout=20,
        )
        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        target = title.lower()

        for article in soup.find_all("article"):
            heading = article.find(
                ["h1", "h2", "h3", "h4"]
            )
            if not heading:
                continue

            found_title = clean_title(
                heading.get_text(" ", strip=True)
            )

            link = heading.find(
                "a",
                href=True
            )

            if (
                link
                and found_title.lower() == target
            ):
                url = normalize_url(
                    link.get("href", "")
                )
                if url and same_domain(url):
                    return url

        # Fallback: first PosterTerritory article result.
        article = soup.find("article")
        if article:
            link = article.find("a", href=True)
            if link:
                url = normalize_url(
                    link.get("href", "")
                )
                if url and same_domain(url):
                    return url

    except Exception as error:
        print(
            "PosterTerritory site search failed:",
            error
        )

    return ""


# ============================================================
# 逐頁搜尋
# ============================================================

def collect_listing_posts():

    all_posts = {}

    # A. Curated competition page: use only the competition section.
    competition_listing_url = BASE_URL + "poster-competitions/"

    print("")
    print("======================================")
    print("Scanning curated competition listing")
    print(competition_listing_url)

    try:
        html = download(
            competition_listing_url
        )
        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        entries = extract_curated_competition_entries(
            soup
        )

        print(
            "Curated competition entries:",
            len(entries)
        )

        for entry in entries:
            article_url = resolve_posterterritory_article_url(
                entry["title"]
            )

            if not article_url:
                continue

            all_posts[article_url] = {
                "title": entry["title"],
                "url": article_url,
                "text": entry["text"],
                "from_curated_listing": True,
                "officialUrlHint": entry.get(
                    "officialUrlHint",
                    ""
                ),
            }

            time.sleep(0.15)

    except Exception as error:
        print(
            "Unable to scan curated competition listing:",
            error
        )

    # B. Homepage pagination catches recent articles and their publication date.
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
        print(url)

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

            post_url = post["url"]

            if (
                not post_url
                or not same_domain(post_url)
            ):
                continue

            existing = all_posts.get(
                post_url
            )

            if existing:
                if existing.get(
                    "from_curated_listing",
                    False
                ):
                    existing["text"] = clean_text(
                        existing.get("text", "")
                        + " "
                        + post.get("text", "")
                    )
                    if post.get("publication_date"):
                        existing["publication_date"] = (
                            post["publication_date"]
                        )
                    continue

            all_posts[post_url] = post

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

def build_competitions(posts):

    results = []

    seen_urls = set()
    seen_titles = set()

    stats = {
        "found": 0,
        "before_cutoff": 0,
        "no_publication_date": 0,
        "publication_fallback": 0,
        "real_deadline": 0,
    }

    for post in posts:

        title = clean_title(
            post.get("title", "")
        )

        text = post.get("text", "")
        url = post.get("url", "")

        if not title:
            continue

        # Curated Poster Competitions entries are trusted as competitions.
        is_curated = post.get(
            "from_curated_listing",
            False
        )

        if not looks_like_poster_competition(
            title,
            text,
            from_competition_listing=is_curated,
        ):
            continue

        article_text = text
        publication_date = post.get(
            "publication_date"
        )

        # The publication date is the tracker cutoff basis.
        if publication_date is None:
            try:
                print(
                    "Checking article:",
                    title
                )

                article_html = download(url)

                article_soup = BeautifulSoup(
                    article_html,
                    "html.parser"
                )

                publication_date = extract_publication_date(
                    article_soup
                )

                article_text = clean_text(
                    article_soup.get_text(
                        " ",
                        strip=True
                    )
                )

                time.sleep(0.25)

            except Exception as error:
                print(
                    "Article lookup failed:",
                    error
                )

        if publication_date is None:
            stats["no_publication_date"] += 1
            print(
                "SKIP - no publication date:",
                title
            )
            continue

        if publication_date < CUTOFF_DATE:
            stats["before_cutoff"] += 1
            print(
                "SKIP - before cutoff:",
                title,
                publication_date.isoformat()
            )
            continue

        stats["found"] += 1

        deadline = find_deadline(article_text)
        date_type = "deadline"

        if deadline is None:
            deadline = publication_date
            date_type = "published"
            stats["publication_fallback"] += 1
        else:
            stats["real_deadline"] += 1

        url_key = normalize_url(url).lower()
        title_key = title.lower()

        if url_key in seen_urls or title_key in seen_titles:
            continue

        seen_urls.add(url_key)
        seen_titles.add(title_key)

        print("Finding official website...")

        official_url = (
            post.get("officialUrlHint", "")
            or find_official_url(url)
        )

        time.sleep(0.3)

        print("Translating title...")

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
            "officialUrl": official_url,
            "sourceUrl": url,
            "url": url,
        }

        results.append(item)

        print(
            "FOUND:",
            title
        )

        print(
            "PUBLISHED:",
            publication_date.isoformat()
        )

        print(
            "DEADLINE:",
            item["deadline"]
        )

    # JSON is stored oldest->newest just as before; the front-end reverses it.
    results.sort(
        key=lambda x: (
            x["deadline"].rstrip("*"),
            x["title"].lower()
        )
    )

    print("")
    print("======================================")
    print("Build summary")
    for key, value in stats.items():
        print(f"{key}:", value)
    print("======================================")

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
