"""
Earthquake Helper - Topic 04
Shelter and Evacuation System Information Gatherer

Purpose
-------
Gather authoritative information about earthquake evacuation,
shelters, evacuation facilities, nearby emergency facilities,
and post-earthquake evacuation decisions.

The collector is ENGLISH-ONLY in:
    - code
    - section names
    - search queries
    - metadata

The SOURCES themselves may be in any language.

Important
---------
This program is an information gathering tool.

It does NOT:
    - bypass CAPTCHAs
    - bypass authentication
    - bypass access controls
    - bypass robots/security restrictions
    - attack servers

It DOES:
    - search the web
    - prioritize authoritative sources
    - explicitly include Safe Korea / 국민안전24
    - retrieve public HTML/PDF sources
    - retry temporary failures
    - cache successful downloads
    - extract HTML/PDF text
    - remove duplicate content
    - preserve provenance
    - preserve original source language
    - produce RAG-friendly TXT output


Output
------
docs/04_shelter_evacuation.txt
docs/04_shelter_evacuation_errors.txt
cache/


Install
-------
pip install ddgs requests beautifulsoup4 pypdf

Run
---
python gathering_info/gather_topic_04.py
"""

import os
import re
import time
import random
import hashlib
import logging
from datetime import datetime, timezone
from urllib.parse import (
    urlparse,
    urljoin,
)

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

try:
    from ddgs import DDGS
except ImportError:
    print("Missing dependency: ddgs")
    print()
    print("Install with:")
    print("    pip install ddgs requests beautifulsoup4 pypdf")
    raise


# ============================================================
# CONFIGURATION
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
    "cache"
)

OUTPUT_FILE = os.path.join(
    DOCS_DIR,
    "04_shelter_evacuation.txt"
)

ERROR_FILE = os.path.join(
    DOCS_DIR,
    "04_shelter_evacuation_errors.txt"
)

os.makedirs(
    DOCS_DIR,
    exist_ok=True
)

os.makedirs(
    CACHE_DIR,
    exist_ok=True
)


# ============================================================
# NETWORK CONFIGURATION
# ============================================================

MAX_RETRIES = 5

CONNECT_TIMEOUT = 20
READ_TIMEOUT = 120

REQUEST_TIMEOUT = (
    CONNECT_TIMEOUT,
    READ_TIMEOUT
)

MIN_DELAY = 3
MAX_DELAY = 8

SEARCH_RESULTS_PER_QUERY = 8

MAX_SOURCES_PER_SECTION = 8

MAX_CONTENT_CHARS_PER_SOURCE = 60000


# ============================================================
# HTTP HEADERS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/157.0.0.0 Safari/537.36"
    ),

    "Accept": (
        "text/html,"
        "application/xhtml+xml,"
        "application/xml;q=0.9,"
        "application/pdf;q=0.8,"
        "*/*;q=0.7"
    ),

    "Accept-Language": (
        "en-US,en;q=0.9"
    ),

    "Connection": "keep-alive",
}


# ============================================================
# DIRECT OFFICIAL SOURCES
# ============================================================

"""
These sources are explicitly included instead of relying only
on search-engine discovery.

Safe Korea / 국민안전24 is especially important for a
Korea-focused deployment because it provides earthquake
evacuation guidance and safety-map facilities.
"""

