import csv
import hashlib
import json
import logging
import re
import time

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIGURATION
# ============================================================

BASE_URL = (
    "https://www.itu.int/net/itu-t/inrdb/"
    "e129_important_numbers.aspx"
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DOCS_DIR = PROJECT_ROOT / "docs"
CACHE_DIR = PROJECT_ROOT / "cache" / "itu_e129"

DOCS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

CACHE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

OUTPUT_TXT = (
    DOCS_DIR / "05_global_emergency_numbers.txt"
)

OUTPUT_CSV = (
    DOCS_DIR / "05_global_emergency_numbers.csv"
)

OUTPUT_JSON = (
    DOCS_DIR / "05_global_emergency_numbers.json"
)

ERROR_LOG = (
    DOCS_DIR / "05_global_emergency_numbers_errors.txt"
)


# ============================================================
# SETTINGS
# ============================================================

PAGE_SIZE = 100

REQUEST_DELAY = 3.0

TIMEOUT = (
    20,
    120,
)

MAX_RETRIES = 4

RETRY_STATUS_CODES = {
    408,
    425,
    429,
    500,
    502,
    503,
    504,
}

# ITU currently reports about 1160 records.
EXPECTED_MIN_RECORDS = 1000


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(
    "ITU-E129"
)


# ============================================================
# HTTP SESSION
# ============================================================

session = requests.Session()

session.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/157.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }
)


# ============================================================
# HELPERS
# ============================================================

def utc_now():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
    )


