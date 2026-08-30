
import json
import os
import re
import time
from datetime import date
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.posterterritory.com/"
START_PAGE = BASE_URL
PAGES_TO_SCAN = 3

# This version intentionally does NOT use a date cutoff.
# First run seeds the tracker from current pages 1-3.
# Later runs accumulate new records and keep old records forever.
ACCUMULATOR_VERSION = 1
STATE_FILE = "tracker_state.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

session = requests.Session()
session.headers.update(HEADERS)

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

NON_COMPETITION_HINTS = (
    "poster recipe series",
    "poster recipes",
    "frontline features",
    "dear friends of the posterterritory initiative",
    "donation",
    "offline/online conference",
)


def clean_text(text):
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_url(url):
    if not url:
        return ""
    return urljoin(BASE_URL, url).split("#")[0].rstrip("/")


def same_domain(url):
    try:
        return urlparse(url).netloc.lower() in {
            "",
            "posterterritory.com",
            "www.posterterritory.com",
        }
    except Exception:
        return False


def download(url):
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def parse_date_text(text, default_year=None):
    text = clean_text(text)

    patterns = [
        (
            re.compile(
                r"\b"
                r"(January|Jan|February|Feb|March|Mar|April|Apr|May|"
                r"June|Jun|July|Jul|August|Aug|September|Sep|Sept|"
                r"October|Oct|November|Nov|December|Dec)"
                r"\s+(\d{1,2})(?:st|nd|rd|th)?"
                r"(?:,\s*|\s+)(\d{4})\b",
                re.I,
            ),
            "mdy",
        ),
        (
            re.compile(
                r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
                r"(January|Jan|February|Feb|March|Mar|April|Apr|May|"
                r"June|Jun|July|Jul|August|Aug|September|Sep|Sept|"
                r"October|Oct|November|Nov|December|Dec)"
                r"(?:,\s*|\s+)(\d{4})\b",
                re.I,
            ),
            "dmy",
        ),
        (
            re.compile(
                r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b"
            ),
            "ymd",
        ),
        (
            re.compile(
                r"\b"
                r"(January|Jan|February|Feb|March|Mar|April|Apr|May|"
                r"June|Jun|July|Jul|August|Aug|September|Sep|Sept|"
                r"October|Oct|November|Nov|December|Dec)"
                r"\s+(\d{1,2})(?:st|nd|rd|th)?\b",
                re.I,
            ),
            "md",
        ),
        (
            re.compile(
                r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
                r"(January|Jan|February|Feb|March|Mar|April|Apr|May|"
                r"June|Jun|July|Jul|August|Aug|September|Sep|Sept|"
                r"October|Oct|November|Nov|December|Dec)\b",
                re.I,
            ),
            "dm",
        ),
    ]

    for pattern, kind in patterns:
        match = pattern.search(text)
        if not match:
            continue

        try:
            g = match.groups()

            if kind == "mdy":
                return date(
                    int(g[2]),
                    MONTHS[g[0].lower()],
                    int(g[1]),
                )

            if kind == "dmy":
                return date(
                    int(g[2]),
                    MONTHS[g[1].lower()],
                    int(g[0]),
                )

            if kind == "ymd":
                return date(
                    int(g[0]),
                    int(g[1]),
                    int(g[2]),
                )

            if default_year is None:
                continue

            if kind == "md":
                return date(
                    int(default_year),
                    MONTHS[g[0].lower()],
                    int(g[1]),
                )

            if kind == "dm":
                return date(
                    int(default_year),
                    MONTHS[g[1].lower()],
                    int(g[0]),
                )

        except (ValueError, KeyError):
            continue

    return None


def parse_roman_date(text, default_year=None):
    match = re.search(
        r"\b(\d{1,2})\s+"
        r"(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)"
        r"(?:\s+(\d{4}))?\b",
        clean_text(text),
        re.I,
    )

    if not match:
        return None

    try:
        roman = {
            "I": 1, "II": 2, "III": 3, "IV": 4,
            "V": 5, "VI": 6, "VII": 7, "VIII": 8,
            "IX": 9, "X": 10, "XI": 11, "XII": 12,
        }

        year = (
            int(match.group(3))
            if match.group(3)
            else default_year
        )

        if year is None:
            return None

        return date(
            year,
            roman[match.group(2).upper()],
            int(match.group(1)),
        )

    except (ValueError, KeyError):
        return None


