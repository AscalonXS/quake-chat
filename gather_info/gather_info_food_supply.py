"""
===============================================================
EARTHQUAKE HELPER
TOPIC 10 — FOOD AND WATER SUPPLY
===============================================================

Purpose
-------
Collect authoritative information for a RAG knowledge base covering:

    - Emergency drinking water
    - Water storage
    - Water treatment
    - Water contamination
    - Food safety
    - Power outages
    - Flood contamination
    - Emergency food supplies
    - Special dietary needs
    - Food/water during evacuation
    - Post-disaster sanitation

IMPORTANT
---------
This collector gathers relatively static safety guidance.

It does NOT determine whether water is currently safe in a
specific location.

Current information such as:

    - boil-water advisories
    - water contamination
    - water distribution points
    - emergency food distribution
    - shelter supplies
    - local utility outages

must come from current official/local sources.

===============================================================
"""

from __future__ import annotations

import hashlib
import io
import logging
import random
import re
import time

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

try:
    from ddgs import DDGS
except ImportError:
    DDGS = None

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DOCS_DIR = BASE_DIR / "docs"
CACHE_DIR = BASE_DIR / "cache" / "topic_10_food_water"

DOCS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

CACHE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# CONFIGURATION
# ============================================================

MAX_SEARCH_RESULTS = 6
MAX_SOURCES_PER_SECTION = 6

MAX_TEXT_CHARS_PER_SOURCE = 30000

MAX_RETRIES = 5

CONNECT_TIMEOUT = 20
READ_TIMEOUT = 120

MIN_DELAY = 2.5
MAX_DELAY = 6.0

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
}


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("topic10_food_water")


# ============================================================
# HTTP SESSION
# ============================================================

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# DATA STRUCTURE
# ============================================================

@dataclass
class Source:
    subsection: str
    title: str
    url: str
    domain: str
    source_type: str
    authority_score: int
    search_snippet: str
    retrieved_at: str
    content: str


# ============================================================
# TOPIC STRUCTURE
# ============================================================

