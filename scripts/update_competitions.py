
import json
import os
import re
import time
from datetime import date
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.posterterritory.com/"
PAGES_TO_SCAN = 3
START_URL = BASE_URL
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
        host = urlparse(url).netloc.lower()
        return host in {"", "posterterritory.com", "www.posterterritory.com"}
    except Exception:
        return False


def parse_date_text(text, default_year=None):
    """
    Parse common English dates. When a year is omitted, default_year is used.
    """
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
                re.IGNORECASE,
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
                re.IGNORECASE,
            ),
            "dmy",
        ),
        (
            re.compile(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b"),
            "ymd",
        ),
        (
            re.compile(
                r"\b"
                r"(January|Jan|February|Feb|March|Mar|April|Apr|May|"
                r"June|Jun|July|Jul|August|Aug|September|Sep|Sept|"
                r"October|Oct|November|Nov|December|Dec)"
                r"\s+(\d{1,2})(?:st|nd|rd|th)?\b",
                re.IGNORECASE,
            ),
            "md",
        ),
        (
            re.compile(
                r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
                r"(January|Jan|February|Feb|March|Mar|April|Apr|May|"
                r"June|Jun|July|Jul|August|Aug|September|Sep|Sept|"
                r"October|Oct|November|Nov|December|Dec)\b",
                re.IGNORECASE,
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
                    int(g[2]), MONTHS[g[0].lower()], int(g[1])
                )

            if kind == "dmy":
                return date(
                    int(g[2]), MONTHS[g[1].lower()], int(g[0])
                )

            if kind == "ymd":
                return date(
                    int(g[0]), int(g[1]), int(g[2])
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
        re.IGNORECASE,
    )
    if not match:
        return None

    try:
        roman = {
            "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
            "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
            "XI": 11, "XII": 12,
        }
        year = int(match.group(3)) if match.group(3) else default_year
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
    Only dates following a deadline-like keyword are treated as deadlines.
    If the year is omitted, default_year (normally publication year) is used.
    """
    text = clean_text(text)

    keywords = (
        r"last\s+deadline|submission\s+deadline|closing\s+date|"
        r"entries\s+close|deadline|submit"
    )

    # Longest/most-specific keyword first.
    for match in re.finditer(keywords, text, flags=re.IGNORECASE):
        chunk = text[match.end():match.end() + 180]

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


def find_publication_date(container):
    """
    Publication date is obtained from WordPress's own time/date link first,
    then from visible date text.
    """
    # Prefer <time datetime="...">.
    for element in container.find_all("time"):
        value = (
            element.get("datetime")
            or element.get("content")
            or element.get_text(" ", strip=True)
        )
        parsed = parse_date_text(value)
        if parsed:
            return parsed

    # WordPress Baskerville pages commonly have a date link.
    date_candidates = []
    for anchor in container.find_all("a", href=True):
        text = clean_text(anchor.get_text(" ", strip=True))
        parsed = parse_date_text(text)
        if parsed:
            date_candidates.append(parsed)

    if date_candidates:
        return date_candidates[-1]

    return parse_date_text(
        container.get_text(" ", strip=True)
    )


def extract_posts(soup):
    posts = []
    seen = set()

    articles = soup.find_all("article")

    if articles:
        containers = articles
    else:
        containers = []
        for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
            parent = heading.parent
            if parent:
                containers.append(parent)

    for container in containers:
        heading = container.find(
            ["h1", "h2", "h3", "h4"]
        )
        if not heading:
            continue

        title = clean_text(
            heading.get_text(" ", strip=True)
        )
        if not title:
            continue

        link = heading.find("a", href=True)
        if not link:
            link = container.find("a", href=True)
        if not link:
            continue

        url = normalize_url(
            link.get("href", "")
        )
        if not url or not same_domain(url):
            continue

        if url in seen:
            continue
        seen.add(url)

        official_url = ""
        for anchor in container.find_all("a", href=True):
            label = clean_text(
                anchor.get_text(" ", strip=True)
            ).lower()
            if label in {"more", "visit website"}:
                candidate = normalize_url(
                    anchor.get("href", "")
                )
                if candidate and not same_domain(candidate):
                    official_url = candidate
                    break

        posts.append(
            {
                "title": title,
                "url": url,
                "text": clean_text(
                    container.get_text(" ", strip=True)
                ),
                "publicationDate": find_publication_date(
                    container
                ),
                "officialUrl": official_url,
            }
        )

    return posts


def collect_first_three_pages():
    all_posts = {}
    for page_number in range(1, PAGES_TO_SCAN + 1):
        url = (
            START_URL
            if page_number == 1
            else BASE_URL + f"page/{page_number}/"
        )

        print("")
        print("======================================")
        print(f"Scanning PosterTerritory page {page_number}")
        print(url)

        try:
            html = download(url)
        except Exception as error:
            print("Unable to download page:", error)
            continue

        soup = BeautifulSoup(html, "html.parser")
        posts = extract_posts(soup)
        print("Posts found:", len(posts))

        for post in posts:
            existing = all_posts.get(post["url"])

            if existing:
                # Keep the most complete publication metadata available.
                if not existing.get("publicationDate") and post.get(
                    "publicationDate"
                ):
                    existing["publicationDate"] = post["publicationDate"]
                if not existing.get("officialUrl") and post.get(
                    "officialUrl"
                ):
                    existing["officialUrl"] = post["officialUrl"]
                continue

            all_posts[post["url"]] = post

        time.sleep(0.35)

    print("")
    print(
        "Total unique posts from first three pages:",
        len(all_posts),
    )
    return list(all_posts.values())


def download(url):
    print("Downloading:", url)
    response = session.get(url, timeout=30)
    print(
        "HTTP:",
        response.status_code,
        "Bytes:",
        len(response.content),
    )
    response.raise_for_status()
    return response.text


def load_json_list(filename):
    if not os.path.exists(filename):
        return []

    try:
        with open(filename, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, list) else []
    except Exception as error:
        print("Could not read", filename, ":", error)
        return []


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"initialized": False}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            state = json.load(file)
        return state if isinstance(state, dict) else {"initialized": False}
    except Exception:
        return {"initialized": False}


def save_state():
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(
            {
                "initialized": True,
                "pagesScannedPerUpdate": PAGES_TO_SCAN,
                "mode": "seed-three-pages-then-accumulate",
            },
            file,
            ensure_ascii=False,
            indent=2,
        )
        file.write("\n")


def preserve_user_data(new_items, old_items):
    by_url = {}
    by_title = {}

    for item in old_items:
        if not isinstance(item, dict):
            continue

        url = normalize_url(
            item.get("sourceUrl") or item.get("url", "")
        ).lower()
        title = clean_text(
            item.get("title", "")
        ).lower()

        if url:
            by_url[url] = item
        if title:
            by_title[title] = item

    for item in new_items:
        old = (
            by_url.get(
                normalize_url(
                    item.get("sourceUrl", "")
                ).lower()
            )
            or by_title.get(
                clean_text(item.get("title", "")).lower()
            )
        )

        if not old:
            continue

        item["participating"] = bool(
            old.get("participating", False)
        )
        item["result"] = (
            old.get("result", "pending")
            or "pending"
        )
        item["resultDate"] = (
            old.get("resultDate", "")
            or ""
        )


def choose_display_date(item):
    """
    Return the tracker-visible date.

    A deadline is stored without a marker.
    A publication-date fallback is stored with '*'.
    """
    deadline = clean_text(
        item.get("deadline", "")
    )

    if deadline:
        return deadline

    publication_date = clean_text(
        item.get("publicationDate", "")
    )

    if publication_date:
        return publication_date.rstrip("*") + "*"

    return ""


def make_item(post):
    publication_date = post.get("publicationDate")
    publication_year = (
        publication_date.year
        if isinstance(publication_date, date)
        else None
    )

    deadline = find_deadline(
        post.get("text", ""),
        default_year=publication_year,
    )

    if deadline is not None:
        display_date = deadline.isoformat()
    elif publication_date is not None:
        display_date = publication_date.isoformat() + "*"
    else:
        # A post without a detectable publication date cannot be reliably
        # ordered; keep it out rather than inventing a date.
        return None

    return {
        "title": clean_text(post.get("title", "")),
        "titleZh": "",
        "deadline": display_date,
        "resultDate": "",
        "participating": False,
        "result": "pending",
        "officialUrl": post.get("officialUrl", "") or "",
        "sourceUrl": normalize_url(post.get("url", "")),
        "url": normalize_url(post.get("url", "")),
    }


def merge_history(old_items, current_items, initialized):
    """
    First run: current first three pages become the complete clean seed.
    Later runs: current first three pages are upserted, and old records
    remain forever even after they leave the first three pages.
    """
    if not initialized:
        result = [
            dict(item)
            for item in current_items
            if isinstance(item, dict)
        ]
        return result

    result = []
    by_url = {}
    by_title = {}

    for old in old_items:
        if not isinstance(old, dict):
            continue

        copy = dict(old)
        result.append(copy)

        url = normalize_url(
            copy.get("sourceUrl") or copy.get("url", "")
        ).lower()
        title = clean_text(
            copy.get("title", "")
        ).lower()

        if url:
            by_url[url] = copy
        if title:
            by_title[title] = copy

    for fresh in current_items:
        url_key = normalize_url(
            fresh.get("sourceUrl") or fresh.get("url", "")
        ).lower()
        title_key = clean_text(
            fresh.get("title", "")
        ).lower()

        existing = (
            by_url.get(url_key)
            or by_title.get(title_key)
        )

        if existing is not None:
            # Preserve the user's participation/result fields.
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

            existing.clear()
            existing.update(fresh)

            existing["participating"] = bool(
                participation
            )
            existing["result"] = (
                result_value or "pending"
            )
            existing["resultDate"] = (
                result_date or ""
            )
        else:
            result.append(dict(fresh))

    return result


def save_json(items):
    # Sort by the actual date, ignoring the publication marker.
    def sort_key(item):
        return (
            str(item.get("deadline", "")).rstrip("*"),
            clean_text(item.get("title", "")).lower(),
        )

    items.sort(key=sort_key)

    with open(
        "competitions.json",
        "w",
        encoding="utf-8",
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
    print("Pages scanned per update:", PAGES_TO_SCAN)
    print("======================================")

    old_items = load_json_list(
        "competitions.json"
    )
    state = load_state()

    raw_posts = collect_first_three_pages()

    current_items = []

    for post in raw_posts:
        item = make_item(post)
        if item is None:
            print(
                "SKIP - no publication date:",
                post.get("title", ""),
            )
            continue

        current_items.append(item)

    initialized = bool(
        state.get("initialized", False)
    )

    if not initialized:
        print("")
        print(
            "FIRST RUN: rebuilding from current first three pages."
        )
    else:
        print("")
        print(
            "ACCUMULATE MODE: upserting current first three pages."
        )

    merged = merge_history(
        old_items,
        current_items,
        initialized=initialized,
    )

    preserve_user_data(
        merged,
        old_items,
    )

    save_json(merged)
    save_state()

    print("")
    print("======================================")
    print("SUCCESS")
    print("Current first-three-page entries:", len(current_items))
    print("Saved total entries:", len(merged))
    print("======================================")


if __name__ == "__main__":
    main()
