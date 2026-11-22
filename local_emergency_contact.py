import os
import re
import time
import hashlib
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

DOCS_DIR = os.path.join(
    BASE_DIR,
    "docs"
)

CACHE_DIR = os.path.join(
    BASE_DIR,
    "cache",
    "global_emergency_numbers"
)

os.makedirs(
    DOCS_DIR,
    exist_ok=True
)

os.makedirs(
    CACHE_DIR,
    exist_ok=True
)

OUTPUT_FILE = os.path.join(
    DOCS_DIR,
    "05_global_emergency_numbers.txt"
)

ERROR_FILE = os.path.join(
    DOCS_DIR,
    "05_global_emergency_numbers_errors.txt"
)

ITU_URL = (
    "https://www.itu.int/net/itu-t/inrdb/"
    "e129_important_numbers.aspx"
)

MAX_RETRIES = 5

CONNECT_TIMEOUT = 20
READ_TIMEOUT = 120

MIN_DELAY = 2.5
MAX_DELAY = 6.0

USER_AGENT = (
    "EarthquakeHelper/1.0 "
    "(emergency-information research)"
)

TEMP_STATUS = {
    408,
    425,
    429,
    500,
    502,
    503,
    504
}

DENIED_STATUS = {
    401,
    403,
    451
}


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(
    "global-emergency-numbers"
)


# ============================================================
# SESSION
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.8"
})


# ============================================================
# HELPERS
# ============================================================

def now_utc():

    return datetime.now(
        timezone.utc
    ).isoformat()


def clean(text):

    if text is None:
        return ""

    text = re.sub(
        r"\s+",
        " ",
        str(text)
    )

    return text.strip()


def cache_file(url):

    digest = hashlib.sha256(
        url.encode("utf-8")
    ).hexdigest()

    return os.path.join(
        CACHE_DIR,
        digest + ".html"
    )


def log_error(message):

    with open(
        ERROR_FILE,
        "a",
        encoding="utf-8"
    ) as f:

        f.write(
            f"[{now_utc()}] {message}\n"
        )


# ============================================================
# DOWNLOAD
# ============================================================

def download(url):

    filename = cache_file(url)

    if os.path.exists(filename):

        logger.info(
            "CACHE: %s",
            url
        )

        with open(
            filename,
            "r",
            encoding="utf-8"
        ) as f:

            return f.read()

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        try:

            logger.info(
                "GET %d/%d: %s",
                attempt,
                MAX_RETRIES,
                url
            )

            response = session.get(
                url,
                timeout=(
                    CONNECT_TIMEOUT,
                    READ_TIMEOUT
                )
            )

            status = response.status_code

            if status == 200:

                response.encoding = (
                    response.apparent_encoding
                    or response.encoding
                    or "utf-8"
                )

                html = response.text

                with open(
                    filename,
                    "w",
                    encoding="utf-8"
                ) as f:

                    f.write(html)

                time.sleep(
                    MIN_DELAY
                )

                return html

            if status in DENIED_STATUS:

                message = (
                    f"Access denied HTTP {status}: "
                    f"{url}"
                )

                logger.error(message)
                log_error(message)

                return None

            if status in TEMP_STATUS:

                logger.warning(
                    "Temporary HTTP %d",
                    status
                )

                time.sleep(
                    attempt * 5
                )

                continue

            message = (
                f"HTTP {status}: {url}"
            )

            logger.error(message)
            log_error(message)

            return None

        except requests.RequestException as e:

            logger.warning(
                "Request failed: %s",
                e
            )

            if attempt < MAX_RETRIES:

                time.sleep(
                    attempt * 5
                )

            else:

                log_error(
                    f"Permanent request failure: "
                    f"{url} | {e}"
                )

    return None


# ============================================================
# PARSE ITU TABLE
# ============================================================