DIRECT_SOURCES = [

    {
        "id": "SAFEKOREA_EARTHQUAKE_GUIDANCE",

        "name": "Safe Korea - Earthquake Guidance",

        "url": (
            "https://safekorea.go.kr/"
            "safekorea-kor/acts/nacts/action-guide.do"
            "?actsHeaderTitle=%EC%A7%80%EC%A7%84"
            "&category=earthQuake"
            "&menuSn=4"
        ),

        "section_ids": [
            "04.01",
            "04.02",
            "04.14",
            "04.17",
            "04.18",
            "04.19",
            "04.20",
            "04.21",
            "04.22",
            "04.23",
            "04.24",
            "04.25",
            "04.26",
            "04.30",
            "04.35",
            "04.36",
        ],

        "authority_score": 10,

        "country": "South Korea",

        "language": "Korean",
    },

    {
        "id": "SAFEKOREA_SAFETY_MAP",

        "name": "Safe Korea - Safety Map",

        "url": (
            "https://safekorea.go.kr/"
            "safekorea-kor/flsm/flsm/"
            "facilitiesSafteyMap.do"
        ),

        "section_ids": [
            "04.03",
            "04.04",
            "04.05",
            "04.06",
            "04.07",
            "04.08",
            "04.09",
            "04.10",
            "04.11",
            "04.12",
            "04.13",
            "04.28",
            "04.29",
            "04.30",
            "04.31",
            "04.32",
            "04.37",
        ],

        "authority_score": 10,

        "country": "South Korea",

        "language": "Korean",
    },

    {
        "id": "SAFEKOREA_EARTHQUAKE_PAGE",

        "name": "Safe Korea - Earthquake",

        "url": (
            "https://safekorea.go.kr/"
            "safekorea-kor/ctim/csim/"
            "earthquake.do"
        ),

        "section_ids": [
            "04.01",
            "04.03",
            "04.06",
            "04.07",
            "04.08",
            "04.09",
            "04.30",
            "04.31",
            "04.32",
        ],

        "authority_score": 10,

        "country": "South Korea",

        "language": "Korean",
    },

    # --------------------------------------------------------
    # United States
    # --------------------------------------------------------

    {
        "id": "FEMA_EARTHQUAKE",

        "name": "FEMA",

        "url": (
            "https://www.ready.gov/"
            "earthquakes"
        ),

        "section_ids": [
            "04.01",
            "04.02",
            "04.14",
            "04.17",
            "04.18",
            "04.19",
            "04.20",
            "04.21",
            "04.22",
            "04.23",
            "04.24",
            "04.26",
            "04.35",
            "04.36",
        ],

        "authority_score": 10,

        "country": "United States",

        "language": "English",
    },

    {
        "id": "USGS_EARTHQUAKE_SAFETY",

        "name": "USGS",

        "url": (
            "https://www.usgs.gov/"
            "programs/earthquake-hazards/"
            "earthquake-safety-home"
        ),

        "section_ids": [
            "04.01",
            "04.02",
            "04.14",
            "04.17",
            "04.19",
            "04.35",
            "04.36",
        ],

        "authority_score": 10,

        "country": "United States",

        "language": "English",
    },

    {
        "id": "RED_CROSS_EARTHQUAKE",

        "name": "American Red Cross",

        "url": (
            "https://www.redcross.org/"
            "get-help/how-to-prepare-for-emergencies/"
            "types-of-emergencies/earthquake.html"
        ),

        "section_ids": [
            "04.01",
            "04.02",
            "04.17",
            "04.18",
            "04.19",
            "04.20",
            "04.21",
            "04.22",
            "04.23",
            "04.26",
            "04.33",
            "04.36",
        ],

        "authority_score": 9,

        "country": "United States",

        "language": "English",
    },

    # --------------------------------------------------------
    # International
    # --------------------------------------------------------

    {
        "id": "IFRC_EARTHQUAKE",

        "name": "International Federation of Red Cross and Red Crescent Societies",

        "url": (
            "https://www.ifrc.org/"
        ),

        "section_ids": [
            "04.01",
            "04.02",
            "04.19",
            "04.20",
            "04.21",
            "04.22",
            "04.23",
            "04.26",
            "04.33",
            "04.35",
        ],

        "authority_score": 9,

        "country": "International",

        "language": "English",
    },

    {
        "id": "WHO_EMERGENCY",

        "name": "World Health Organization",

        "url": (
            "https://www.who.int/"
        ),

        "section_ids": [
            "04.06",
            "04.07",
            "04.08",
            "04.09",
            "04.10",
            "04.11",
            "04.12",
            "04.29",
        ],

        "authority_score": 10,

        "country": "International",

        "language": "English",
    },

    # --------------------------------------------------------
    # Japan
    # --------------------------------------------------------

    {
        "id": "JMA_EARTHQUAKE",

        "name": "Japan Meteorological Agency",

        "url": (
            "https://www.jma.go.jp/"
        ),

        "section_ids": [
            "04.01",
            "04.03",
            "04.04",
            "04.14",
            "04.19",
            "04.25",
            "04.35",
        ],

        "authority_score": 10,

        "country": "Japan",

        "language": "Japanese",
    },

    # --------------------------------------------------------
    # New Zealand
    # --------------------------------------------------------

    {
        "id": "NEMA_NEW_ZEALAND",

        "name": "New Zealand National Emergency Management Agency",

        "url": (
            "https://www.civildefence.govt.nz/"
        ),

        "section_ids": [
            "04.01",
            "04.02",
            "04.14",
            "04.19",
            "04.25",
            "04.26",
            "04.35",
        ],

        "authority_score": 10,

        "country": "New Zealand",

        "language": "English",
    },

    # --------------------------------------------------------
    # Australia
    # --------------------------------------------------------

    {
        "id": "AUSTRALIA_BOM",

        "name": "Australian Bureau of Meteorology",

        "url": (
            "https://www.bom.gov.au/"
        ),

        "section_ids": [
            "04.25",
            "04.26",
            "04.35",
        ],

        "authority_score": 10,

        "country": "Australia",

        "language": "English",
    },

    # --------------------------------------------------------
    # Canada
    # --------------------------------------------------------

    {
        "id": "CANADA_EMERGENCY",

        "name": "Government of Canada",

        "url": (
            "https://www.canada.ca/"
            "en/public-safety-canada.html"
        ),

        "section_ids": [
            "04.01",
            "04.02",
            "04.14",
            "04.19",
            "04.26",
            "04.35",
            "04.36",
        ],

        "authority_score": 10,

        "country": "Canada",

        "language": "English/French",
    },
]