def find_deadline(text, default_year=None):
    """
    Only parse a date immediately associated with a deadline-like keyword.
    A yearless deadline inherits the publication year.
    """
    text = clean_text(text)

    keywords = (
        r"last\s+deadline|submission\s+deadline|"
        r"closing\s+date|entries\s+close|deadline|submit"
    )

    for keyword in re.finditer(
        keywords,
        text,
        flags=re.I,
    ):
        chunk = text[
            keyword.end():
            keyword.end() + 180
        ]

        parsed = parse_date_text(
            chunk,
            default_year=default_year,
        )

        if parsed:
            return parsed

        parsed = parse_roman_date(
            chunk,
            default_year=default_year,
        )

        if parsed:
            return parsed

    return None


def extract_publication_date(container):
    # WordPress generally provides <time datetime="...">.
    for time_element in container.find_all("time"):
        for value in (
            time_element.get("datetime", ""),
            time_element.get("content", ""),
            time_element.get_text(" ", strip=True),
        ):
            parsed = parse_date_text(value)
            if parsed:
                return parsed

    # Also inspect date-like classes/attributes.
    candidates = container.find_all(
        attrs={
            "class": re.compile(
                r"(entry-date|published|post-date|posted)",
                re.I,
            )
        }
    )

    for candidate in candidates:
        for value in (
            candidate.get("datetime", ""),
            candidate.get("content", ""),
            candidate.get_text(" ", strip=True),
        ):
            parsed = parse_date_text(value)
            if parsed:
                return parsed

    # Final fallback: visible text.
    return parse_date_text(
        container.get_text(" ", strip=True)
    )


def should_include_post(title, text):
    combined = (
        clean_text(title)
        + " "
        + clean_text(text)
    ).lower()

    # We intentionally do NOT require words such as "poster",
    # "biennale", or "competition": that was causing legitimate
    # entries such as BULLSEYE/Hiiibrand to disappear.
    for hint in NON_COMPETITION_HINTS:
        if hint in combined:
            return False

    return True


def extract_posts(soup):
    posts = []

    for article in soup.find_all("article"):
        heading = article.find(
            ["h1", "h2", "h3", "h4"]
        )

        if not heading:
            continue

        link = heading.find("a", href=True)
        if not link:
            link = article.find("a", href=True)

        if not link:
            continue

        title = clean_text(
            heading.get_text(" ", strip=True)
        )
        url = normalize_url(
            link.get("href", "")
        )

        if not title or not url or not same_domain(url):
            continue

        text = clean_text(
            article.get_text(" ", strip=True)
        )

        posts.append(
            {
                "title": title,
                "url": url,
                "text": text,
                "publicationDate": extract_publication_date(
                    article
                ),
            }
        )

    return posts


def collect_first_three_pages():
    all_posts = {}

    for page_number in range(
        1,
        PAGES_TO_SCAN + 1
    ):
        url = (
            START_PAGE
            if page_number == 1
            else BASE_URL + f"page/{page_number}/"
        )

        print(
            f"Scanning page {page_number}: {url}"
        )

        try:
            html = download(url)
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

        posts = extract_posts(soup)

        print(
            f"Posts found on page {page_number}:",
            len(posts)
        )

        for post in posts:
            existing = all_posts.get(
                post["url"]
            )

            if existing:
                if (
                    existing.get("publicationDate") is None
                    and post.get("publicationDate") is not None
                ):
                    existing["publicationDate"] = (
                        post["publicationDate"]
                    )
                existing["text"] = clean_text(
                    existing.get("text", "")
                    + " "
                    + post.get("text", "")
                )
            else:
                all_posts[
                    post["url"]
                ] = post

        time.sleep(0.35)

    print(
        "Total unique posts from pages 1-3:",
        len(all_posts)
    )

    return list(
        all_posts.values()
    )