RESEARCH_SECTIONS = [

    (
        "10.01 Drinking Water Priorities",
        [
            "emergency drinking water earthquake",
            "disaster drinking water emergency official",
            "WHO emergency drinking water disaster",
        ],
    ),

    (
        "10.02 Emergency Water Storage",
        [
            "emergency water storage disaster",
            "store drinking water emergency FEMA",
            "emergency water supply CDC",
        ],
    ),

    (
        "10.03 Minimum Water Needs",
        [
            "emergency water amount per person disaster",
            "drinking water emergency supply amount",
            "FEMA emergency water one gallon per person",
        ],
    ),

    (
        "10.04 Water for Drinking Food and Hygiene",
        [
            "emergency water drinking cooking hygiene",
            "disaster water drinking cooking sanitation",
        ],
    ),

    (
        "10.05 Safe Water Sources",
        [
            "safe emergency water sources disaster",
            "emergency water sources CDC",
            "disaster safe water sources FEMA",
        ],
    ),

    (
        "10.06 Unsafe Water Sources",
        [
            "unsafe water sources disaster",
            "emergency water unsafe sources CDC",
            "earthquake contaminated water safety",
        ],
    ),

    (
        "10.07 Boil Water Guidance",
        [
            "boil water advisory CDC",
            "boiling water emergency disaster",
            "safe drinking water boil advisory",
        ],
    ),

    (
        "10.08 Water Disinfection",
        [
            "emergency water disinfection CDC",
            "disinfect drinking water disaster",
            "household water treatment WHO emergency",
        ],
    ),

    (
        "10.09 Chemical Contamination",
        [
            "chemical contamination drinking water disaster",
            "water contaminated chemicals emergency",
            "CDC chemical contamination drinking water",
        ],
    ),

    (
        "10.10 Fuel and Chemical Exposure",
        [
            "drinking water fuel contamination disaster",
            "water contaminated fuel chemicals emergency",
            "earthquake water chemical contamination",
        ],
    ),

    (
        "10.11 Floodwater",
        [
            "floodwater drinking water unsafe CDC",
            "flood contaminated water food safety",
            "disaster floodwater contamination",
        ],
    ),

    (
        "10.12 Seawater",
        [
            "seawater drinking unsafe emergency",
            "tsunami seawater drinking water safety",
            "salt water drinking emergency",
        ],
    ),

    (
        "10.13 Rainwater",
        [
            "rainwater emergency drinking safety CDC",
            "rainwater collection drinking water emergency",
        ],
    ),

    (
        "10.14 Household Water Sources",
        [
            "water heater emergency drinking water",
            "household pipes emergency drinking water",
            "emergency water from water heater",
        ],
    ),

    (
        "10.15 Water Storage Containers",
        [
            "safe emergency water storage containers",
            "water storage food grade containers CDC",
            "emergency drinking water storage",
        ],
    ),

    (
        "10.16 Water Treatment Tablets",
        [
            "water purification tablets emergency CDC",
            "emergency water treatment tablets",
            "disaster water purification chemicals",
        ],
    ),

    (
        "10.17 Water Filters",
        [
            "emergency water filters CDC",
            "water filter disaster drinking water",
            "household water treatment filter emergency",
        ],
    ),

    (
        "10.18 Bottled Water",
        [
            "bottled water emergency disaster safety",
            "bottled water storage emergency",
            "FDA bottled water emergency",
        ],
    ),

    (
        "10.19 Water Conservation",
        [
            "water conservation disaster emergency",
            "emergency water rationing household",
            "save drinking water disaster",
        ],
    ),

    (
        "10.20 Signs of Unsafe Water",
        [
            "unsafe drinking water signs emergency",
            "contaminated water cannot tell by smell taste CDC",
            "drinking water contamination safety",
        ],
    ),

    (
        "10.21 Local Water Advisories",
        [
            "boil water advisory disaster official",
            "water advisory emergency public health",
            "drinking water emergency local authority",
        ],
    ),

    (
        "10.22 Food Safety After Earthquake",
        [
            "earthquake food safety official",
            "disaster food safety CDC",
            "FEMA food safety earthquake",
        ],
    ),

    (
        "10.23 Refrigerated Food",
        [
            "power outage refrigerator food safety USDA",
            "refrigerated food power outage safety",
            "food safety disaster refrigerator",
        ],
    ),

    (
        "10.24 Frozen Food",
        [
            "power outage frozen food safety USDA",
            "frozen food thawed emergency safety",
            "disaster freezer food safety",
        ],
    ),

    (
        "10.25 Spoiled Food",
        [
            "food spoilage emergency power outage USDA",
            "when to throw away food disaster",
            "food safety after power outage",
        ],
    ),

    (
        "10.26 Flood-Contaminated Food",
        [
            "flood contaminated food throw away USDA",
            "food exposed floodwater safety",
            "flood food contamination CDC",
        ],
    ),

    (
        "10.27 Damaged Food Packaging",
        [
            "damaged food cans earthquake safety",
            "food package damaged disaster safety",
            "USDA damaged cans emergency food",
        ],
    ),

    (
        "10.28 Food Exposed to Chemicals",
        [
            "food contaminated chemicals disaster safety",
            "food exposed to cleaning chemicals emergency",
            "chemical contamination food disaster",
        ],
    ),

    (
        "10.29 Canned and Shelf-Stable Food",
        [
            "emergency shelf stable food disaster",
            "canned food emergency preparedness",
            "FEMA emergency food supplies",
        ],
    ),

    (
        "10.30 Emergency Food Supplies",
        [
            "emergency food supply disaster preparedness",
            "food emergency kit official",
            "disaster food supplies Red Cross",
        ],
    ),

    (
        "10.31 Infant Formula",
        [
            "infant formula emergency disaster",
            "baby formula emergency water safety CDC",
            "infant feeding disaster emergency",
        ],
    ),

    (
        "10.32 Special Dietary Requirements",
        [
            "disaster food special dietary needs",
            "emergency food allergies disaster",
            "disaster preparedness dietary restrictions",
        ],
    ),

    (
        "10.33 Older Adults",
        [
            "older adults food water disaster preparedness",
            "elderly emergency food water",
            "disaster nutrition older adults",
        ],
    ),

    (
        "10.34 People With Disabilities",
        [
            "disaster food water people with disabilities",
            "emergency supplies disability food water",
            "disaster preparedness disability food",
        ],
    ),

    (
        "10.35 Pet Food and Water",
        [
            "disaster pet food water emergency",
            "earthquake pet emergency supplies",
            "FEMA pets food water disaster",
        ],
    ),

    (
        "10.36 Food and Water During Evacuation",
        [
            "evacuation food water emergency",
            "disaster evacuation food supplies",
            "emergency shelter food water",
        ],
    ),

    (
        "10.37 Food and Water During Shelter",
        [
            "emergency shelter food water disaster",
            "shelter food water public health",
            "disaster shelter nutrition water",
        ],
    ),

    (
        "10.38 Prolonged Water Outage",
        [
            "prolonged water outage emergency food water",
            "long term disaster water supply",
            "extended water outage emergency preparedness",
        ],
    ),

    (
        "10.39 Prolonged Power Outage",
        [
            "prolonged power outage food water safety",
            "long power outage food emergency USDA",
            "disaster power outage food supplies",
        ],
    ),

    (
        "10.40 Food Distribution",
        [
            "disaster emergency food distribution official",
            "emergency food distribution FEMA",
            "disaster food assistance Red Cross",
        ],
    ),

    (
        "10.41 Water Distribution",
        [
            "disaster emergency water distribution official",
            "emergency drinking water distribution disaster",
            "community water distribution emergency",
        ],
    ),

    (
        "10.42 Community Resources",
        [
            "disaster food water assistance community",
            "emergency food water resources disaster",
            "disaster assistance food water official",
        ],
    ),

    (
        "10.43 Post-Disaster Sanitation",
        [
            "disaster sanitation drinking water food safety WHO",
            "emergency sanitation food water disaster",
            "post disaster hygiene water food safety",
        ],
    ),

    (
        "10.44 Preventing Cross-Contamination",
        [
            "disaster food cross contamination safety",
            "emergency food hygiene contamination",
            "food preparation disaster sanitation",
        ],
    ),

    (
        "10.45 Food and Water During Evacuation Centers",
        [
            "evacuation center food water safety",
            "emergency evacuation center drinking water food",
            "disaster shelter food safety",
        ],
    ),
]