# ============================================================
# RESEARCH SECTIONS
# ============================================================

RESEARCH_SECTIONS = [

    (
        "04.01",
        "Earthquake Evacuation Principles",
        [
            "earthquake evacuation principles",
            "earthquake evacuation safety guidance",
            "what to do after an earthquake evacuation",
        ],
    ),

    (
        "04.02",
        "Immediate Evacuation vs Shelter-in-Place",
        [
            "earthquake evacuate or shelter in place",
            "earthquake when to evacuate building",
            "earthquake shelter in place guidance",
        ],
    ),

    (
        "04.03",
        "Earthquake Outdoor Evacuation Locations",
        [
            "earthquake outdoor evacuation area",
            "earthquake outdoor evacuation shelter",
            "earthquake designated evacuation area",
            "earthquake safe open space evacuation",
        ],
    ),

    (
        "04.04",
        "Earthquake Tsunami Evacuation Locations",
        [
            "earthquake tsunami evacuation shelter",
            "earthquake tsunami evacuation area",
            "tsunami evacuation location after earthquake",
            "tsunami evacuation high ground earthquake",
        ],
    ),

    (
        "04.05",
        "Temporary Housing Facilities",
        [
            "earthquake temporary housing facilities",
            "earthquake emergency temporary accommodation",
            "earthquake temporary shelter housing",
        ],
    ),

    (
        "04.06",
        "Nearby Fire Stations",
        [
            "earthquake nearby fire station emergency",
            "fire station earthquake emergency response",
            "earthquake fire department emergency services",
        ],
    ),

    (
        "04.07",
        "Nearby Hospitals",
        [
            "earthquake nearby hospital emergency",
            "earthquake hospital emergency care",
            "earthquake medical facility evacuation",
        ],
    ),

    (
        "04.08",
        "Nearby Emergency Medical Centers",
        [
            "earthquake emergency medical center",
            "earthquake emergency department nearby",
            "earthquake emergency medical services",
        ],
    ),

    (
        "04.09",
        "Nearby Pharmacies",
        [
            "earthquake nearby pharmacy emergency",
            "earthquake pharmacy emergency supplies",
            "pharmacy availability disaster emergency",
        ],
    ),

    (
        "04.10",
        "Nearby Police Stations",
        [
            "earthquake nearby police station",
            "earthquake police emergency services",
            "police response earthquake disaster",
        ],
    ),

    (
        "04.11",
        "Nearby Public Health Centers",
        [
            "earthquake public health center emergency",
            "earthquake public health services",
            "disaster public health facility",
        ],
    ),

    (
        "04.12",
        "Emergency Water Supply Facilities",
        [
            "earthquake emergency water supply facility",
            "earthquake emergency drinking water",
            "disaster emergency water facilities",
        ],
    ),

    (
        "04.13",
        "Evacuation Routes",
        [
            "earthquake evacuation route planning",
            "earthquake evacuation routes",
            "safe evacuation route after earthquake",
        ],
    ),

    (
        "04.14",
        "Safe Areas and Open Spaces",
        [
            "earthquake safe open spaces",
            "earthquake parks evacuation safety",
            "earthquake open area away from buildings",
        ],
    ),

    (
        "04.15",
        "Unsafe Evacuation Areas",
        [
            "earthquake unsafe areas evacuation",
            "earthquake hazards near buildings during evacuation",
            "earthquake places to avoid after shaking",
        ],
    ),

    (
        "04.16",
        "Building Evacuation",
        [
            "earthquake evacuating damaged building",
            "earthquake building evacuation stairs",
            "earthquake evacuation building safety",
        ],
    ),

    (
        "04.17",
        "Elevator Prohibition",
        [
            "earthquake elevator safety evacuation",
            "earthquake do not use elevator",
            "earthquake elevator emergency guidance",
        ],
    ),

    (
        "04.18",
        "Evacuation During Aftershocks",
        [
            "earthquake aftershock evacuation",
            "aftershock evacuation safety",
            "earthquake damaged building aftershock evacuation",
        ],
    ),

    (
        "04.19",
        "Evacuation With Children",
        [
            "earthquake evacuation children safety",
            "earthquake evacuation infants children",
            "earthquake shelter children emergency",
        ],
    ),

    (
        "04.20",
        "Evacuation With Older Adults",
        [
            "earthquake evacuation elderly older adults",
            "earthquake shelter older people",
            "earthquake evacuation assistance elderly",
        ],
    ),

    (
        "04.21",
        "Evacuation With People With Disabilities",
        [
            "earthquake evacuation people with disabilities",
            "earthquake accessible evacuation shelter",
            "earthquake evacuation wheelchair users",
        ],
    ),

    (
        "04.22",
        "Evacuation With Pets",
        [
            "earthquake evacuation pets",
            "earthquake emergency shelter pets",
            "earthquake evacuation animals",
        ],
    ),

    (
        "04.23",
        "Evacuation During Fire or Gas Leak",
        [
            "earthquake evacuation gas leak fire",
            "earthquake fire evacuation guidance",
            "earthquake gas leak evacuation safety",
        ],
    ),

    (
        "04.24",
        "Evacuation During Tsunami Risk",
        [
            "earthquake tsunami evacuation immediately",
            "earthquake tsunami warning evacuation",
            "tsunami evacuation after coastal earthquake",
        ],
    ),

    (
        "04.25",
        "Evacuation During Winter or Extreme Weather",
        [
            "earthquake evacuation winter weather",
            "earthquake shelter extreme cold",
            "earthquake evacuation extreme heat",
        ],
    ),

    (
        "04.26",
        "Shelter Capacity and Availability",
        [
            "earthquake shelter capacity availability",
            "emergency shelter available capacity earthquake",
            "disaster shelter occupancy information",
        ],
    ),

    (
        "04.27",
        "Shelter Accessibility",
        [
            "earthquake shelter accessibility",
            "accessible emergency shelter earthquake",
            "wheelchair accessible disaster shelter",
        ],
    ),

    (
        "04.28",
        "Shelter Facilities and Services",
        [
            "earthquake emergency shelter facilities services",
            "disaster shelter services food water medical",
            "emergency evacuation center services",
        ],
    ),

    (
        "04.29",
        "How to Find the Nearest Shelter",
        [
            "how to find nearest earthquake shelter",
            "earthquake shelter location map",
            "find nearest evacuation center earthquake",
        ],
    ),

    (
        "04.30",
        "How to Find Nearby Medical Assistance",
        [
            "earthquake find nearby hospital emergency",
            "earthquake find nearby pharmacy",
            "earthquake find emergency medical center",
        ],
    ),

    (
        "04.31",
        "How to Find Emergency Services",
        [
            "earthquake find nearby fire station",
            "earthquake find police station",
            "earthquake emergency services nearby",
        ],
    ),

    (
        "04.32",
        "What to Bring to an Evacuation Shelter",
        [
            "earthquake evacuation shelter what to bring",
            "earthquake emergency shelter supplies",
            "what to take to disaster shelter",
        ],
    ),

    (
        "04.33",
        "Shelter Registration and Family Reunification",
        [
            "earthquake shelter registration family reunification",
            "disaster shelter family reunification",
            "earthquake missing family shelter information",
        ],
    ),

    (
        "04.34",
        "Official Evacuation Orders and Warnings",
        [
            "earthquake official evacuation warning",
            "earthquake evacuation order emergency alert",
            "earthquake government evacuation instructions",
        ],
    ),

    (
        "04.35",
        "Returning Home After Evacuation",
        [
            "earthquake when safe to return home",
            "earthquake reentry after evacuation",
            "earthquake returning home safety",
        ],
    ),

    (
        "04.36",
        "Shelter Status and Temporary Closure",
        [
            "earthquake shelter closure status",
            "emergency shelter temporary closure",
            "earthquake evacuation shelter status",
        ],
    ),

    (
        "04.37",
        "Emergency Contacts and Disaster Response Agencies",
        [
            "earthquake emergency contacts disaster agency",
            "earthquake emergency numbers official",
            "earthquake emergency services government",
        ],
    ),
]


