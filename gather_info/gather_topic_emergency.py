# gathering_info/gather_topic_05.py

"""
TOPIC 05 — EMERGENCY CONTACTS BY COUNTRY

Purpose
-------
Build a RAG-friendly emergency-contact knowledge base for countries/
geographical areas around the world.

Primary global source
---------------------
ITU-T E.129 Important Numbers:
https://www.itu.int/net/itu-t/inrdb/e129_important_numbers.aspx

The collector does NOT assume that one ITU page contains all records.
It attempts several extraction methods and follows pagination.

Output
------
docs/05_emergency_contacts.txt
docs/05_emergency_contacts_errors.txt
docs/05_emergency_contacts_conflicts.txt

Cache
-----
cache/itu_e129/

Important
---------
Emergency numbers are life-safety information.

This collector therefore:
- preserves source URLs
- preserves ITU's "Last update" field
- records our retrieval timestamp
- does not silently resolve conflicting numbers
- marks old records as potentially stale
- does not bypass authentication/CAPTCHA/access controls
- keeps failed countries in the error log
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import random
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DOCS_DIR = BASE_DIR / "docs"
CACHE_DIR = BASE_DIR / "cache" / "itu_e129"

DOCS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = DOCS_DIR / "05_emergency_contacts.txt"
ERROR_FILE = DOCS_DIR / "05_emergency_contacts_errors.txt"
CONFLICT_FILE = DOCS_DIR / "05_emergency_contacts_conflicts.txt"

ITU_URL = (
    "https://www.itu.int/net/itu-t/inrdb/"
    "e129_important_numbers.aspx"
)

# Try several page sizes.
PAGE_SIZES = [100, 50, 25]

# Maximum pages for safety.
MAX_PAGES = 100

# Do not hammer ITU.
MIN_DELAY = 2.0
MAX_DELAY = 5.0

MAX_RETRIES = 5

CONNECT_TIMEOUT = 20
READ_TIMEOUT = 120

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/157.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Connection": "keep-alive",
}

# If True, the collector saves raw HTML.
# This is extremely useful when the site changes.
SAVE_RAW_HTML = True

# If True, try multiple extraction methods.
MULTI_METHOD_EXTRACTION = True


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("topic05")


# ============================================================
# HTTP SESSION
# ============================================================

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# HELPERS
# ============================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def polite_delay():
    delay = random.uniform(MIN_DELAY, MAX_DELAY)
    logger.debug("Sleeping %.2f seconds", delay)
    time.sleep(delay)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cache_path(url: str) -> Path:
    digest = sha256_text(url)
    return CACHE_DIR / f"{digest}.html"


def safe_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return value[:100]


def clean_text(value) -> str:
    if value is None:
        return ""

    value = str(value)

    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_service(service: str) -> str:
    service = clean_text(service).lower()

    mapping = {
        "emergency": "Emergency",
        "police": "Police",
        "fire": "Fire",
        "medical": "Medical",
        "ambulance": "Medical / Ambulance",
        "ambulance service": "Medical / Ambulance",
        "traffic": "Traffic",
        "hazards": "Hazards",
        "child help-line": "Child Help Line",
        "child helpline": "Child Help Line",
        "other": "Other",
    }

    return mapping.get(
        service,
        service.title() if service else "Unknown",
    )


def is_probably_header(row) -> bool:
    text = " ".join(clean_text(x).lower() for x in row)

    return (
        "country" in text
        and "number" in text
        and "service" in text
    )


# ============================================================
# HTTP FETCH
# ============================================================

def fetch_url(url: str) -> str | None:

    cached = cache_path(url)

    if cached.exists():
        logger.info("Using cached ITU page: %s", cached.name)

        try:
            return cached.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except Exception as exc:
            logger.warning(
                "Could not read cache %s: %s",
                cached,
                exc,
            )

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):

        try:
            logger.info(
                "GET %s (attempt %d/%d)",
                url,
                attempt,
                MAX_RETRIES,
            )

            response = session.get(
                url,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                allow_redirects=True,
            )

            logger.info(
                "HTTP %s | %d bytes | %s",
                response.status_code,
                len(response.content),
                response.url,
            )

            # Explicit access restrictions.
            if response.status_code in (401, 403, 451):

                logger.error(
                    "Access denied by server: HTTP %s",
                    response.status_code,
                )

                last_error = (
                    f"HTTP {response.status_code}: access denied"
                )

                break

            # Temporary errors.
            if response.status_code in (
                408,
                425,
                429,
                500,
                502,
                503,
                504,
            ):

                last_error = (
                    f"HTTP {response.status_code}"
                )

                wait = min(
                    60,
                    (2 ** attempt) + random.uniform(1, 4),
                )

                logger.warning(
                    "Temporary HTTP error. Waiting %.1f seconds.",
                    wait,
                )

                time.sleep(wait)

                continue

            response.raise_for_status()

            html = response.text

            if SAVE_RAW_HTML:

                try:
                    cached.write_text(
                        html,
                        encoding="utf-8",
                    )

                except Exception as exc:
                    logger.warning(
                        "Could not save cache: %s",
                        exc,
                    )

            return html

        except requests.RequestException as exc:

            last_error = str(exc)

            logger.warning(
                "Request failed: %s",
                exc,
            )

            if attempt < MAX_RETRIES:

                wait = min(
                    60,
                    (2 ** attempt) + random.uniform(1, 4),
                )

                time.sleep(wait)

    logger.error(
        "Failed to fetch %s: %s",
        url,
        last_error,
    )

    return None


# ============================================================
# METHOD 1 — PANDAS
# ============================================================

def extract_with_pandas(html: str) -> list[dict]:

    try:
        import pandas as pd
    except ImportError:
        logger.warning(
            "pandas is not installed; skipping pandas parser."
        )
        return []

    records = []

    try:
        tables = pd.read_html(io.StringIO(html))

    except Exception as exc:

        logger.debug(
            "pandas.read_html failed: %s",
            exc,
        )

        return []

    logger.info(
        "pandas found %d HTML table(s).",
        len(tables),
    )

    for table_index, df in enumerate(tables):

        logger.info(
            "Inspecting pandas table %d: shape=%s",
            table_index,
            df.shape,
        )

        if df.empty:
            continue

        columns = [
            clean_text(c).lower()
            for c in df.columns
        ]

        # Look for the ITU table.
        country_col = None
        number_col = None
        service_col = None

        for i, col in enumerate(columns):

            if "country" in col:
                country_col = i

            elif "number" in col:
                number_col = i

            elif "service" in col:
                service_col = i

        if (
            country_col is None
            or number_col is None
            or service_col is None
        ):
            continue

        for _, row in df.iterrows():

            country = clean_text(
                row.iloc[country_col]
            )

            number = clean_text(
                row.iloc[number_col]
            )

            service = clean_text(
                row.iloc[service_col]
            )

            if not country or not number:
                continue

            records.append({
                "country": country,
                "number": number,
                "service": normalize_service(service),
                "additional_information": (
                    clean_text(row.iloc[3])
                    if len(row) > 3
                    else ""
                ),
                "allocated_or_assigned": (
                    clean_text(row.iloc[4])
                    if len(row) > 4
                    else ""
                ),
                "note": (
                    clean_text(row.iloc[5])
                    if len(row) > 5
                    else ""
                ),
                "last_update": (
                    clean_text(row.iloc[6])
                    if len(row) > 6
                    else ""
                ),
                "extraction_method": "pandas.read_html",
            })

    return records


# ============================================================
# METHOD 2 — BEAUTIFULSOUP TABLE PARSER
# ============================================================

def extract_with_bs4(html: str) -> list[dict]:

    soup = BeautifulSoup(html, "html.parser")

    records = []

    tables = soup.find_all("table")

    logger.info(
        "BeautifulSoup found %d table(s).",
        len(tables),
    )

    for table_index, table in enumerate(tables):

        rows = table.find_all("tr")

        if not rows:
            continue

        header_row = None

        for tr in rows:

            cells = tr.find_all(
                ["th", "td"]
            )

            values = [
                clean_text(c.get_text(" ", strip=True))
                for c in cells
            ]

            if is_probably_header(values):

                header_row = values
                break

        if not header_row:
            continue

        headers = [
            h.lower()
            for h in header_row
        ]

        def find_column(words):

            for i, h in enumerate(headers):

                for word in words:

                    if word in h:
                        return i

            return None

        country_i = find_column(["country"])
        number_i = find_column(["number"])
        service_i = find_column(["service"])

        if (
            country_i is None
            or number_i is None
            or service_i is None
        ):
            continue

        for tr in rows:

            cells = tr.find_all(
                ["td", "th"]
            )

            values = [
                clean_text(c.get_text(" ", strip=True))
                for c in cells
            ]

            if len(values) < 3:
                continue

            if is_probably_header(values):
                continue

            try:
                country = values[country_i]
                number = values[number_i]
                service = values[service_i]
            except IndexError:
                continue

            if not country or not number:
                continue

            records.append({
                "country": country,
                "number": number,
                "service": normalize_service(service),
                "additional_information": (
                    values[3]
                    if len(values) > 3
                    else ""
                ),
                "allocated_or_assigned": (
                    values[4]
                    if len(values) > 4
                    else ""
                ),
                "note": (
                    values[5]
                    if len(values) > 5
                    else ""
                ),
                "last_update": (
                    values[6]
                    if len(values) > 6
                    else ""
                ),
                "extraction_method": "BeautifulSoup",
            })

    return records


# ============================================================
# METHOD 3 — TEXT FALLBACK
# ============================================================

def extract_with_text_fallback(html: str) -> list[dict]:

    """
    The ITU page is also exposed as readable structured text
    by indexing systems. If the normal HTML table parser fails,
    inspect visible table-like text.

    This is intentionally conservative.
    """

    soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text(
        "\n",
        strip=True,
    )

    lines = [
        clean_text(line)
        for line in text.splitlines()
    ]

    lines = [
        line
        for line in lines
        if line
    ]

    records = []

    # Example:
    #
    # Afghanistan 100 Police - - - 2012-04-03
    #
    # We only accept lines ending in YYYY-MM-DD.

    pattern = re.compile(
        r"^(?P<country>.+?)\s+"
        r"(?P<number>\d[\d\s;,-]*)\s+"
        r"(?P<service>"
        r"Emergency|Police|Fire|Medical|Traffic|"
        r"Hazards|Child help-line|Other"
        r")\s+"
        r"(?P<rest>.*?)\s+"
        r"(?P<date>\d{4}-\d{2}-\d{2})$",
        re.IGNORECASE,
    )

    for line in lines:

        match = pattern.match(line)

        if not match:
            continue

        country = clean_text(
            match.group("country")
        )

        number = clean_text(
            match.group("number")
        )

        service = normalize_service(
            match.group("service")
        )

        rest = clean_text(
            match.group("rest")
        )

        date = match.group("date")

        if not country or not number:
            continue

        records.append({
            "country": country,
            "number": number,
            "service": service,
            "additional_information": rest,
            "allocated_or_assigned": "",
            "note": "",
            "last_update": date,
            "extraction_method": "text_fallback",
        })

    return records


# ============================================================
# COMBINED EXTRACTION
# ============================================================

def extract_records(html: str) -> list[dict]:

    all_records = []

    # Method 1
    records = extract_with_pandas(html)

    if records:
        logger.info(
            "Pandas extracted %d records.",
            len(records),
        )

        all_records.extend(records)

    # Method 2
    if MULTI_METHOD_EXTRACTION:

        records = extract_with_bs4(html)

        if records:

            logger.info(
                "BeautifulSoup extracted %d records.",
                len(records),
            )

            all_records.extend(records)

    # Method 3
    if not all_records:

        records = extract_with_text_fallback(html)

        if records:

            logger.info(
                "Text fallback extracted %d records.",
                len(records),
            )

            all_records.extend(records)

    # Deduplicate.
    unique = {}

    for record in all_records:

        key = (
            record["country"].lower(),
            record["number"],
            record["service"].lower(),
            record["last_update"],
        )

        unique[key] = record

    return list(unique.values())


# ============================================================
# PAGINATION DISCOVERY
# ============================================================

def discover_pagination_urls(
    html: str,
    current_url: str,
) -> list[str]:

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    urls = []

    for a in soup.find_all("a"):

        href = a.get("href")

        if not href:
            continue

        text = clean_text(
            a.get_text(" ", strip=True)
        )

        href_lower = href.lower()

        # Pagination-related link.
        looks_like_page = (
            text.isdigit()
            or text.lower() in {
                "next",
                "last",
                ">",
                ">>",
            }
            or "page" in href_lower
            or "pg_" in href_lower
        )

        if not looks_like_page:
            continue

        absolute = urljoin(
            current_url,
            href,
        )

        if absolute not in urls:
            urls.append(absolute)

    return urls


# ============================================================
# PAGINATED ITU COLLECTION
# ============================================================

def collect_itu_pages() -> list[dict]:

    all_records = []

    visited_urls = set()

    queue = []

    # Start with the normal endpoint.
    queue.append(ITU_URL)

    pages_processed = 0

    while queue and pages_processed < MAX_PAGES:

        url = queue.pop(0)

        if url in visited_urls:
            continue

        visited_urls.add(url)

        logger.info(
            "Processing ITU page %d: %s",
            pages_processed + 1,
            url,
        )

        html = fetch_url(url)

        if html is None:
            continue

        pages_processed += 1

        records = extract_records(html)

        logger.info(
            "Parsed %d ITU records from this page.",
            len(records),
        )

        all_records.extend(records)

        # Discover pagination.
        next_urls = discover_pagination_urls(
            html,
            url,
        )

        logger.info(
            "Discovered %d pagination candidate(s).",
            len(next_urls),
        )

        for next_url in next_urls:

            if next_url not in visited_urls:
                queue.append(next_url)

        polite_delay()

    # Deduplicate everything.
    unique = {}

    for record in all_records:

        key = (
            record["country"].lower(),
            record["number"],
            record["service"].lower(),
            record["last_update"],
        )

        unique[key] = record

    result = list(unique.values())

    logger.info(
        "Total unique ITU records collected: %d",
        len(result),
    )

    return result


# ============================================================
# COUNTRY GROUPING
# ============================================================

def group_by_country(records):

    grouped = defaultdict(list)

    for record in records:

        grouped[
            record["country"]
        ].append(record)

    return dict(
        sorted(
            grouped.items(),
            key=lambda item: item[0].lower(),
        )
    )


# ============================================================
# STALENESS
# ============================================================

def classify_staleness(last_update: str) -> str:

    if not last_update:
        return "Unknown"

    try:

        dt = datetime.strptime(
            last_update,
            "%Y-%m-%d",
        ).replace(
            tzinfo=timezone.utc
        )

        now = datetime.now(timezone.utc)

        age_days = (
            now - dt
        ).days

        if age_days <= 365:
            return "Current-ish"

        if age_days <= 3 * 365:
            return "Aging"

        return "Old"

    except Exception:
        return "Unknown"


# ============================================================
# CONFLICT DETECTION
# ============================================================

def detect_conflicts(grouped):

    conflicts = []

    for country, records in grouped.items():

        services = defaultdict(set)

        for record in records:

            service = record["service"]

            # Focus on emergency-relevant services.
            if service in {
                "Emergency",
                "Police",
                "Fire",
                "Medical",
                "Medical / Ambulance",
            }:

                services[service].add(
                    record["number"]
                )

        for service, numbers in services.items():

            if len(numbers) > 1:

                conflicts.append({
                    "country": country,
                    "service": service,
                    "numbers": sorted(numbers),
                })

    return conflicts


# ============================================================
# WRITE MAIN RAG FILE
# ============================================================

def write_output(grouped, total_records):

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
    ) as f:

        f.write(
            "TOPIC 05 — EMERGENCY CONTACTS BY COUNTRY\n"
        )

        f.write("=" * 72 + "\n\n")

        f.write(
            "PURPOSE\n"
        )

        f.write(
            "This document contains emergency and socially important "
            "telephone numbers reported through the ITU-T E.129 "
            "Important Numbers database.\n\n"
        )

        f.write(
            "IMPORTANT SAFETY NOTE\n"
        )

        f.write(
            "Emergency telephone numbers can change. The chatbot "
            "must consider the user's current country or geographic "
            "location before recommending a number. ITU records may "
            "also have different update dates. The chatbot should "
            "prefer current official national emergency information "
            "when available and should not silently resolve conflicting "
            "numbers.\n\n"
        )

        f.write(
            f"COLLECTION TIME: {utc_now()}\n"
        )

        f.write(
            f"ITU RECORDS COLLECTED: {total_records}\n"
        )

        f.write(
            f"COUNTRIES / GEOGRAPHICAL AREAS: {len(grouped)}\n"
        )

        f.write(
            f"PRIMARY SOURCE: {ITU_URL}\n\n"
        )

        f.write(
            "SERVICE CATEGORIES\n"
            "------------------\n"
            "Emergency\n"
            "Police\n"
            "Fire\n"
            "Medical / Ambulance\n"
            "Traffic\n"
            "Hazards\n"
            "Child Help Line\n"
            "Other\n\n"
        )

        for country, records in grouped.items():

            f.write("\n")
            f.write("=" * 72 + "\n")
            f.write(f"COUNTRY / AREA: {country}\n")
            f.write("=" * 72 + "\n\n")

            records = sorted(
                records,
                key=lambda r: (
                    r["service"],
                    r["number"],
                ),
            )

            for record in records:

                f.write(
                    f"SERVICE: {record['service']}\n"
                )

                f.write(
                    f"NUMBER: {record['number']}\n"
                )

                if record[
                    "additional_information"
                ]:

                    f.write(
                        "ADDITIONAL INFORMATION: "
                        f"{record['additional_information']}\n"
                    )

                if record[
                    "allocated_or_assigned"
                ]:

                    f.write(
                        "ALLOCATED / ASSIGNED: "
                        f"{record['allocated_or_assigned']}\n"
                    )

                if record["note"]:

                    f.write(
                        f"NOTE: {record['note']}\n"
                    )

                f.write(
                    f"ITU LAST UPDATE: "
                    f"{record['last_update'] or 'Unknown'}\n"
                )

                f.write(
                    "DATA AGE STATUS: "
                    f"{classify_staleness(record['last_update'])}\n"
                )

                f.write(
                    f"SOURCE: {ITU_URL}\n"
                )

                f.write(
                    f"RETRIEVED: {utc_now()}\n"
                )

                f.write(
                    f"EXTRACTION METHOD: "
                    f"{record['extraction_method']}\n\n"
                )


# ============================================================
# WRITE CONFLICT FILE
# ============================================================

def write_conflicts(conflicts):

    with CONFLICT_FILE.open(
        "w",
        encoding="utf-8",
    ) as f:

        f.write(
            "TOPIC 05 — EMERGENCY CONTACT CONFLICTS\n"
        )

        f.write("=" * 72 + "\n\n")

        f.write(
            "These are countries where ITU contains more than "
            "one number for the same emergency-relevant service.\n\n"
        )

        if not conflicts:

            f.write(
                "No conflicts detected.\n"
            )

            return

        for conflict in conflicts:

            f.write(
                f"COUNTRY: {conflict['country']}\n"
            )

            f.write(
                f"SERVICE: {conflict['service']}\n"
            )

            f.write(
                "NUMBERS: "
                + ", ".join(
                    conflict["numbers"]
                )
                + "\n"
            )

            f.write(
                "ACTION: Verify against a current "
                "official national source before "
                "treating one number as authoritative.\n\n"
            )


# ============================================================
# WRITE ERROR FILE
# ============================================================

def write_error(message):

    with ERROR_FILE.open(
        "a",
        encoding="utf-8",
    ) as f:

        f.write(
            f"[{utc_now()}] {message}\n"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    logger.info("=" * 60)
    logger.info(
        "TOPIC 05 — EMERGENCY CONTACTS BY COUNTRY"
    )
    logger.info("=" * 60)

    logger.info(
        "Starting ITU E.129 collection..."
    )

    records = collect_itu_pages()

    if not records:

        error = (
            "No ITU records were collected. "
            "The collector tried multiple extraction methods. "
            "Check cache/itu_e129/ for the raw response and "
            "05_emergency_contacts_errors.txt."
        )

        logger.error(error)

        write_error(error)

        # DO NOT create an apparently valid empty RAG file.
        raise RuntimeError(error)

    grouped = group_by_country(records)

    conflicts = detect_conflicts(grouped)

    logger.info(
        "Countries / geographical areas: %d",
        len(grouped),
    )

    logger.info(
        "Total records: %d",
        len(records),
    )

    logger.info(
        "Conflicting services: %d",
        len(conflicts),
    )

    write_output(
        grouped,
        len(records),
    )

    write_conflicts(
        conflicts,
    )

    logger.info(
        "Output written to: %s",
        OUTPUT_FILE,
    )

    logger.info(
        "Conflict report written to: %s",
        CONFLICT_FILE,
    )

    logger.info(
        "Finished successfully."
    )


if __name__ == "__main__":
    main()