# ============================================================
# AUTHORITY
# ============================================================

AUTHORITY_RULES = {

    # International
    "who.int": 100,
    "fao.org": 100,
    "ifrc.org": 100,
    "icrc.org": 100,
    "unicef.org": 100,
    "un.org": 100,

    # United States
    "cdc.gov": 100,
    "fda.gov": 100,
    "usda.gov": 100,
    "foodsafety.gov": 100,
    "epa.gov": 100,
    "fema.gov": 100,
    "ready.gov": 100,
    "redcross.org": 100,

    # Korea
    "kdca.go.kr": 100,
    "korea.kr": 95,
    "gov.kr": 95,
    "safekorea.go.kr": 100,
    "kma.go.kr": 100,
    "me.go.kr": 100,

    # Japan
    "mhlw.go.jp": 100,
    "bousai.go.jp": 100,
    "jma.go.jp": 100,

    # Indonesia
    "kemkes.go.id": 100,
    "bnpb.go.id": 100,
    "pu.go.id": 100,

    # Australia
    "health.gov.au": 100,
    "foodstandards.gov.au": 100,
    "bom.gov.au": 100,

    # New Zealand
    "health.govt.nz": 100,
    "civildefence.govt.nz": 100,

    # Canada
    "canada.ca": 100,

    # Government domains
    ".gov": 90,
    ".gov.uk": 90,
    ".go.kr": 90,
    ".go.jp": 90,
    ".go.id": 90,
    ".gov.au": 90,
    ".govt.nz": 90,

    # Academic
    ".edu": 70,
    ".ac.uk": 70,
}