# ============================================================
# AUTHORITY
# ============================================================

PRIMARY_AUTHORITY_DOMAINS = {

    # --------------------------------------------
    # South Korea
    # --------------------------------------------

    "safekorea.go.kr": 10,
    "mois.go.kr": 10,
    "kma.go.kr": 10,
    "nfa.go.kr": 10,
    "119.go.kr": 10,
    "korea.kr": 9,

    # --------------------------------------------
    # United States
    # --------------------------------------------

    "fema.gov": 10,
    "ready.gov": 10,
    "usgs.gov": 10,
    "noaa.gov": 10,
    "cdc.gov": 10,

    # --------------------------------------------
    # International
    # --------------------------------------------

    "who.int": 10,
    "ifrc.org": 9,
    "un.org": 9,

    # --------------------------------------------
    # Japan
    # --------------------------------------------

    "jma.go.jp": 10,

    # --------------------------------------------
    # New Zealand
    # --------------------------------------------

    "civildefence.govt.nz": 10,

    # --------------------------------------------
    # Australia
    # --------------------------------------------

    "bom.gov.au": 10,
    "gov.au": 9,

    # --------------------------------------------
    # Canada
    # --------------------------------------------

    "canada.ca": 10,

    # --------------------------------------------
    # United Kingdom
    # --------------------------------------------

    "gov.uk": 10,
}