def find_official_url(article_url):
    try:
        html = download(article_url)
        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        strong_words = (
            "official website",
            "official site",
            "visit website",
            "website",
            "visit site",
            "apply",
            "submit",
            "enter now",
            "enter competition",
            "submission",
            "register",
        )

        for anchor in soup.find_all(
            "a",
            href=True
        ):
            href = normalize_url(
                anchor.get("href", "")
            )

            if (
                not href
                or same_domain(href)
            ):
                continue

            label = clean_text(
                anchor.get_text(" ", strip=True)
            ).lower()

            context = clean_text(
                anchor.parent.get_text(
                    " ",
                    strip=True
                )
                if anchor.parent
                else ""
            ).lower()

            if any(
                word in label
                or word in context
                for word in strong_words
            ):
                return href

    except Exception as error:
        print(
            "Official website lookup failed:",
            error
        )

    return ""


TRANSLATION_URL = (
    "https://api.mymemory.translated.net/get"
)


def clean_translated_title(value):
    value = clean_text(value)

    if not value:
        return ""

    lowered = value.lower()

    # MyMemory sometimes returns quota/warning strings as the translated text.
    if (
        "mymemory warning" in lowered
        or "quota exceeded" in lowered
        or "please use" in lowered
        and "api" in lowered
    ):
        return ""

    return value


def translate_title_zh(title, retries=3):
    """
    Translate the competition title to Traditional Chinese.
    Retry transient API failures so the front-end does not lose titleZh
    for a whole batch during a temporary service hiccup.
    """
    title = clean_text(title)

    if not title:
        return ""

    for attempt in range(1, retries + 1):
        try:
            response = session.get(
                TRANSLATION_URL,
                params={
                    "q": title,
                    "langpair": "en|zh-TW",
                },
                timeout=20,
            )

            response.raise_for_status()

            data = response.json()

            translated = clean_translated_title(
                data.get(
                    "responseData",
                    {}
                ).get(
                    "translatedText",
                    ""
                )
            )

            if translated:
                return translated

            # A valid HTTP response with an empty translation should not
            # be retried aggressively; one short retry can still recover
            # from transient upstream errors.
            if attempt < retries:
                time.sleep(0.8)

        except Exception as error:
            print(
                f"Translation failed (attempt {attempt}/{retries}):",
                error
            )

            if attempt < retries:
                time.sleep(1.2)

    return ""


def load_json_list(filename):
    if not os.path.exists(filename):
        return []

    try:
        with open(
            filename,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

        return data if isinstance(
            data,
            list
        ) else []

    except Exception as error:
        print(
            "Could not read",
            filename,
            ":",
            error
        )
        return []


def load_state():
    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

        return data if isinstance(
            data,
            dict
        ) else {}

    except Exception:
        return {}


def save_state():
    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            {
                "initialized": True,
                "accumulatorVersion": ACCUMULATOR_VERSION,
                "pagesScannedPerUpdate": PAGES_TO_SCAN,
                "mode": "first-three-pages-then-accumulate",
            },
            file,
            ensure_ascii=False,
            indent=2,
        )
        file.write("\n")


def preserve_user_data(new_items, old_items):
    by_url = {}

    for item in old_items:
        if not isinstance(item, dict):
            continue

        key = normalize_url(
            item.get("sourceUrl")
            or item.get("url", "")
        ).lower()

        if key:
            by_url[key] = item

    for item in new_items:
        key = normalize_url(
            item.get("sourceUrl")
            or item.get("url", "")
        ).lower()

        old = by_url.get(key)

        if not old:
            continue

        item["participating"] = bool(
            old.get(
                "participating",
                False
            )
        )
        item["result"] = (
            old.get("result", "pending")
            or "pending"
        )
        item["resultDate"] = (
            old.get("resultDate", "")
            or ""
        )

        if not item.get("titleZh"):
            item["titleZh"] = (
                old.get("titleZh", "")
                or ""
            )