# ============================================================
# HELPERS
# ============================================================

def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def clean_text(text: str) -> str:

    if not text:
        return ""

    text = text.replace(
        "\xa0",
        " ",
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def sha256(value: str) -> str:

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def cache_path(url: str) -> Path:

    return (
        CACHE_DIR
        / f"{sha256(url)}.cache"
    )


def authority_score(url: str) -> int:

    hostname = (
        urlparse(url).hostname
        or ""
    ).lower()

    score = 0

    for domain, value in (
        AUTHORITY_RULES.items()
    ):

        if (
            hostname == domain
            or hostname.endswith(domain)
        ):

            score = max(
                score,
                value,
            )

    return score


def source_type(score: int) -> str:

    if score >= 100:
        return (
            "Official government / "
            "international organization"
        )

    if score >= 90:
        return "Government"

    if score >= 70:
        return "Academic / educational"

    return "Secondary / other"


def normalize_url(url: str) -> str:

    parsed = urlparse(url)

    return (
        parsed.scheme.lower()
        + "://"
        + parsed.netloc.lower()
        + parsed.path.rstrip("/")
    )


def polite_delay():

    time.sleep(
        random.uniform(
            MIN_DELAY,
            MAX_DELAY,
        )
    )


# ============================================================
# SEARCH
# ============================================================

def search_web(
    query: str,
) -> list[dict]:

    if DDGS is None:

        logger.error(
            "ddgs is not installed."
        )

        return []

    logger.info(
        "SEARCH: %s",
        query,
    )

    results = []

    try:

        with DDGS() as ddgs:

            found = ddgs.text(
                query,
                max_results=MAX_SEARCH_RESULTS,
            )

            for result in found:

                url = result.get(
                    "href",
                    "",
                )

                if not url:
                    continue

                score = authority_score(
                    url
                )

                # Food/water safety is sensitive.
                # Prefer authoritative material.
                if score < 40:
                    continue

                results.append({
                    "title": clean_text(
                        result.get(
                            "title",
                            "",
                        )
                    ),
                    "url": url,
                    "snippet": clean_text(
                        result.get(
                            "body",
                            "",
                        )
                    ),
                })

    except Exception as exc:

        logger.warning(
            "Search failed: %s",
            exc,
        )

    time.sleep(
        random.uniform(
            3.0,
            7.0,
        )
    )

    return results


# ============================================================
# DOWNLOAD
# ============================================================

def download(
    url: str,
) -> bytes | None:

    cache = cache_path(url)

    if cache.exists():

        try:

            logger.info(
                "CACHE: %s",
                url,
            )

            return cache.read_bytes()

        except Exception:
            pass

    last_error = None

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):

        try:

            logger.info(
                "GET %s "
                "(attempt %d/%d)",
                url,
                attempt,
                MAX_RETRIES,
            )

            response = session.get(
                url,
                timeout=(
                    CONNECT_TIMEOUT,
                    READ_TIMEOUT,
                ),
                allow_redirects=True,
            )

            status = response.status_code

            logger.info(
                "HTTP %d | %d bytes",
                status,
                len(response.content),
            )

            # Explicit access denial.
            if status in (
                401,
                403,
                451,
            ):

                logger.warning(
                    "Server denied access: HTTP %d",
                    status,
                )

                return None

            # Temporary errors.
            if status in (
                408,
                425,
                429,
                500,
                502,
                503,
                504,
            ):

                wait = min(
                    60,
                    2 ** attempt
                    + random.uniform(
                        1,
                        4,
                    ),
                )

                logger.warning(
                    "Temporary error. "
                    "Waiting %.1f seconds.",
                    wait,
                )

                time.sleep(wait)

                continue

            response.raise_for_status()

            data = response.content

            try:

                cache.write_bytes(
                    data
                )

            except Exception as exc:

                logger.warning(
                    "Could not write cache: %s",
                    exc,
                )

            polite_delay()

            return data

        except requests.RequestException as exc:

            last_error = exc

            logger.warning(
                "Request error: %s",
                exc,
            )

            if attempt < MAX_RETRIES:

                wait = min(
                    60,
                    2 ** attempt
                    + random.uniform(
                        1,
                        4,
                    ),
                )

                time.sleep(wait)

    logger.error(
        "FAILED: %s | %s",
        url,
        last_error,
    )

    return None