MEDIUM_AUTHORITY_SUFFIXES = (
    ".gov",
    ".gov.uk",
    ".go.kr",
    ".go.jp",
    ".gov.au",
    ".govt.nz",
    ".gc.ca",
    ".ac.kr",
    ".ac.jp",
    ".edu",
    ".edu.au",
    ".int",
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(
    "shelter_evacuation"
)


def log_error(message):
    timestamp = datetime.now(
        timezone.utc
    ).isoformat()

    with open(
        ERROR_FILE,
        "a",
        encoding="utf-8"
    ) as f:

        f.write(
            f"[{timestamp}] {message}\n"
        )


# ============================================================
# URL UTILITIES
# ============================================================

def normalize_url(url):

    if not url:
        return ""

    url = url.strip()

    # Remove common tracking parameters.
    url = re.sub(
        r"[?&]"
        r"(utm_[^&]+|"
        r"fbclid|"
        r"gclid|"
        r"mc_cid|"
        r"mc_eid)"
        r"=[^&]*",
        "",
        url,
        flags=re.IGNORECASE
    )

    return url.rstrip("/")


def domain_from_url(url):

    try:
        domain = urlparse(
            url
        ).netloc.lower()

        if domain.startswith("www."):
            domain = domain[4:]

        return domain

    except Exception:
        return ""


def authority_score(url):

    domain = domain_from_url(
        url
    )

    if domain in PRIMARY_AUTHORITY_DOMAINS:
        return PRIMARY_AUTHORITY_DOMAINS[
            domain
        ]

    for suffix in MEDIUM_AUTHORITY_SUFFIXES:

        if domain.endswith(
            suffix
        ):
            return 7

    return 3


def source_category(url):

    domain = domain_from_url(
        url
    )

    if (
        domain in PRIMARY_AUTHORITY_DOMAINS
        or domain.endswith(
            (
                ".gov",
                ".go.kr",
                ".go.jp",
                ".gov.au",
                ".govt.nz",
            )
        )
    ):
        return "government / public authority"

    if (
        domain.endswith(
            (
                ".edu",
                ".ac.kr",
                ".ac.jp",
                ".edu.au",
            )
        )
    ):
        return "academic"

    if domain.endswith(
        ".int"
    ):
        return "international organization"

    if (
        "redcross.org" in domain
        or "ifrc.org" in domain
    ):
        return "humanitarian organization"

    return "general web source"


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text):

    if not text:
        return ""

    text = text.replace(
        "\xa0",
        " "
    )

    # Normalize whitespace while preserving lines.
    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    text = re.sub(
        r"\n\s*\n\s*\n+",
        "\n\n",
        text
    )

    return text.strip()


def content_hash(text):

    return hashlib.sha256(
        text.encode(
            "utf-8",
            errors="ignore"
        )
    ).hexdigest()


# ============================================================
# CACHE
# ============================================================

def cache_path_for_url(url):

    digest = hashlib.sha256(
        url.encode(
            "utf-8"
        )
    ).hexdigest()

    return os.path.join(
        CACHE_DIR,
        digest + ".txt"
    )


def load_cache(url):

    path = cache_path_for_url(
        url
    )

    if not os.path.exists(
        path
    ):
        return None

    try:

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            return f.read()

    except Exception as e:

        log_error(
            f"Cache read failed: "
            f"{url} | {repr(e)}"
        )

        return None


def save_cache(
    url,
    text
):

    path = cache_path_for_url(
        url
    )

    try:

        with open(
            path,
            "w",
            encoding="utf-8"
        ) as f:

            f.write(
                text
            )

    except Exception as e:

        log_error(
            f"Cache write failed: "
            f"{url} | {repr(e)}"
        )


# ============================================================
# POLITE DELAY
# ============================================================

def polite_delay():

    delay = random.uniform(
        MIN_DELAY,
        MAX_DELAY
    )

    logger.info(
        "Waiting %.1f seconds...",
        delay
    )

    time.sleep(
        delay
    )


# ============================================================
# HTTP SESSION
# ============================================================

session = requests.Session()

session.headers.update(
    HEADERS
)


# ============================================================
# HTML EXTRACTION
# ============================================================

def extract_html(
    html,
    base_url=""
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    # Remove irrelevant elements.
    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "svg",
            "nav",
            "footer",
            "header",
            "form",
            "aside",
        ]
    ):
        tag.decompose()

    # Prefer main content.
    candidates = []

    selectors = [
        "main",
        "article",
        "[role='main']",
        ".content",
        ".main-content",
        "#content",
        "#main-content",
    ]

    for selector in selectors:

        try:

            candidates.extend(
                soup.select(
                    selector
                )
            )

        except Exception:
            pass

    if candidates:

        element = max(
            candidates,
            key=lambda x:
                len(
                    x.get_text(
                        " ",
                        strip=True
                    )
                )
        )

    else:

        element = (
            soup.body
            or soup
        )

    text = element.get_text(
        "\n",
        strip=True
    )

    return clean_text(
        text
    )


# ============================================================
# PDF EXTRACTION
# ============================================================