def make_item(post):
    title = clean_text(
        post.get("title", "")
    )

    url = normalize_url(
        post.get("url", "")
    )

    publication_date = post.get(
        "publicationDate"
    )

    if publication_date is None:
        return None

    deadline = find_deadline(
        post.get("text", ""),
        default_year=publication_date.year
    )

    if deadline is not None:
        display_date = deadline.isoformat()
    else:
        display_date = (
            publication_date.isoformat()
            + "*"
        )

    return {
        "title": title,
        "titleZh": "",
        "deadline": display_date,
        "resultDate": "",
        "participating": False,
        "result": "pending",
        "officialUrl": "",
        "sourceUrl": url,
        "url": url,
    }


def merge_history(
    old_items,
    current_items,
    initialized
):
    """
    First run of this accumulator version:
      replace the old dataset with the current first-three-page seed.

    Later runs:
      update records seen on pages 1-3, add new ones, never delete old ones.
    """
    if not initialized:
        return [
            dict(item)
            for item in current_items
        ]

    result = []
    by_url = {}

    for old in old_items:
        if not isinstance(old, dict):
            continue

        copy = dict(old)
        result.append(copy)

        key = normalize_url(
            copy.get("sourceUrl")
            or copy.get("url", "")
        ).lower()

        if key:
            by_url[key] = copy

    for fresh in current_items:
        key = normalize_url(
            fresh.get("sourceUrl")
            or fresh.get("url", "")
        ).lower()

        existing = by_url.get(key)

        if existing:
            participation = existing.get(
                "participating",
                False
            )
            result_value = existing.get(
                "result",
                "pending"
            )
            result_date = existing.get(
                "resultDate",
                ""
            )
            title_zh = existing.get(
                "titleZh",
                ""
            )

            existing.clear()
            existing.update(fresh)

            existing["participating"] = bool(
                participation
            )
            existing["result"] = (
                result_value
                or "pending"
            )
            existing["resultDate"] = (
                result_date
                or ""
            )

            if not existing.get("titleZh"):
                existing["titleZh"] = title_zh

        else:
            result.append(
                dict(fresh)
            )

    return result


def save_json(items):
    items.sort(
        key=lambda item: (
            str(
                item.get(
                    "deadline",
                    ""
                )
            ).rstrip("*"),
            clean_text(
                item.get(
                    "title",
                    ""
                )
            ).lower(),
        ),
        reverse=True,
    )

    with open(
        "competitions.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            items,
            file,
            ensure_ascii=False,
            indent=2,
        )
        file.write("\n")


def main():
    print("")
    print("======================================")
    print("PosterTerritory 3-page accumulator")
    print("Pages scanned:", PAGES_TO_SCAN)
    print("Date cutoff: NONE")
    print("======================================")

    old_items = load_json_list(
        "competitions.json"
    )

    state = load_state()

    initialized = (
        state.get("initialized") is True
        and state.get("accumulatorVersion")
        == ACCUMULATOR_VERSION
    )

    posts = collect_first_three_pages()

    current_items = []

    for post in posts:
        if not should_include_post(
            post.get("title", ""),
            post.get("text", ""),
        ):
            print(
                "SKIP - obvious non-competition/editorial:",
                post.get("title", ""),
            )
            continue

        item = make_item(post)

        if item is None:
            print(
                "SKIP - no publication date:",
                post.get("title", ""),
            )
            continue

        current_items.append(item)

    # Enrich the current batch with official links and translations.
    for item in current_items:
        print(
            "Enriching:",
            item["title"]
        )

        item["officialUrl"] = find_official_url(
            item["sourceUrl"]
        )

        item["titleZh"] = translate_title_zh(
            item["title"]
        )

        # Keep a small pause between translation requests.
        time.sleep(0.8)

    merged = merge_history(
        old_items,
        current_items,
        initialized=initialized,
    )

    preserve_user_data(
        merged,
        old_items,
    )

    save_json(
        merged
    )

    save_state()

    print("")
    print("======================================")
    print("SUCCESS")
    print(
        "Current page-1-to-3 entries:",
        len(current_items)
    )
    print(
        "Saved total entries:",
        len(merged)
    )
    print(
        "Mode:",
        "ACCUMULATE"
        if initialized
        else "FRESH 3-PAGE SEED",
    )
    print("======================================")


if __name__ == "__main__":
    main()