# ============================================================
# HTML EXTRACTION
# ============================================================

def extract_html(
    data: bytes,
) -> str:

    soup = BeautifulSoup(
        data,
        "html.parser",
    )

    for element in soup(
        [
            "script",
            "style",
            "noscript",
            "svg",
            "nav",
            "footer",
            "header",
        ]
    ):

        element.decompose()

    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(
            "div",
            class_=re.compile(
                r"(content|article|main|body)",
                re.I,
            ),
        )
    )

    if main:

        text = main.get_text(
            "\n",
            strip=True,
        )

    else:

        text = soup.get_text(
            "\n",
            strip=True,
        )

    lines = []

    for line in text.splitlines():

        line = clean_text(
            line
        )

        if line:
            lines.append(line)

    text = "\n".join(lines)

    return text[
        :MAX_TEXT_CHARS_PER_SOURCE
    ]


# ============================================================
# PDF EXTRACTION
# ============================================================

def extract_pdf(
    data: bytes,
) -> str:

    if PdfReader is None:

        logger.error(
            "pypdf is not installed."
        )

        return ""

    try:

        reader = PdfReader(
            io.BytesIO(data)
        )

    except Exception as exc:

        logger.warning(
            "Could not read PDF: %s",
            exc,
        )

        return ""

    pages = []

    for page in reader.pages:

        try:

            text = page.extract_text()

            if text:
                pages.append(text)

        except Exception as exc:

            logger.debug(
                "PDF page failed: %s",
                exc,
            )

    text = "\n".join(
        pages
    )

    text = clean_text(
        text
    )

    return text[
        :MAX_TEXT_CHARS_PER_SOURCE
    ]


# ============================================================
# CONTENT EXTRACTION
# ============================================================

def extract_content(
    url: str,
    data: bytes,
) -> str:

    if (
        url.lower().endswith(".pdf")
        or data[:10].startswith(b"%PDF")
    ):

        return extract_pdf(
            data
        )

    return extract_html(
        data
    )


# ============================================================
# DUPLICATE DETECTION
# ============================================================

def duplicate(
    sources: list[Source],
    url: str,
    content: str,
) -> bool:

    normalized = normalize_url(
        url
    )

    content_hash = sha256(
        content[:10000]
    )

    for source in sources:

        if (
            normalize_url(
                source.url
            )
            == normalized
        ):

            return True

        if (
            sha256(
                source.content[:10000]
            )
            == content_hash
        ):

            return True

    return False


# ============================================================
# COLLECT ONE SECTION
# ============================================================