def extract_pdf(
    content
):

    temp_path = os.path.join(
        CACHE_DIR,
        "_temporary_topic04.pdf"
    )

    try:

        with open(
            temp_path,
            "wb"
        ) as f:

            f.write(
                content
            )

        reader = PdfReader(
            temp_path
        )

        pages = []

        for page_number, page in enumerate(
            reader.pages,
            start=1
        ):

            try:

                page_text = (
                    page.extract_text()
                )

                if page_text:

                    pages.append(
                        "\n"
                        f"[PDF PAGE {page_number}]"
                        "\n"
                        f"{page_text}"
                    )

            except Exception as e:

                log_error(
                    "PDF page extraction failed "
                    f"page={page_number} | "
                    f"{repr(e)}"
                )

        return clean_text(
            "\n".join(
                pages
            )
        )

    finally:

        try:
            os.remove(
                temp_path
            )
        except Exception:
            pass


# ============================================================
# FETCH URL
# ============================================================

def fetch_url(
    url
):

    url = normalize_url(
        url
    )

    if not url:
        return None

    # --------------------------------------------------------
    # Cache
    # --------------------------------------------------------

    cached = load_cache(
        url
    )

    if cached:

        logger.info(
            "Using cached source: %s",
            url
        )

        return cached

    # --------------------------------------------------------
    # Retry loop
    # --------------------------------------------------------

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        logger.info(
            "Fetching [%d/%d]: %s",
            attempt,
            MAX_RETRIES,
            url
        )

        try:

            response = session.get(
                url,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True
            )

            status = (
                response.status_code
            )

            # ------------------------------------------------
            # Successful response
            # ------------------------------------------------

            if status == 200:

                content_type = (
                    response.headers
                    .get(
                        "Content-Type",
                        ""
                    )
                    .lower()
                )

                if (
                    "application/pdf"
                    in content_type
                    or url.lower().endswith(
                        ".pdf"
                    )
                ):

                    text = extract_pdf(
                        response.content
                    )

                else:

                    text = extract_html(
                        response.text,
                        url
                    )

                text = clean_text(
                    text
                )

                if not text:

                    raise RuntimeError(
                        "No extractable text."
                    )

                text = text[
                    :MAX_CONTENT_CHARS_PER_SOURCE
                ]

                save_cache(
                    url,
                    text
                )

                return text

            # ------------------------------------------------
            # Explicit access restrictions
            # ------------------------------------------------

            if status in (
                401,
                403,
                451
            ):

                message = (
                    f"Access restricted "
                    f"(HTTP {status}): "
                    f"{url}"
                )

                logger.warning(
                    message
                )

                log_error(
                    message
                )

                return None

            # ------------------------------------------------
            # Temporary server/network errors
            # ------------------------------------------------

            if status in (
                408,
                425,
                429,
                500,
                502,
                503,
                504
            ):

                wait_time = min(
                    60,
                    (2 ** attempt)
                    + random.uniform(
                        1,
                        4
                    )
                )

                logger.warning(
                    "Temporary HTTP %s.",
                    status
                )

                logger.warning(
                    "Retrying in %.1f seconds...",
                    wait_time
                )

                time.sleep(
                    wait_time
                )

                continue

            # ------------------------------------------------
            # Other errors
            # ------------------------------------------------

            message = (
                f"HTTP {status}: {url}"
            )

            logger.warning(
                message
            )

            log_error(
                message
            )

            return None

        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError
        ) as e:

            wait_time = min(
                60,
                (2 ** attempt)
                + random.uniform(
                    1,
                    4
                )
            )

            logger.warning(
                "Temporary network error: %s",
                repr(e)
            )

            logger.warning(
                "Retrying in %.1f seconds...",
                wait_time
            )

            time.sleep(
                wait_time
            )

        except Exception as e:

            message = (
                f"Fetch failed: "
                f"{url} | "
                f"{repr(e)}"
            )

            logger.warning(
                message
            )

            log_error(
                message
            )

            return None

    log_error(
        "Maximum retries exceeded: "
        f"{url}"
    )

    return None


# ============================================================
# SEARCH
# ============================================================

def search_web(
    query
):

    logger.info(
        "Searching: %s",
        query
    )

    results = []

    try:

        with DDGS() as ddgs:

            search_results = ddgs.text(
                query,
                max_results=SEARCH_RESULTS_PER_QUERY
            )

            for result in search_results:

                url = normalize_url(
                    result.get(
                        "href",
                        ""
                    )
                )

                if not url:
                    continue

                results.append(
                    {
                        "title": (
                            result.get(
                                "title",
                                ""
                            )
                        ),

                        "url": url,

                        "snippet": (
                            result.get(
                                "body",
                                ""
                            )
                        ),
                    }
                )

    except Exception as e:

        message = (
            f"Search failed: "
            f"{query} | "
            f"{repr(e)}"
        )

        logger.warning(
            message
        )

        log_error(
            message
        )

    return results


# ============================================================
# DIRECT SOURCE CONVERSION
# ============================================================

