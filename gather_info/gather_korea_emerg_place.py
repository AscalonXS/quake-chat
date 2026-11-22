"""
KOREA EMERGENCY PLACES COLLECTOR
================================

Collects Korea location-dependent emergency/safety facilities:

1. Earthquake outdoor evacuation shelters
2. Hospitals / medical facilities
3. Pharmacies

Output:
    docs/05_korea_emergency_places.txt

Errors:
    docs/05_korea_emergency_places_errors.txt

Cache:
    cache/korea_places/

SERVER-FRIENDLY DESIGN
----------------------
- One request at a time
- 7-second delay between successful requests
- Maximum 2 retries
- NEVER retries HTTP 401 / 403 / 404
- Uses local cache whenever possible
- Does not repeatedly download already-cached pages
- Uses a reasonably large page size
- Stops when the API stops returning records

REQUIRED ENVIRONMENT VARIABLES
------------------------------
MOIS_SERVICE_KEY
HIRA_SERVICE_KEY

Windows CMD:
    set MOIS_SERVICE_KEY=YOUR_KEY
    set HIRA_SERVICE_KEY=YOUR_KEY

PowerShell:
    $env:MOIS_SERVICE_KEY="YOUR_KEY"
    $env:HIRA_SERVICE_KEY="YOUR_KEY"

Run:
    python gather_korea_emergency_places.py
"""

# ============================================================
# IMPORTS
# ============================================================

import json
import logging
import math
import os
import re
import time

from datetime import datetime, timezone
from pathlib import Path

import requests


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DOCS_DIR = PROJECT_ROOT / "docs"
CACHE_DIR = PROJECT_ROOT / "cache" / "korea_places"

DOCS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_TXT = DOCS_DIR / "05_korea_emergency_places.txt"
ERROR_LOG = DOCS_DIR / "05_korea_emergency_places_errors.txt"


# ============================================================
# API ENDPOINTS
# ============================================================

MOIS_ENDPOINT = (
    "https://apis.data.go.kr/"
    "1741000/EarthquakeShelter3/"
    "getEarthquakeShelter1List"
)

HIRA_HOSPITAL_ENDPOINT = (
    "https://apis.data.go.kr/"
    "B551182/hospInfoServicev2/"
    "getHospBasisList"
)

HIRA_PHARMACY_ENDPOINT = (
    "https://apis.data.go.kr/"
    "B551182/pharmacyInfoService/"
    "getParmacyBasisList"
)


# ============================================================
# SERVER-FRIENDLY SETTINGS
# ============================================================

# Large enough to reduce the number of requests.
PAGE_SIZE = 1000

# Be deliberately polite to the APIs.
REQUEST_DELAY = 7.0

# Only a very small number of retries.
MAX_RETRIES = 2

# Connection timeout, read timeout.
TIMEOUT = (20, 120)

# Retry only temporary conditions.
RETRY_STATUS_CODES = {
    408,
    425,
    429,
    500,
    502,
    503,
    504,
}

# Stop after this many consecutive empty pages.
MAX_EMPTY_PAGES = 2

# Set True only when you intentionally want to refresh
# existing cached API responses.
FORCE_REFRESH = False


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("korea-emergency-places")


# ============================================================
# HTTP SESSION
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/157.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "application/json,"
        "application/xml,"
        "text/xml,"
        "text/plain,"
        "*/*"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
})


# ============================================================
# GENERAL HELPERS
# ============================================================

def utc_now():
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def clean_text(value):
    """Convert a value into clean text."""
    if value is None:
        return ""

    text = str(value)

    text = (
        text.replace("\r", " ")
        .replace("\n", " ")
        .replace("\t", " ")
    )

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_key(value):
    """
    Normalize field names so Korean/English API field
    variations are easier to compare.
    """
    text = clean_text(value).lower()

    text = re.sub(
        r"[^0-9a-z가-힣]+",
        "",
        text
    )

    return text


def parse_float(value):
    """Safely convert a value to float."""
    if value is None:
        return None

    text = clean_text(value)

    if not text:
        return None

    text = text.replace(",", "")

    try:
        return float(text)
    except ValueError:
        return None