def collect_section(
    subsection: str,
    queries: list[str],
) -> list[Source]:

    sources = []

    logger.info("")
    logger.info(
        "=" * 70
    )

    logger.info(
        "SECTION: %s",
        subsection,
    )

    logger.info(
        "=" * 70
    )

    for query in queries:

        results = search_web(
            query
        )

        for result in results:

            url = result["url"]

            if duplicate(
                sources,
                url,
                result["snippet"],
            ):
                continue

            data = download(
                url
            )

            if not data:
                continue

            content = extract_content(
                url,
                data,
            )

            if not content:
                logger.warning(
                    "No extractable content: %s",
                    url,
                )

                continue

            if duplicate(
                sources,
                url,
                content,
            ):
                continue

            score = authority_score(
                url
            )

            source = Source(
                subsection=subsection,
                title=result[
                    "title"
                ],
                url=url,
                domain=(
                    urlparse(url).hostname
                    or ""
                ),
                source_type=source_type(
                    score
                ),
                authority_score=score,
                search_snippet=result[
                    "snippet"
                ],
                retrieved_at=utc_now(),
                content=content,
            )

            sources.append(
                source
            )

            logger.info(
                "ACCEPTED "
                "[authority=%d] %s",
                score,
                url,
            )

            if (
                len(sources)
                >= MAX_SOURCES_PER_SECTION
            ):
                break

        if (
            len(sources)
            >= MAX_SOURCES_PER_SECTION
        ):
            break

    sources.sort(
        key=lambda s: (
            -s.authority_score,
            s.title.lower(),
        )
    )

    return sources


# ============================================================
# WRITE OUTPUT
# ============================================================

def write_output(
    sources: list[Source],
):

    output = (
        DOCS_DIR
        / "10_food_and_water.txt"
    )

    with output.open(
        "w",
        encoding="utf-8",
    ) as f:

        f.write(
            "=" * 80
            + "\n"
        )

        f.write(
            "10. FOOD AND WATER SUPPLY\n"
        )

        f.write(
            "=" * 80
            + "\n\n"
        )

        f.write(
            "PURPOSE\n"
        )

        f.write(
            "This document contains emergency food and water "
            "guidance relevant to earthquake and disaster "
            "situations.\n\n"
        )

        f.write(
            "CRITICAL SAFETY DISTINCTION\n"
        )

        f.write(
            "This document contains general preparedness and "
            "safety knowledge. It does NOT determine whether "
            "water or food is currently safe in a specific "
            "location. Current boil-water advisories, water "
            "contamination, food recalls, emergency food "
            "distribution, water distribution, and utility "
            "conditions must be retrieved from current "
            "official local sources.\n\n"
        )

        f.write(
            f"COLLECTED: {utc_now()}\n"
        )

        f.write(
            f"TOTAL SOURCES: {len(sources)}\n\n"
        )

        grouped = {}

        for source in sources:

            grouped.setdefault(
                source.subsection,
                [],
            ).append(source)

        for subsection, section_sources in (
            grouped.items()
        ):

            f.write(
                "\n"
                + "#" * 80
                + "\n"
            )

            f.write(
                subsection
                + "\n"
            )

            f.write(
                "#" * 80
                + "\n\n"
            )

            for i, source in enumerate(
                section_sources,
                1,
            ):

                f.write(
                    "-" * 70
                    + "\n"
                )

                f.write(
                    f"SOURCE {i}\n"
                )

                f.write(
                    f"TITLE: "
                    f"{source.title}\n"
                )

                f.write(
                    f"URL: "
                    f"{source.url}\n"
                )

                f.write(
                    f"DOMAIN: "
                    f"{source.domain}\n"
                )

                f.write(
                    f"SOURCE TYPE: "
                    f"{source.source_type}\n"
                )

                f.write(
                    f"AUTHORITY SCORE: "
                    f"{source.authority_score}/100\n"
                )

                f.write(
                    f"RETRIEVED: "
                    f"{source.retrieved_at}\n\n"
                )

                if source.search_snippet:

                    f.write(
                        "SEARCH SNIPPET\n"
                    )

                    f.write(
                        source.search_snippet
                        + "\n\n"
                    )

                f.write(
                    "SOURCE CONTENT\n"
                )

                f.write(
                    source.content
                    + "\n\n"
                )


# ============================================================
# ERROR REPORT
# ============================================================