def direct_source_to_result(
    source
):

    return {
        "title": source["name"],
        "url": normalize_url(
            source["url"]
        ),
        "snippet": (
            "Directly configured "
            "authoritative source."
        ),
        "authority_score": (
            source["authority_score"]
        ),
        "domain": domain_from_url(
            source["url"]
        ),
        "category": (
            "government / public authority"
            if source["authority_score"] >= 10
            else source_category(
                source["url"]
            )
        ),
        "country": source.get(
            "country",
            "Unknown"
        ),
        "language": source.get(
            "language",
            "Unknown"
        ),
        "direct_source": True,
    }


# ============================================================
# SOURCE RANKING
# ============================================================

def rank_sources(
    results
):

    seen_urls = set()

    ranked = []

    for result in results:

        url = normalize_url(
            result.get(
                "url",
                ""
            )
        )

        if not url:
            continue

        if url in seen_urls:
            continue

        seen_urls.add(
            url
        )

        result["url"] = url

        # Direct source scores are retained.
        if "authority_score" not in result:

            result["authority_score"] = (
                authority_score(
                    url
                )
            )

        if "domain" not in result:

            result["domain"] = (
                domain_from_url(
                    url
                )
            )

        if "category" not in result:

            result["category"] = (
                source_category(
                    url
                )
            )

        if "country" not in result:

            result["country"] = (
                "Unknown"
            )

        if "language" not in result:

            result["language"] = (
                "Unknown / not detected"
            )

        if "direct_source" not in result:

            result["direct_source"] = False

        ranked.append(
            result
        )

    ranked.sort(
        key=lambda item: (
            -item[
                "authority_score"
            ],

            # Directly configured sources
            # receive a secondary preference.
            -int(
                item.get(
                    "direct_source",
                    False
                )
            ),

            item["url"]
        )
    )

    return ranked


# ============================================================
# DUPLICATE CONTENT
# ============================================================

def remove_duplicate_content(
    sources
):

    seen_hashes = set()

    unique = []

    for source in sources:

        text = source.get(
            "content",
            ""
        )

        if not text:
            continue

        digest = content_hash(
            text
        )

        if digest in seen_hashes:

            logger.info(
                "Duplicate content skipped: %s",
                source["url"]
            )

            continue

        seen_hashes.add(
            digest
        )

        source[
            "content_hash"
        ] = digest

        unique.append(
            source
        )

    return unique


# ============================================================
# DIRECT SOURCES FOR A SECTION
# ============================================================

def get_direct_sources_for_section(
    section_id
):

    results = []

    for source in DIRECT_SOURCES:

        if section_id in source[
            "section_ids"
        ]:

            results.append(
                direct_source_to_result(
                    source
                )
            )

    return results


# ============================================================
# COLLECT ONE SECTION
# ============================================================

def collect_section(
    section_id,
    section_name,
    queries
):

    logger.info("")
    logger.info("=" * 80)
    logger.info(
        "SECTION %s - %s",
        section_id,
        section_name
    )
    logger.info("=" * 80)

    discovered = []

    # --------------------------------------------------------
    # Add explicitly configured authoritative sources first.
    # --------------------------------------------------------

    direct_sources = (
        get_direct_sources_for_section(
            section_id
        )
    )

    discovered.extend(
        direct_sources
    )

    logger.info(
        "Added %d direct authoritative sources.",
        len(direct_sources)
    )

    # --------------------------------------------------------
    # Search web
    # --------------------------------------------------------

    for query in queries:

        results = search_web(
            query
        )

        discovered.extend(
            results
        )

        polite_delay()

    # --------------------------------------------------------
    # Rank
    # --------------------------------------------------------

    ranked = rank_sources(
        discovered
    )

    selected = ranked[
        :MAX_SOURCES_PER_SECTION
    ]

    logger.info(
        "Selected %d sources for retrieval.",
        len(selected)
    )

    # --------------------------------------------------------
    # Retrieve
    # --------------------------------------------------------

    retrieved = []

    for source in selected:

        url = source["url"]

        logger.info(
            "Retrieving: %s",
            url
        )

        content = fetch_url(
            url
        )

        if not content:

            logger.warning(
                "No usable content: %s",
                url
            )

            polite_delay()

            continue

        source["content"] = content

        retrieved.append(
            source
        )

        polite_delay()

    # --------------------------------------------------------
    # Remove duplicate pages/content
    # --------------------------------------------------------

    retrieved = remove_duplicate_content(
        retrieved
    )

    return retrieved


# ============================================================
# WRITE OUTPUT
# ============================================================