def first_value(record, *possible_keys):
    """
    Return the first non-empty value from a record.

    Handles Korean and English field names.
    """

    if not isinstance(record, dict):
        return ""

    normalized_record = {}

    for key, value in record.items():
        normalized_record[normalize_key(key)] = value

    for key in possible_keys:
        normalized = normalize_key(key)

        if normalized in normalized_record:
            value = normalized_record[normalized]

            if value is not None and clean_text(value):
                return clean_text(value)

    return ""


def save_error(message):
    """Append an error to the error log."""

    timestamp = utc_now()

    with ERROR_LOG.open(
        "a",
        encoding="utf-8"
    ) as f:

        f.write("\n")
        f.write("=" * 80)
        f.write("\n")
        f.write(timestamp)
        f.write("\n")
        f.write(message)
        f.write("\n")


# ============================================================
# CACHE
# ============================================================

def cache_path(prefix, page):
    """
    Return cache filename for a specific API/page.
    """

    safe_prefix = re.sub(
        r"[^A-Za-z0-9_-]",
        "_",
        prefix
    )

    return CACHE_DIR / f"{safe_prefix}_page_{page}.json"


def load_cache(path):
    """Load JSON cache if available."""

    if not path.exists():
        return None

    try:

        with path.open(
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception as exc:

        logger.warning(
            "Could not read cache %s: %s",
            path,
            exc
        )

        return None


def save_cache(path, data):
    """Save API response to cache."""

    try:

        with path.open(
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
            "Saved cache: %s",
            path
        )

    except Exception as exc:

        logger.warning(
            "Could not save cache %s: %s",
            path,
            exc
        )


# ============================================================
# API RESPONSE INSPECTION
# ============================================================

def inspect_api_response(data):
    """
    Look for common data.go.kr API error structures.
    """

    if not isinstance(data, dict):
        return

    text = json.dumps(
        data,
        ensure_ascii=False
    ).lower()

    error_words = [
        "servicekey",
        "service key",
        "invalid",
        "unauthorized",
        "forbidden",
        "errorcode",
        "errormsg",
        "fail",
    ]

    found = [
        word
        for word in error_words
        if word in text
    ]

    if found:
        logger.warning(
            "API response may contain an error: %s",
            ", ".join(found)
        )


# ============================================================
# EXTRACT RECORDS
# ============================================================

def extract_records(data):
    """
    Recursively search a JSON response for the largest list
    containing dictionary records.

    This makes the parser tolerant of different data.go.kr
    response wrappers.
    """

    candidates = []

    def walk(value):

        if isinstance(value, list):

            dict_items = [
                item
                for item in value
                if isinstance(item, dict)
            ]

            if dict_items:
                candidates.append(dict_items)

            for item in value:
                walk(item)

        elif isinstance(value, dict):

            for child in value.values():
                walk(child)

    walk(data)

    if not candidates:
        return []

    candidates.sort(
        key=len,
        reverse=True
    )

    return candidates[0]


# ============================================================
# FETCH JSON
# ============================================================

def fetch_json(
    url,
    params,
    cache_file=None,
):
    """
    Server-friendly JSON GET.

    Important:
    HTTP 403 is NOT retried.
    """

    if (
        cache_file
        and cache_file.exists()
        and not FORCE_REFRESH
    ):

        logger.info(
            "Using cached response: %s",
            cache_file
        )

        return load_cache(cache_file)

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        try:

            logger.info(
                "Requesting: %s | attempt %d/%d",
                url,
                attempt,
                MAX_RETRIES
            )

            response = session.get(
                url,
                params=params,
                timeout=TIMEOUT,
            )

            status = response.status_code

            # ------------------------------------------------
            # SUCCESS
            # ------------------------------------------------

            if status == 200:

                # Be kind to the server.
                time.sleep(REQUEST_DELAY)

                try:

                    data = response.json()

                except ValueError:

                    message = (
                        "HTTP 200 but response is not valid JSON.\n"
                        f"URL: {response.url}\n"
                        f"Response:\n{response.text[:3000]}"
                    )

                    logger.error(message)
                    save_error(message)

                    return None

                inspect_api_response(data)

                if cache_file:
                    save_cache(
                        cache_file,
                        data
                    )

                return data

            # ------------------------------------------------
            # DO NOT RETRY 401
            # ------------------------------------------------

            if status == 401:

                message = (
                    "HTTP 401 Unauthorized.\n"
                    f"URL: {response.url}\n"
                    f"Response:\n{response.text[:3000]}"
                )

                logger.error(message)
                save_error(message)

                return None

            # ------------------------------------------------
            # DO NOT RETRY 403
            # ------------------------------------------------

            if status == 403:

                message = (
                    "HTTP 403 Forbidden.\n"
                    "The server rejected the request.\n"
                    "The collector will NOT retry this request.\n"
                    f"URL: {response.url}\n"
                    f"Response:\n{response.text[:3000]}"
                )

                logger.error(message)
                save_error(message)

                return None

            # ------------------------------------------------
            # DO NOT RETRY 404
            # ------------------------------------------------

            if status == 404:

                message = (
                    "HTTP 404 Not Found.\n"
                    f"URL: {response.url}\n"
                    f"Response:\n{response.text[:3000]}"
                )

                logger.error(message)
                save_error(message)

                return None

            # ------------------------------------------------
            # TEMPORARY ERROR
            # ------------------------------------------------

            if status in RETRY_STATUS_CODES:

                logger.warning(
                    "HTTP %d received.",
                    status
                )

                save_error(
                    f"HTTP {status}\n"
                    f"URL: {response.url}\n"
                    f"Response:\n{response.text[:2000]}"
                )

                if attempt < MAX_RETRIES:

                    wait_time = 15 * attempt

                    logger.info(
                        "Waiting %d seconds before retry.",
                        wait_time
                    )

                    time.sleep(wait_time)

                    continue

                return None

            # ------------------------------------------------
            # OTHER ERROR
            # ------------------------------------------------

            message = (
                f"Unexpected HTTP {status}.\n"
                f"URL: {response.url}\n"
                f"Response:\n{response.text[:3000]}"
            )

            logger.error(message)
            save_error(message)

            return None

        except requests.Timeout as exc:

            logger.warning(
                "Request timed out: %s",
                exc
            )

            if attempt < MAX_RETRIES:

                wait_time = 15 * attempt

                logger.info(
                    "Waiting %d seconds before retry.",
                    wait_time
                )

                time.sleep(wait_time)

                continue

            save_error(
                f"Request timeout\n"
                f"URL: {url}\n"
                f"Error: {exc}"
            )

            return None

        except requests.RequestException as exc:

            logger.warning(
                "Request failed: %s",
                exc
            )

            if attempt < MAX_RETRIES:

                wait_time = 15 * attempt

                logger.info(
                    "Waiting %d seconds before retry.",
                    wait_time
                )

                time.sleep(wait_time)

                continue

            save_error(
                f"Request exception\n"
                f"URL: {url}\n"
                f"Error: {exc}"
            )

            return None

    return None


# ============================================================
# COLLECT PAGINATED API
# ============================================================

def collect_api(
    prefix,
    endpoint,
    service_key,
    extra_params=None,
):
    """
    Collect all pages from an API.

    Requests are strictly sequential.
    """

    records = []

    if not service_key:

        logger.error(
            "%s service key is missing.",
            prefix
        )

        save_error(
            f"{prefix}: service key is missing."
        )

        return records

    page = 1
    empty_pages = 0

    while True:

        cache_file = cache_path(
            prefix,
            page
        )

        params = {
            "serviceKey": service_key,
            "pageNo": page,
            "numOfRows": PAGE_SIZE,
            "type": "json",
        }

        if extra_params:
            params.update(extra_params)

        data = fetch_json(
            endpoint,
            params,
            cache_file
        )

        if data is None:

            logger.error(
                "%s: stopping at page %d.",
                prefix,
                page
            )

            break

        page_records = extract_records(data)

        logger.info(
            "%s: page %d -> %d records",
            prefix,
            page,
            len(page_records)
        )

        if not page_records:

            empty_pages += 1

            if empty_pages >= MAX_EMPTY_PAGES:

                logger.info(
                    "%s: reached end of data.",
                    prefix
                )

                break

        else:

            empty_pages = 0
            records.extend(page_records)

        # If a full page was not returned, this is almost
        # certainly the last page.
        if (
            page_records
            and len(page_records) < PAGE_SIZE
        ):

            logger.info(
                "%s: final page reached.",
                prefix
            )

            break

        page += 1

    logger.info(
        "%s: collected %d raw records.",
        prefix,
        len(records)
    )

    return records


# ============================================================
# SHELTERS
# ============================================================

def parse_shelter(record):
    """Convert a raw shelter API record into our standard format."""

    name = first_value(
        record,
        "시설명",
        "대피소명",
        "지진옥외대피장소명",
        "shelterName",
        "facilityName",
        "name",
    )

    address = first_value(
        record,
        "주소",
        "소재지",
        "도로명주소",
        "address",
    )

    road_address = first_value(
        record,
        "도로명주소",
        "roadAddress",
    )

    jibun_address = first_value(
        record,
        "지번주소",
        "jibunAddress",
    )

    latitude = parse_float(
        first_value(
            record,
            "위도",
            "latitude",
            "lat",
        )
    )

    longitude = parse_float(
        first_value(
            record,
            "경도",
            "longitude",
            "lon",
            "lng",
        )
    )

    phone = first_value(
        record,
        "전화번호",
        "연락처",
        "phone",
    )

    capacity = first_value(
        record,
        "수용가능인원",
        "수용인원",
        "capacity",
    )

    area = first_value(
        record,
        "수용가능면적",
        "면적",
        "area",
    )

    facility_type = first_value(
        record,
        "시설구분명",
        "시설구분",
        "facilityType",
    )

    if not name and not address:
        return None

    return {
        "type": "earthquake_shelter",
        "category": "shelter",
        "name": name,
        "address": address,
        "road_address": road_address,
        "jibun_address": jibun_address,
        "latitude": latitude,
        "longitude": longitude,
        "phone": phone,
        "capacity": capacity,
        "area": area,
        "facility_type": facility_type,
        "source": MOIS_ENDPOINT,
        "source_type": (
            "Ministry of the Interior and Safety "
            "public data"
        ),
        "retrieved_at": utc_now(),
    }


# ============================================================
# HOSPITALS
# ============================================================

def parse_hospital(record):
    """Convert hospital API record into standard format."""

    name = first_value(
        record,
        "yadmNm",
        "요양기관명",
        "병원명",
        "기관명",
        "name",
    )

    address = first_value(
        record,
        "addr",
        "주소",
        "소재지",
        "address",
    )

    phone = first_value(
        record,
        "telno",
        "전화번호",
        "연락처",
        "phone",
    )

    latitude = parse_float(
        first_value(
            record,
            "YPos",
            "위도",
            "latitude",
            "lat",
        )
    )

    longitude = parse_float(
        first_value(
            record,
            "XPos",
            "경도",
            "longitude",
            "lon",
            "lng",
        )
    )

    hospital_type = first_value(
        record,
        "clCdNm",
        "종별코드명",
        "기관종별",
        "hospitalType",
    )

    homepage = first_value(
        record,
        "hospUrl",
        "홈페이지",
        "homepage",
        "url",
    )

    if not name and not address:
        return None

    return {
        "type": "hospital",
        "category": "medical",
        "name": name,
        "address": address,
        "road_address": "",
        "jibun_address": "",
        "latitude": latitude,
        "longitude": longitude,
        "phone": phone,
        "capacity": "",
        "area": "",
        "facility_type": hospital_type,
        "homepage": homepage,
        "source": HIRA_HOSPITAL_ENDPOINT,
        "source_type": (
            "Health Insurance Review & "
            "Assessment Service public data"
        ),
        "retrieved_at": utc_now(),
    }


# ============================================================
# PHARMACIES
# ============================================================

def parse_pharmacy(record):
    """Convert pharmacy API record into standard format."""

    name = first_value(
        record,
        "yadmNm",
        "요양기관명",
        "약국명",
        "기관명",
        "name",
    )

    address = first_value(
        record,
        "addr",
        "주소",
        "소재지",
        "address",
    )

    phone = first_value(
        record,
        "telno",
        "전화번호",
        "연락처",
        "phone",
    )

    latitude = parse_float(
        first_value(
            record,
            "YPos",
            "위도",
            "latitude",
            "lat",
        )
    )

    longitude = parse_float(
        first_value(
            record,
            "XPos",
            "경도",
            "longitude",
            "lon",
            "lng",
        )
    )

    homepage = first_value(
        record,
        "hospUrl",
        "홈페이지",
        "homepage",
        "url",
    )

    if not name and not address:
        return None

    return {
        "type": "pharmacy",
        "category": "pharmacy",
        "name": name,
        "address": address,
        "road_address": "",
        "jibun_address": "",
        "latitude": latitude,
        "longitude": longitude,
        "phone": phone,
        "capacity": "",
        "area": "",
        "facility_type": "",
        "homepage": homepage,
        "source": HIRA_PHARMACY_ENDPOINT,
        "source_type": (
            "Health Insurance Review & "
            "Assessment Service public data"
        ),
        "retrieved_at": utc_now(),
    }


# ============================================================
# DEDUPLICATION
# ============================================================

def deduplicate(records):
    """Remove duplicate facilities."""

    unique = []
    seen = set()

    for record in records:

        key = (
            record.get("type", ""),
            clean_text(
                record.get("name", "")
            ).lower(),

            clean_text(
                record.get("address", "")
            ).lower(),

            record.get("latitude"),
            record.get("longitude"),
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(record)

    logger.info(
        "Deduplication: %d -> %d records",
        len(records),
        len(unique)
    )

    return unique


# ============================================================
# HAVERSINE DISTANCE
# ============================================================

def haversine_km(
    lat1,
    lon1,
    lat2,
    lon2,
):
    """
    Calculate straight-line geographic distance.

    This is NOT walking/driving distance.
    """

    if (
        lat1 is None
        or lon1 is None
        or lat2 is None
        or lon2 is None
    ):
        return None

    radius = 6371.0088

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    delta_lat = math.radians(
        lat2 - lat1
    )

    delta_lon = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(delta_lat / 2) ** 2
        +
        math.cos(lat1)
        *
        math.cos(lat2)
        *
        math.sin(delta_lon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return radius * c


# ============================================================
# NEAREST FACILITIES
# ============================================================

def find_nearest_places(
    records,
    user_latitude,
    user_longitude,
    category=None,
    limit=5,
):
    """
    Return nearest facilities.

    This function is intentionally deterministic.
    The LLM should NOT calculate distances itself.
    """

    results = []

    for record in records:

        if (
            category
            and record.get("category") != category
        ):
            continue

        distance = haversine_km(
            user_latitude,
            user_longitude,
            record.get("latitude"),
            record.get("longitude"),
        )

        if distance is None:
            continue

        item = dict(record)

        item["distance_km"] = round(
            distance,
            3
        )

        results.append(item)

    results.sort(
        key=lambda x: x["distance_km"]
    )

    return results[:limit]


# ============================================================
# VALIDATION
# ============================================================

def validate_records(records):
    """
    Remove records with insufficient identifying information.
    """

    valid = []

    for record in records:

        name = clean_text(
            record.get("name", "")
        )

        address = clean_text(
            record.get("address", "")
        )

        if not name and not address:
            continue

        valid.append(record)

    return valid


# ============================================================
# TXT OUTPUT HELPERS
# ============================================================

def write_field(
    f,
    label,
    value,
):
    """Write one field if it has a useful value."""

    value = clean_text(value)

    if value:
        f.write(
            f"{label}: {value}\n"
        )


def write_record(
    f,
    number,
    record,
):
    """Write one facility."""

    f.write(f"[{number}]\n")

    write_field(
        f,
        "Type",
        record.get("type")
    )

    write_field(
        f,
        "Category",
        record.get("category")
    )

    write_field(
        f,
        "Name",
        record.get("name")
    )

    write_field(
        f,
        "Address",
        record.get("address")
    )

    write_field(
        f,
        "Road Address",
        record.get("road_address")
    )

    write_field(
        f,
        "Jibun Address",
        record.get("jibun_address")
    )

    write_field(
        f,
        "Latitude",
        record.get("latitude")
    )

    write_field(
        f,
        "Longitude",
        record.get("longitude")
    )

    write_field(
        f,
        "Phone",
        record.get("phone")
    )

    write_field(
        f,
        "Capacity",
        record.get("capacity")
    )

    write_field(
        f,
        "Area",
        record.get("area")
    )

    write_field(
        f,
        "Facility Type",
        record.get("facility_type")
    )

    write_field(
        f,
        "Homepage",
        record.get("homepage")
    )

    write_field(
        f,
        "Source",
        record.get("source")
    )

    write_field(
        f,
        "Source Type",
        record.get("source_type")
    )

    write_field(
        f,
        "Retrieved At",
        record.get("retrieved_at")
    )

    f.write("\n")


# ============================================================
# SAVE TXT
# ============================================================

def save_txt(records):
    """Write the final TXT knowledge file."""

    shelters = [
        r for r in records
        if r.get("type") == "earthquake_shelter"
    ]

    hospitals = [
        r for r in records
        if r.get("type") == "hospital"
    ]

    pharmacies = [
        r for r in records
        if r.get("type") == "pharmacy"
    ]

    with OUTPUT_TXT.open(
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "KOREA EMERGENCY / SAFETY PLACES\n"
        )

        f.write(
            "================================\n\n"
        )

        f.write(
            f"Retrieved: {utc_now()}\n"
        )

        f.write(
            f"Total records: {len(records)}\n"
        )

        f.write(
            f"Shelters: {len(shelters)}\n"
        )

        f.write(
            f"Hospitals / medical facilities: "
            f"{len(hospitals)}\n"
        )

        f.write(
            f"Pharmacies: {len(pharmacies)}\n"
        )

        f.write("\n")

        f.write("PURPOSE\n")
        f.write("=======\n")

        f.write(
            "This file contains Korea location-dependent "
            "facilities for the Earthquake Helper chatbot.\n"
        )

        f.write(
            "The chatbot should use latitude/longitude "
            "to calculate the nearest suitable facility.\n"
        )

        f.write("\n")

        f.write("IMPORTANT SAFETY NOTES\n")
        f.write("======================\n")

        f.write(
            "- Geographic distance is not walking or "
            "driving distance.\n"
        )

        f.write(
            "- A hospital listing does not guarantee that "
            "an emergency department is currently operating.\n"
        )

        f.write(
            "- A listed facility may be damaged, closed, "
            "full, inaccessible, or otherwise unavailable "
            "after an earthquake.\n"
        )

        f.write(
            "- Current operating status should be verified "
            "when possible.\n"
        )

        f.write(
            "- Never invent a facility that is not in the data.\n"
        )

        f.write(
            "- If no suitable facility is available in the "
            "dataset, say that no suitable facility was found.\n"
        )

        f.write("\n")

        # ----------------------------------------------------
        # SHELTERS
        # ----------------------------------------------------

        f.write(
            "EARTHQUAKE OUTDOOR SHELTERS\n"
        )

        f.write(
            "===========================\n\n"
        )

        if shelters:

            for i, record in enumerate(
                shelters,
                start=1
            ):

                write_record(
                    f,
                    i,
                    record
                )

        else:

            f.write(
                "No earthquake shelter records were collected.\n\n"
            )

        # ----------------------------------------------------
        # HOSPITALS
        # ----------------------------------------------------

        f.write(
            "HOSPITALS / MEDICAL FACILITIES\n"
        )

        f.write(
            "==============================\n\n"
        )

        if hospitals:

            for i, record in enumerate(
                hospitals,
                start=1
            ):

                write_record(
                    f,
                    i,
                    record
                )

        else:

            f.write(
                "No hospital records were collected.\n\n"
            )

        # ----------------------------------------------------
        # PHARMACIES
        # ----------------------------------------------------

        f.write(
            "PHARMACIES\n"
        )

        f.write(
            "==========\n\n"
        )

        if pharmacies:

            for i, record in enumerate(
                pharmacies,
                start=1
            ):

                write_record(
                    f,
                    i,
                    record
                )

        else:

            f.write(
                "No pharmacy records were collected.\n\n"
            )

    logger.info(
        "TXT written: %s",
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
        "Korea Emergency Places Collector"
    )

    logger.info(
        "=============================================="
    )

    logger.info(
        "Output: %s",
        OUTPUT_TXT
    )

    logger.info(
        "Cache: %s",
        CACHE_DIR
    )

    logger.info(
        "Server delay: %.1f seconds",
        REQUEST_DELAY
    )

    # --------------------------------------------------------
    # LOAD API KEYS
    # --------------------------------------------------------

    mois_key = os.getenv(
        "MOIS_SERVICE_KEY"
    )

    hira_key = os.getenv(
        "HIRA_SERVICE_KEY"
    )

    if not mois_key:

        logger.error(
            "MOIS_SERVICE_KEY is not set."
        )

        save_error(
            "MOIS_SERVICE_KEY is not set."
        )

    if not hira_key:

        logger.error(
            "HIRA_SERVICE_KEY is not set."
        )

        save_error(
            "HIRA_SERVICE_KEY is not set."
        )

    all_records = []

    # --------------------------------------------------------
    # 1. EARTHQUAKE SHELTERS
    # --------------------------------------------------------

    if mois_key:

        logger.info(
            ""
        )

        logger.info(
            "Collecting earthquake shelters..."
        )

        raw_shelters = collect_api(
            prefix="MOIS_shelters",
            endpoint=MOIS_ENDPOINT,
            service_key=mois_key,
        )

        logger.info(
            "Parsing %d shelter records...",
            len(raw_shelters)
        )

        for raw in raw_shelters:

            record = parse_shelter(raw)

            if record:
                all_records.append(record)

    else:

        logger.warning(
            "Skipping shelter collection."
        )

    # --------------------------------------------------------
    # 2. HOSPITALS
    # --------------------------------------------------------

    if hira_key:

        logger.info(
            ""
        )

        logger.info(
            "Collecting hospitals..."
        )

        raw_hospitals = collect_api(
            prefix="HIRA_hospitals",
            endpoint=HIRA_HOSPITAL_ENDPOINT,
            service_key=hira_key,
        )

        logger.info(
            "Parsing %d hospital records...",
            len(raw_hospitals)
        )

        for raw in raw_hospitals:

            record = parse_hospital(raw)

            if record:
                all_records.append(record)

    else:

        logger.warning(
            "Skipping hospital collection."
        )

    # --------------------------------------------------------
    # 3. PHARMACIES
    # --------------------------------------------------------

    if hira_key:

        logger.info(
            ""
        )

        logger.info(
            "Collecting pharmacies..."
        )

        raw_pharmacies = collect_api(
            prefix="HIRA_pharmacies",
            endpoint=HIRA_PHARMACY_ENDPOINT,
            service_key=hira_key,
        )

        logger.info(
            "Parsing %d pharmacy records...",
            len(raw_pharmacies)
        )

        for raw in raw_pharmacies:

            record = parse_pharmacy(raw)

            if record:
                all_records.append(record)

    else:

        logger.warning(
            "Skipping pharmacy collection."
        )

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    logger.info(
        ""
    )

    logger.info(
        "Validating records..."
    )

    all_records = validate_records(
        all_records
    )

    # --------------------------------------------------------
    # DEDUPLICATION
    # --------------------------------------------------------

    all_records = deduplicate(
        all_records
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    save_txt(
        all_records
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    shelters = sum(
        1
        for r in all_records
        if r.get("type") == "earthquake_shelter"
    )

    hospitals = sum(
        1
        for r in all_records
        if r.get("type") == "hospital"
    )

    pharmacies = sum(
        1
        for r in all_records
        if r.get("type") == "pharmacy"
    )

    logger.info(
        ""
    )

    logger.info(
        "=============================================="
    )

    logger.info(
        "COLLECTION COMPLETE"
    )

    logger.info(
        "=============================================="
    )

    logger.info(
        "Total: %d",
        len(all_records)
    )

    logger.info(
        "Shelters: %d",
        shelters
    )

    logger.info(
        "Hospitals: %d",
        hospitals
    )

    logger.info(
        "Pharmacies: %d",
        pharmacies
    )

    logger.info(
        "TXT: %s",
        OUTPUT_TXT
    )

    logger.info(
        "Errors: %s",
        ERROR_LOG
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()