def write_errors(
    errors: list[str],
):

    output = (
        DOCS_DIR
        / "10_food_and_water_errors.txt"
    )

    with output.open(
        "w",
        encoding="utf-8",
    ) as f:

        f.write(
            "TOPIC 10 — ERRORS\n"
        )

        f.write(
            "=" * 70
            + "\n\n"
        )

        if not errors:

            f.write(
                "No errors recorded.\n"
            )

            return

        for error in errors:

            f.write(
                f"[{utc_now()}]\n"
            )

            f.write(
                error
                + "\n\n"
            )


# ============================================================
# QUALITY REPORT
# ============================================================

def write_quality_report(
    sources: list[Source],
):

    output = (
        DOCS_DIR
        / "10_food_and_water_quality.txt"
    )

    official = sum(
        1
        for source in sources
        if source.authority_score >= 90
    )

    academic = sum(
        1
        for source in sources
        if 70 <= source.authority_score < 90
    )

    secondary = sum(
        1
        for source in sources
        if source.authority_score < 70
    )

    with output.open(
        "w",
        encoding="utf-8",
    ) as f:

        f.write(
            "TOPIC 10 — QUALITY REPORT\n"
        )

        f.write(
            "=" * 70
            + "\n\n"
        )

        f.write(
            f"Total sources: "
            f"{len(sources)}\n"
        )

        f.write(
            f"Official / international: "
            f"{official}\n"
        )

        f.write(
            f"Academic: "
            f"{academic}\n"
        )

        f.write(
            f"Secondary: "
            f"{secondary}\n\n"
        )

        if not sources:

            f.write(
                "CRITICAL: No sources collected.\n"
            )

        elif official == 0:

            f.write(
                "WARNING: No high-authority "
                "sources were collected.\n"
            )

        else:

            f.write(
                "High-authority material was "
                "successfully collected.\n"
            )

        f.write(
            "\nIMPORTANT:\n"
        )

        f.write(
            "Before production deployment, review "
            "the emergency drinking-water and "
            "food-contamination sections manually. "
            "These sections contain life-safety "
            "information and should have explicit "
            "source provenance.\n"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    logger.info(
        "=" * 70
    )

    logger.info(
        "TOPIC 10 — FOOD AND WATER SUPPLY"
    )

    logger.info(
        "=" * 70
    )

    logger.info(
        "Sections: %d",
        len(
            RESEARCH_SECTIONS
        ),
    )

    all_sources = []
    errors = []

    for subsection, queries in (
        RESEARCH_SECTIONS
    ):

        try:

            sources = collect_section(
                subsection,
                queries,
            )

            if not sources:

                message = (
                    "No sources found for "
                    f"{subsection}"
                )

                logger.warning(
                    message
                )

                errors.append(
                    message
                )

            all_sources.extend(
                sources
            )

        except Exception as exc:

            message = (
                f"Failed section "
                f"{subsection}: {exc}"
            )

            logger.exception(
                message
            )

            errors.append(
                message
            )

    # Global deduplication.
    unique = {}

    for source in all_sources:

        key = (
            normalize_url(
                source.url
            ),
            sha256(
                source.content[:10000]
            ),
        )

        unique[key] = source

    all_sources = list(
        unique.values()
    )

    all_sources.sort(
        key=lambda s: (
            s.subsection,
            -s.authority_score,
            s.title.lower(),
        )
    )

    write_output(
        all_sources
    )

    write_errors(
        errors
    )

    write_quality_report(
        all_sources
    )

    logger.info("")
    logger.info(
        "=" * 70
    )

    logger.info(
        "TOPIC 10 COMPLETE"
    )

    logger.info(
        "Sources collected: %d",
        len(all_sources),
    )

    logger.info(
        "Output: docs/10_food_and_water.txt"
    )

    logger.info(
        "Errors: docs/10_food_and_water_errors.txt"
    )

    logger.info(
        "Quality: docs/10_food_and_water_quality.txt"
    )

    logger.info(
        "=" * 70
    )


if __name__ == "__main__":
    main()