def write_section(
    output,
    section_id,
    section_name,
    sources
):

    output.write(
        "\n"
        + "=" * 100
        + "\n"
    )

    output.write(
        f"{section_id} "
        f"{section_name}\n"
    )

    output.write(
        "=" * 100
        + "\n\n"
    )

    if not sources:

        output.write(
            "NO USABLE SOURCES FOUND.\n"
        )

        output.write(
            "Manual research/review is required "
            "for this section.\n\n"
        )

        return

    for index, source in enumerate(
        sources,
        start=1
    ):

        output.write(
            "-" * 85
            + "\n"
        )

        output.write(
            f"SOURCE {index}\n"
        )

        output.write(
            "-" * 85
            + "\n"
        )

        output.write(
            f"Title: "
            f"{source.get('title', '')}\n"
        )

        output.write(
            f"URL: "
            f"{source.get('url', '')}\n"
        )

        output.write(
            f"Domain: "
            f"{source.get('domain', '')}\n"
        )

        output.write(
            f"Country/Region: "
            f"{source.get('country', 'Unknown')}\n"
        )

        output.write(
            f"Source language: "
            f"{source.get('language', 'Unknown')}\n"
        )

        output.write(
            f"Source category: "
            f"{source.get('category', '')}\n"
        )

        output.write(
            f"Authority score: "
            f"{source.get('authority_score', 0)}/10\n"
        )

        output.write(
            "Directly configured source: "
            f"{source.get('direct_source', False)}\n"
        )

        output.write(
            "Retrieved: "
            f"{datetime.now(timezone.utc).isoformat()}\n"
        )

        output.write(
            f"Content hash: "
            f"{source.get('content_hash', '')}\n"
        )

        snippet = source.get(
            "snippet",
            ""
        ).strip()

        if snippet:

            output.write(
                "\nSEARCH RESULT SUMMARY:\n"
            )

            output.write(
                snippet
                + "\n"
            )

        output.write(
            "\nSOURCE CONTENT:\n"
        )

        output.write(
            source.get(
                "content",
                ""
            )
        )

        output.write(
            "\n\n"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    logger.info("")
    logger.info("=" * 80)
    logger.info(
        "EARTHQUAKE HELPER"
    )
    logger.info(
        "TOPIC 04 - SHELTER AND EVACUATION SYSTEM"
    )
    logger.info("=" * 80)
    logger.info("")

    total_sources = 0

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as output:

        # ----------------------------------------------------
        # Document metadata
        # ----------------------------------------------------

        output.write(
            "EARTHQUAKE HELPER\n"
        )

        output.write(
            "TOPIC 04 - SHELTER AND EVACUATION SYSTEM\n"
        )

        output.write(
            "=" * 100
            + "\n\n"
        )

        output.write(
            "DOCUMENT PURPOSE\n"
        )

        output.write(
            "This document contains gathered information "
            "about earthquake evacuation, shelters, "
            "evacuation facilities, nearby emergency "
            "services, and post-earthquake shelter decisions.\n\n"
        )

        output.write(
            "COLLECTION LANGUAGE\n"
        )

        output.write(
            "The collector uses English search queries "
            "and English metadata. Source material may be "
            "in any language and is preserved in its "
            "original language.\n\n"
        )

        output.write(
            "SOURCE POLICY\n"
        )

        output.write(
            "Official government agencies, emergency "
            "management organizations, scientific agencies, "
            "and recognized humanitarian organizations "
            "receive higher authority scores.\n\n"
        )

        output.write(
            "KOREA-SPECIFIC SOURCE\n"
        )

        output.write(
            "Safe Korea / 국민안전24 is explicitly included "
            "as a Tier-1 authoritative source because its "
            "official earthquake guidance and Safety Map "
            "provide earthquake evacuation locations and "
            "nearby safety facilities.\n\n"
        )

        output.write(
            "IMPORTANT RAG DISTINCTION\n"
        )

        output.write(
            "Static evacuation guidance and dynamic "
            "facility/location information should not be "
            "treated as identical data. Facility availability "
            "and location should be refreshed when used for "
            "real-time emergency assistance.\n\n"
        )

        output.write(
            "Generated: "
            f"{datetime.now(timezone.utc).isoformat()}\n\n"
        )

        # ----------------------------------------------------
        # Collect sections
        # ----------------------------------------------------

        for (
            section_id,
            section_name,
            queries
        ) in RESEARCH_SECTIONS:

            sources = collect_section(
                section_id,
                section_name,
                queries
            )

            total_sources += len(
                sources
            )

            write_section(
                output,
                section_id,
                section_name,
                sources
            )

    logger.info("")
    logger.info("=" * 80)
    logger.info(
        "COLLECTION COMPLETE"
    )
    logger.info("=" * 80)

    logger.info(
        "Output file:"
    )

    logger.info(
        "%s",
        OUTPUT_FILE
    )

    logger.info(
        "Total usable sources: %d",
        total_sources
    )

    logger.info(
        "Error log:"
    )

    logger.info(
        "%s",
        ERROR_FILE
    )

    logger.info("")
    logger.info(
        "The collector preserves source language."
    )

    logger.info(
        "The collector does not bypass access controls."
    )


if __name__ == "__main__":
    main()