def clean_text(value):
    if value is None:
        return ""

    value = value.replace(
        "\xa0",
        " "
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def normalize_header(value):
    """
    Normalize table headers so these all become
    comparable:

        Country
        Country/Geographical Area
        COUNTRY / GEOGRAPHICAL AREA
    """

    value = clean_text(value)

    value = value.lower()

    value = value.replace(
        "/",
        " "
    )

    value = value.replace(
        "-",
        " "
    )

    value = re.sub(
        r"[^a-z0-9 ]",
        "",
        value
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def cache_filename(url):
    digest = hashlib.sha256(
        url.encode("utf-8")
    ).hexdigest()

    return (
        CACHE_DIR
        / f"{digest}.html"
    )


def save_error(message):
    with ERROR_LOG.open(
        "a",
        encoding="utf-8"
    ) as f:

        f.write(
            f"[{utc_now()}] "
            f"{message}\n"
        )


# ============================================================
# FETCH
# ============================================================

def fetch_page(url):
    """
    Fetch a webpage using cache + retry.
    """

    cache_file = cache_filename(
        url
    )

    # --------------------------------------------------------
    # CACHE
    # --------------------------------------------------------

    if cache_file.exists():

        logger.info(
            "CACHE HIT: %s",
            url
        )

        return cache_file.read_text(
            encoding="utf-8",
            errors="ignore"
        )

    # --------------------------------------------------------
    # REQUEST
    # --------------------------------------------------------

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        try:

            logger.info(
                "Fetching %d/%d: %s",
                attempt,
                MAX_RETRIES,
                url
            )

            response = session.get(
                url,
                timeout=TIMEOUT,
                allow_redirects=True
            )

            logger.info(
                "HTTP %d | %d bytes",
                response.status_code,
                len(response.content)
            )

            # ------------------------------------------------
            # SUCCESS
            # ------------------------------------------------

            if response.status_code == 200:

                html = response.text

                cache_file.write_text(
                    html,
                    encoding="utf-8"
                )

                return html

            # ------------------------------------------------
            # RETRY
            # ------------------------------------------------

            if response.status_code in RETRY_STATUS_CODES:

                wait = min(
                    60,
                    2 ** attempt
                )

                logger.warning(
                    "Temporary HTTP %d. "
                    "Waiting %.1f seconds.",
                    response.status_code,
                    wait
                )

                time.sleep(
                    wait
                )

                continue

            # ------------------------------------------------
            # BLOCKED
            # ------------------------------------------------

            if response.status_code in {
                401,
                403,
                451
            }:

                message = (
                    f"Access blocked: "
                    f"HTTP {response.status_code} "
                    f"| {url}"
                )

                logger.error(
                    message
                )

                save_error(
                    message
                )

                return None

            # ------------------------------------------------
            # OTHER ERROR
            # ------------------------------------------------

            message = (
                f"Unexpected HTTP "
                f"{response.status_code} "
                f"| {url}"
            )

            logger.error(
                message
            )

            save_error(
                message
            )

            return None

        except requests.RequestException as exc:

            logger.warning(
                "Request error: %s",
                exc
            )

            if attempt < MAX_RETRIES:

                wait = min(
                    60,
                    2 ** attempt
                )

                time.sleep(
                    wait
                )

            else:

                save_error(
                    f"Request failed: "
                    f"{url} | {exc}"
                )

    return None


# ============================================================
# COUNTRY LIST
# ============================================================

def discover_countries(html):
    """
    Extract country IDs from the ITU country selector.
    """

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    selects = soup.find_all(
        "select"
    )

    best_select = None
    best_count = 0

    for select in selects:

        options = select.find_all(
            "option"
        )

        valid = 0

        for option in options:

            value = clean_text(
                option.get(
                    "value",
                    ""
                )
            )

            text = clean_text(
                option.get_text(
                    " ",
                    strip=True
                )
            )

            if value and text:
                valid += 1

        if valid > best_count:

            best_count = valid
            best_select = select

    if best_select is None:

        raise RuntimeError(
            "Could not find ITU country selector."
        )

    countries = []

    seen = set()

    for option in best_select.find_all(
        "option"
    ):

        country_id = clean_text(
            option.get(
                "value",
                ""
            )
        )

        country_name = clean_text(
            option.get_text(
                " ",
                strip=True
            )
        )

        if not country_id:
            continue

        if not country_name:
            continue

        # Ignore generic selection options.
        if country_name.lower() in {
            "select",
            "select country",
            "all",
            "all countries",
        }:
            continue

        key = (
            country_id,
            country_name
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        countries.append(
            {
                "id": country_id,
                "name": country_name
            }
        )

    logger.info(
        "Discovered %d countries/geographical areas.",
        len(countries)
    )

    return countries


# ============================================================
# FIND ITU DATA TABLE
# ============================================================

def find_data_table(soup):
    """
    Find the table containing the actual
    E.129 records.

    The current ITU table has:

        Country/Geographical Area
        Number
        Service category
        Additional information
        Allocated or assigned
        Note
        Last update
    """

    tables = soup.find_all(
        "table"
    )

    best_table = None
    best_score = 0

    for table in tables:

        table_text = clean_text(
            table.get_text(
                " ",
                strip=True
            )
        )

        normalized = normalize_header(
            table_text
        )

        score = 0

        # Actual ITU wording.
        if (
            "country geographical area"
            in normalized
        ):
            score += 5

        if (
            "service category"
            in normalized
        ):
            score += 3

        if (
            "additional information"
            in normalized
        ):
            score += 2

        if (
            "allocated or assigned"
            in normalized
        ):
            score += 2

        if (
            "last update"
            in normalized
        ):
            score += 2

        if score > best_score:

            best_score = score
            best_table = table

    if best_table is not None:

        logger.info(
            "Found ITU data table. Score=%d",
            best_score
        )

    return best_table


# ============================================================
# FIND HEADER ROW
# ============================================================

def find_header_row(table):
    """
    Find the row containing the actual ITU
    column headers.
    """

    rows = table.find_all(
        "tr"
    )

    for row in rows:

        cells = row.find_all(
            ["th", "td"]
        )

        if not cells:
            continue

        values = [
            normalize_header(
                cell.get_text(
                    " ",
                    strip=True
                )
            )
            for cell in cells
        ]

        joined = " | ".join(
            values
        )

        # Actual ITU wording.
        has_country = (
            "country geographical area"
            in joined
        )

        has_number = (
            "number"
            in values
        )

        has_service = (
            "service category"
            in joined
        )

        if (
            has_country
            and has_number
            and has_service
        ):

            return row

    return None


# ============================================================
# PARSE ITU TABLE
# ============================================================

def parse_table(
    html,
    source_url
):
    """
    Parse one ITU country page.
    """

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    table = find_data_table(
        soup
    )

    if table is None:

        logger.error(
            "ITU data table not found."
        )

        return []

    header_row = find_header_row(
        table
    )

    if header_row is None:

        logger.error(
            "ITU table found, "
            "but header row could not be identified."
        )

        # Diagnostic output.
        logger.error(
            "Table text preview: %s",
            clean_text(
                table.get_text(
                    " ",
                    strip=True
                )
            )[:500]
        )

        return []

    # --------------------------------------------------------
    # Build header map
    # --------------------------------------------------------

    header_cells = header_row.find_all(
        ["th", "td"]
    )

    header_map = {}

    for index, cell in enumerate(
        header_cells
    ):

        header = normalize_header(
            cell.get_text(
                " ",
                strip=True
            )
        )

        header_map[
            header
        ] = index

    logger.info(
        "Detected columns: %s",
        list(header_map.keys())
    )

    # --------------------------------------------------------
    # Resolve column indexes
    # --------------------------------------------------------

    def find_column(
        *names
    ):

        for name in names:

            normalized = normalize_header(
                name
            )

            if normalized in header_map:

                return header_map[
                    normalized
                ]

        return None

    country_index = find_column(
        "Country/Geographical Area",
        "Country",
        "Geographical Area"
    )

    number_index = find_column(
        "Number"
    )

    service_index = find_column(
        "Service category"
    )

    additional_index = find_column(
        "Additional information"
    )

    allocated_index = find_column(
        "Allocated or assigned"
    )

    note_index = find_column(
        "Note"
    )

    update_index = find_column(
        "Last update"
    )

    # --------------------------------------------------------
    # Verify mandatory columns
    # --------------------------------------------------------

    if (
        country_index is None
        or number_index is None
        or service_index is None
    ):

        logger.error(
            "Mandatory ITU columns missing."
        )

        logger.error(
            "Columns found: %s",
            list(header_map.keys())
        )

        return []

    # --------------------------------------------------------
    # Parse data rows
    # --------------------------------------------------------

    records = []

    for row in table.find_all(
        "tr"
    ):

        if row == header_row:
            continue

        cells = row.find_all(
            ["td", "th"]
        )

        if not cells:
            continue

        values = [
            clean_text(
                cell.get_text(
                    " ",
                    strip=True
                )
            )
            for cell in cells
        ]

        # Need enough cells.
        if len(values) < 3:
            continue

        def value_at(index):

            if index is None:
                return ""

            if index >= len(values):
                return ""

            return values[index]

        country = value_at(
            country_index
        )

        number = value_at(
            number_index
        )

        service = value_at(
            service_index
        )

        if not country:
            continue

        if not number:
            continue

        # Avoid accidental repeated header.
        if (
            normalize_header(
                country
            )
            == "country geographical area"
        ):
            continue

        record = {
            "country": country,
            "number": number,
            "service": service,
            "additional_information": value_at(
                additional_index
            ),
            "allocated_or_assigned": value_at(
                allocated_index
            ),
            "note": value_at(
                note_index
            ),
            "last_update": value_at(
                update_index
            ),
            "source": source_url,
            "retrieved_at": utc_now()
        }

        records.append(
            record
        )

    logger.info(
        "Parsed %d ITU records.",
        len(records)
    )

    return records


# ============================================================
# BUILD COUNTRY URL
# ============================================================

def build_country_url(
    country_id
):

    params = {
        "country": country_id,
        "pg_size": PAGE_SIZE
    }

    return (
        BASE_URL
        + "?"
        + urlencode(params)
    )


# ============================================================
# RECORD KEY
# ============================================================

def record_key(
    record
):

    return (
        clean_text(
            record.get(
                "country",
                ""
            )
        ).lower(),

        clean_text(
            record.get(
                "number",
                ""
            )
        ).lower(),

        clean_text(
            record.get(
                "service",
                ""
            )
        ).lower(),

        clean_text(
            record.get(
                "additional_information",
                ""
            )
        ).lower()
    )


# ============================================================
# COLLECT ONE COUNTRY
# ============================================================

def collect_country(
    country
):

    country_id = country[
        "id"
    ]

    country_name = country[
        "name"
    ]

    url = build_country_url(
        country_id
    )

    logger.info(
        "------------------------------------------------"
    )

    logger.info(
        "Country: %s",
        country_name
    )

    logger.info(
        "Country ID: %s",
        country_id
    )

    html = fetch_page(
        url
    )

    if html is None:

        logger.error(
            "FAILED: %s",
            country_name
        )

        return []

    records = parse_table(
        html,
        url
    )

    logger.info(
        "%s -> %d records",
        country_name,
        len(records)
    )

    return records


# ============================================================
# COLLECT EVERYTHING
# ============================================================

def collect_all_records():

    logger.info(
        "Downloading ITU main page..."
    )

    main_html = fetch_page(
        BASE_URL
    )

    if main_html is None:

        raise RuntimeError(
            "Could not download ITU main page."
        )

    countries = discover_countries(
        main_html
    )

    if not countries:

        raise RuntimeError(
            "No countries were discovered "
            "from the ITU country selector."
        )

    all_records = []

    seen_records = set()

    successful = 0
    failed = 0

    total = len(
        countries
    )

    for index, country in enumerate(
        countries,
        start=1
    ):

        logger.info(
            "Processing country %d/%d",
            index,
            total
        )

        if index > 1:

            time.sleep(
                REQUEST_DELAY
            )

        records = collect_country(
            country
        )

        if records:

            successful += 1

        else:

            failed += 1

        for record in records:

            key = record_key(
                record
            )

            if key in seen_records:
                continue

            seen_records.add(
                key
            )

            all_records.append(
                record
            )

    logger.info(
        "============================================"
    )

    logger.info(
        "COLLECTION FINISHED"
    )

    logger.info(
        "Countries discovered: %d",
        total
    )

    logger.info(
        "Successful countries: %d",
        successful
    )

    logger.info(
        "Failed countries: %d",
        failed
    )

    logger.info(
        "Unique records: %d",
        len(all_records)
    )

    logger.info(
        "============================================"
    )

    return all_records


# ============================================================
# VALIDATION
# ============================================================

def validate_records(
    records
):

    if not records:

        raise RuntimeError(
            "NO RECORDS WERE COLLECTED."
        )

    countries = {
        record[
            "country"
        ]
        for record in records
        if record.get(
            "country"
        )
    }

    services = {
        record[
            "service"
        ]
        for record in records
        if record.get(
            "service"
        )
    }

    logger.info(
        "Validation:"
    )

    logger.info(
        "  Records: %d",
        len(records)
    )

    logger.info(
        "  Countries: %d",
        len(countries)
    )

    logger.info(
        "  Services: %d",
        len(services)
    )

    if len(records) < EXPECTED_MIN_RECORDS:

        logger.warning(
            "WARNING: only %d records collected.",
            len(records)
        )

        logger.warning(
            "The ITU page currently reports "
            "approximately 1160 records."
        )

    else:

        logger.info(
            "Record count looks reasonable."
        )


# ============================================================
# SAVE JSON
# ============================================================

def save_json(
    records
):

    data = {
        "dataset": (
            "ITU-T E.129 Important Numbers"
        ),

        "source": BASE_URL,

        "retrieved_at": utc_now(),

        "record_count": len(
            records
        ),

        "records": records
    }

    with OUTPUT_JSON.open(
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

    logger.info(
        "JSON saved: %s",
        OUTPUT_JSON
    )


# ============================================================
# SAVE CSV
# ============================================================

def save_csv(
    records
):

    fieldnames = [
        "country",
        "number",
        "service",
        "additional_information",
        "allocated_or_assigned",
        "note",
        "last_update",
        "source",
        "retrieved_at"
    ]

    with OUTPUT_CSV.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore"
        )

        writer.writeheader()

        for record in records:

            writer.writerow(
                record
            )

    logger.info(
        "CSV saved: %s",
        OUTPUT_CSV
    )


# ============================================================
# SAVE TXT
# ============================================================

def save_txt(
    records
):

    grouped = defaultdict(
        list
    )

    for record in records:

        country = (
            record.get(
                "country",
                ""
            )
            or "Unknown"
        )

        grouped[
            country
        ].append(
            record
        )

    countries = sorted(
        grouped.keys(),
        key=str.casefold
    )

    with OUTPUT_TXT.open(
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "GLOBAL EMERGENCY AND IMPORTANT SERVICE NUMBERS\n"
        )

        f.write(
            "====================================================\n\n"
        )

        f.write(
            "Source: ITU-T E.129 Important Numbers\n"
        )

        f.write(
            f"Retrieved: {utc_now()}\n"
        )

        f.write(
            f"Total records: {len(records)}\n"
        )

        f.write(
            f"Countries/geographical areas: "
            f"{len(countries)}\n\n"
        )

        f.write(
            "IMPORTANT:\n"
        )

        f.write(
            "- A country may have multiple numbers.\n"
        )

        f.write(
            "- Do not assume one number covers every emergency service.\n"
        )

        f.write(
            "- This dataset is based on ITU E.129 information.\n"
        )

        f.write(
            "- Verify current local information when possible.\n\n"
        )

        for country in countries:

            f.write(
                "\n"
            )

            f.write(
                "=" * 70
                + "\n"
            )

            f.write(
                country
                + "\n"
            )

            f.write(
                "=" * 70
                + "\n"
            )

            country_records = sorted(
                grouped[
                    country
                ],
                key=lambda record: (
                    record.get(
                        "service",
                        ""
                    ).casefold(),

                    record.get(
                        "number",
                        ""
                    )
                )
            )

            for record in country_records:

                f.write(
                    "\n"
                )

                f.write(
                    "Service: "
                    + (
                        record.get(
                            "service",
                            ""
                        )
                        or "Not specified"
                    )
                    + "\n"
                )

                f.write(
                    "Number: "
                    + record.get(
                        "number",
                        ""
                    )
                    + "\n"
                )

                if record.get(
                    "additional_information"
                ):

                    f.write(
                        "Additional information: "
                        + record[
                            "additional_information"
                        ]
                        + "\n"
                    )

                if record.get(
                    "allocated_or_assigned"
                ):

                    f.write(
                        "Allocated/assigned: "
                        + record[
                            "allocated_or_assigned"
                        ]
                        + "\n"
                    )

                if record.get(
                    "note"
                ):

                    f.write(
                        "Note: "
                        + record[
                            "note"
                        ]
                        + "\n"
                    )

                if record.get(
                    "last_update"
                ):

                    f.write(
                        "Last update: "
                        + record[
                            "last_update"
                        ]
                        + "\n"
                    )

                f.write(
                    "Source: "
                    + record.get(
                        "source",
                        ""
                    )
                    + "\n"
                )

    logger.info(
        "TXT saved: %s",
        OUTPUT_TXT
    )


# ============================================================
# MAIN
# ============================================================

def main():

    logger.info(
        "=============================================="
    )

    logger.info(
        "ITU-T E.129 EMERGENCY NUMBER COLLECTOR"
    )

    logger.info(
        "=============================================="
    )

    try:

        records = collect_all_records()

        validate_records(
            records
        )

        save_json(
            records
        )

        save_csv(
            records
        )

        save_txt(
            records
        )

        print()
        print(
            "=============================================="
        )

        print(
            "COLLECTION COMPLETE"
        )

        print(
            "=============================================="
        )

        print(
            f"Records: {len(records)}"
        )

        print(
            f"TXT : {OUTPUT_TXT}"
        )

        print(
            f"CSV : {OUTPUT_CSV}"
        )

        print(
            f"JSON: {OUTPUT_JSON}"
        )

    except Exception as exc:

        logger.exception(
            "COLLECTION FAILED: %s",
            exc
        )

        save_error(
            f"COLLECTION FAILED: {exc}"
        )

        raise


if __name__ == "__main__":
    main()  