def parse_page(
    html,
    source_url
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    records = []

    tables = soup.find_all(
        "table"
    )

    for table in tables:

        rows = table.find_all(
            "tr"
        )

        if not rows:
            continue

        header = [
            clean(
                x.get_text(
                    " ",
                    strip=True
                )
            )
            for x in rows[0].find_all(
                ["th", "td"]
            )
        ]

        header_lower = [
            x.lower()
            for x in header
        ]

        if not any(
            "country" in x
            for x in header_lower
        ):
            continue

        if not any(
            "service" in x
            for x in header_lower
        ):
            continue

        for row in rows[1:]:

            cells = row.find_all(
                ["td", "th"]
            )

            values = [
                clean(
                    x.get_text(
                        " ",
                        strip=True
                    )
                )
                for x in cells
            ]

            if len(values) < 3:
                continue

            record = {

                "country":
                    values[0],

                "number":
                    values[1],

                "service":
                    values[2],

                "additional_information":
                    values[3]
                    if len(values) > 3
                    else "",

                "allocation":
                    values[4]
                    if len(values) > 4
                    else "",

                "note":
                    values[5]
                    if len(values) > 5
                    else "",

                "last_update":
                    values[6]
                    if len(values) > 6
                    else "",

                "source_url":
                    source_url,

                "retrieved_at":
                    now_utc()
            }

            if (
                record["country"]
                and record["number"]
                and record["service"]
            ):

                records.append(
                    record
                )

    return records


# ============================================================
# FIND NEXT PAGES
# ============================================================

def find_page_links(
    html,
    current_url
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    links = set()

    for a in soup.find_all(
        "a",
        href=True
    ):

        href = a["href"]

        absolute = urljoin(
            current_url,
            href
        )

        parsed = urlparse(
            absolute
        )

        if (
            parsed.netloc.lower()
            != "www.itu.int"
        ):
            continue

        if (
            "e129_important_numbers"
            not in parsed.path.lower()
        ):
            continue

        text = clean(
            a.get_text(
                " ",
                strip=True
            )
        ).lower()

        query = parsed.query.lower()

        if (
            "pg_" in query
            or "page" in query
            or text in {
                "next",
                "last"
            }
        ):

            links.add(
                absolute
            )

    return links


# ============================================================
# COLLECT
# ============================================================

def collect():

    queue = [
        ITU_URL
    ]

    visited = set()

    records = []

    while queue:

        url = queue.pop(0)

        if url in visited:
            continue

        visited.add(url)

        logger.info(
            "PROCESSING PAGE %d: %s",
            len(visited),
            url
        )

        html = download(
            url
        )

        if not html:
            continue

        page_records = parse_page(
            html,
            url
        )

        logger.info(
            "FOUND %d records",
            len(page_records)
        )

        records.extend(
            page_records
        )

        for link in find_page_links(
            html,
            url
        ):

            if link not in visited:
                queue.append(
                    link
                )

        # Prevent accidental infinite crawl
        if len(visited) >= 200:

            logger.error(
                "Pagination safety limit reached."
            )

            break

    return records


# ============================================================
# DEDUPLICATE
# ============================================================

def deduplicate(records):

    unique = {}

    for r in records:

        key = (
            r["country"].lower(),
            r["number"].lower(),
            r["service"].lower(),
            r[
                "additional_information"
            ].lower()
        )

        if key not in unique:
            unique[key] = r

    return list(
        unique.values()
    )


# ============================================================
# WRITE TXT
# ============================================================

def write_txt(records):

    records.sort(
        key=lambda x: (
            x["country"].lower(),
            x["service"].lower(),
            x["number"]
        )
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "EARTHQUAKE HELPER\n"
        )

        f.write(
            "GLOBAL EMERGENCY TELEPHONE NUMBERS\n"
        )

        f.write(
            "===================================\n\n"
        )

        f.write(
            "SOURCE\n"
        )

        f.write(
            "------\n"
        )

        f.write(
            "ITU-T E.129 Important Numbers\n"
        )

        f.write(
            f"{ITU_URL}\n\n"
        )

        f.write(
            "IMPORTANT\n"
        )

        f.write(
            "---------\n"
        )

        f.write(
            "Numbers are national emergency/social-service "
            "numbers reported through the ITU-T E.129 system. "
            "The chatbot should preserve the service category "
            "and country because emergency arrangements differ "
            "between countries. Verify current local information "
            "when possible.\n\n"
        )

        f.write(
            f"Retrieved: {now_utc()}\n"
        )

        f.write(
            f"Total records: {len(records)}\n\n"
        )

        current_country = None

        for r in records:

            if (
                r["country"]
                != current_country
            ):

                current_country = (
                    r["country"]
                )

                f.write(
                    "\n"
                    + "=" * 72
                    + "\n"
                )

                f.write(
                    f"COUNTRY: "
                    f"{current_country}\n"
                )

                f.write(
                    "=" * 72
                    + "\n\n"
                )

            f.write(
                f"Emergency service: "
                f"{r['service']}\n"
            )

            f.write(
                f"Phone number: "
                f"{r['number']}\n"
            )

            if r[
                "additional_information"
            ]:

                f.write(
                    "Additional information: "
                    f"{r['additional_information']}\n"
                )

            if r["allocation"]:

                f.write(
                    "Allocation/assignment: "
                    f"{r['allocation']}\n"
                )

            if r["note"]:

                f.write(
                    f"Note: {r['note']}\n"
                )

            if r["last_update"]:

                f.write(
                    f"ITU last update: "
                    f"{r['last_update']}\n"
                )

            f.write(
                f"Source: "
                f"{r['source_url']}\n"
            )

            f.write(
                f"Retrieved: "
                f"{r['retrieved_at']}\n\n"
            )


# ============================================================
# MAIN
# ============================================================

def main():

    logger.info(
        "Starting ITU emergency-number collection."
    )

    records = collect()

    logger.info(
        "Raw records: %d",
        len(records)
    )

    records = deduplicate(
        records
    )

    logger.info(
        "Unique records: %d",
        len(records)
    )

    if not records:

        log_error(
            "No emergency-number records collected."
        )

        logger.error(
            "No records collected."
        )

        return

    write_txt(
        records
    )

    logger.info(
        "Finished."
    )

    logger.info(
        "Output: %s",
        OUTPUT_FILE
    )


if __name__ == "__main__":
    main()