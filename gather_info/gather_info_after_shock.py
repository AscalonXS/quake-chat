"""
===============================================================
EARTHQUAKE HELPER
TOPICS 06–09 INFORMATION GATHERER
===============================================================

06. Tsunami
07. Aftershocks
08. Trapped Person / Collapsed Structure
09. Family Reunification

PURPOSE
-------
This program gathers authoritative information for an earthquake
emergency RAG knowledge base.

It is NOT intended to blindly crawl the internet.

The collector:

    1. Searches for relevant authoritative sources.
    2. Downloads useful HTML/PDF pages.
    3. Extracts readable text.
    4. Scores source authority.
    5. Removes duplicates.
    6. Preserves provenance.
    7. Organizes information by topic/subtopic.
    8. Writes RAG-friendly TXT files.
    9. Records failures instead of silently ignoring them.

OUTPUT
------

docs/
    06_tsunami.txt
    06_tsunami_errors.txt

    07_aftershocks.txt
    07_aftershocks_errors.txt

    08_trapped_person.txt
    08_trapped_person_errors.txt

    09_family_reunification.txt
    09_family_reunification_errors.txt

cache/
    downloaded pages and PDFs

IMPORTANT SAFETY DESIGN
-----------------------
This dataset should NOT be treated as a source of live emergency
status.

Static knowledge:
    - tsunami warning signs
    - evacuation principles
    - aftershock safety
    - trapped-person guidance
    - family communication planning

Dynamic information:
    - current tsunami warning
    - current earthquake
    - current aftershock sequence
    - current shelter status
    - current hospital status
    - current missing-person information

The chatbot should retrieve live information from official systems
when answering time-sensitive questions.

===============================================================
"""

from __future__ import annotations

import hashlib
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
CACHE_DIR = BASE_DIR / "cache" / "topics_06_09"

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

MAX_SOURCES_PER_SUBSECTION = 6

MAX_TEXT_CHARS_PER_SOURCE = 30000

MAX_RETRIES = 5

CONNECT_TIMEOUT = 20
READ_TIMEOUT = 120

MIN_DELAY = 2.5
MAX_DELAY = 6.0

SEARCH_DELAY_MIN = 3.0
SEARCH_DELAY_MAX = 7.0

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

logger = logging.getLogger("earthquake_topics_06_09")


# ============================================================
# HTTP
# ============================================================

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class Source:
    topic: str
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
# TOPIC DEFINITIONS
# ============================================================

TOPICS = {

    # ========================================================
    # 06 TSUNAMI
    # ========================================================

    "06_tsunami": {

        "title": "06. TSUNAMI",

        "description": (
            "Earthquake-related tsunami recognition, warnings, "
            "evacuation, coastal hazards, and post-tsunami safety."
        ),

        "sections": [

            (
                "06.01 Tsunami Recognition",
                [
                    "tsunami recognition after earthquake",
                    "earthquake tsunami warning signs",
                    "tsunami safety official guidance",
                ],
            ),

            (
                "06.02 Natural Tsunami Warning Signs",
                [
                    "strong long earthquake natural tsunami warning",
                    "sudden sea level fall tsunami warning",
                    "ocean roar tsunami warning",
                ],
            ),

            (
                "06.03 Official Tsunami Warnings",
                [
                    "official tsunami warning watch advisory guidance",
                    "tsunami warning evacuation official",
                    "tsunami warning levels emergency management",
                ],
            ),

            (
                "06.04 Immediate Evacuation",
                [
                    "tsunami evacuation immediately high ground inland",
                    "tsunami evacuation official guidance",
                    "tsunami evacuation routes safety",
                ],
            ),

            (
                "06.05 High Ground and Inland Evacuation",
                [
                    "tsunami move to high ground inland",
                    "tsunami evacuation high ground official",
                    "tsunami vertical evacuation guidance",
                ],
            ),

            (
                "06.06 Tsunami Evacuation Zones",
                [
                    "tsunami evacuation zone official guidance",
                    "tsunami hazard map evacuation zone",
                    "tsunami evacuation map safety",
                ],
            ),

            (
                "06.07 Tsunami Shelters",
                [
                    "tsunami evacuation shelter official",
                    "tsunami vertical evacuation building guidance",
                    "tsunami shelter emergency management",
                ],
            ),

            (
                "06.08 Multiple Waves",
                [
                    "tsunami multiple waves return after first wave",
                    "tsunami do not return after first wave",
                    "tsunami waves can continue hours official",
                ],
            ),

            (
                "06.09 Coastal and Marine Hazards",
                [
                    "tsunami coastal currents harbor danger",
                    "tsunami harbor dangerous currents official",
                    "tsunami boats harbor safety",
                ],
            ),

            (
                "06.10 Rivers and Estuaries",
                [
                    "tsunami rivers estuaries inland flooding",
                    "tsunami river evacuation safety",
                ],
            ),

            (
                "06.11 Tsunami From Aftershocks",
                [
                    "aftershock tsunami risk official",
                    "earthquake aftershock tsunami warning",
                    "tsunami aftershock coastal safety",
                ],
            ),

            (
                "06.12 Landslide Generated Tsunami",
                [
                    "landslide tsunami official safety",
                    "earthquake landslide generated tsunami",
                ],
            ),

            (
                "06.13 What NOT To Do",
                [
                    "tsunami safety do not return coast",
                    "tsunami safety mistakes official",
                    "tsunami evacuation do not wait warning",
                ],
            ),

            (
                "06.14 Post-Tsunami Safety",
                [
                    "after tsunami safety debris contaminated water",
                    "return after tsunami official guidance",
                    "post tsunami hazards safety",
                ],
            ),

            (
                "06.15 Children and Vulnerable People",
                [
                    "tsunami evacuation children elderly disability",
                    "tsunami evacuation people with disabilities",
                ],
            ),

            (
                "06.16 Tsunami Warning Centers",
                [
                    "international tsunami warning centers official",
                    "regional tsunami warning center information",
                    "tsunami warning center official",
                ],
            ),

            (
                "06.17 Country-Specific Tsunami Information",
                [
                    "Japan tsunami safety official",
                    "Korea tsunami safety official",
                    "Indonesia tsunami safety official",
                    "United States tsunami safety official",
                ],
            ),
        ],
    },


    # ========================================================
    # 07 AFTERSHOCKS
    # ========================================================

    "07_aftershocks": {

        "title": "07. AFTERSHOCKS",

        "description": (
            "Aftershock behavior, safety during additional shaking, "
            "damaged structures, and aftershock risk communication."
        ),

        "sections": [

            (
                "07.01 What Is an Aftershock",
                [
                    "USGS what is an aftershock",
                    "aftershock definition official",
                    "earthquake aftershock sequence official",
                ],
            ),

            (
                "07.02 Aftershock Sequence",
                [
                    "aftershock sequence earthquake official",
                    "earthquake aftershock sequence days weeks months",
                ],
            ),

            (
                "07.03 Aftershock Probability",
                [
                    "aftershock probability official",
                    "aftershock forecast official",
                    "earthquake probability larger aftershock USGS",
                ],
            ),

            (
                "07.04 Foreshock vs Aftershock",
                [
                    "foreshock aftershock difference USGS",
                    "earthquake cannot know foreshock beforehand",
                ],
            ),

            (
                "07.05 What To Do During an Aftershock",
                [
                    "what to do during aftershock",
                    "earthquake aftershock drop cover hold on",
                    "aftershock safety official",
                ],
            ),

            (
                "07.06 Damaged Buildings",
                [
                    "aftershock damaged building safety",
                    "do not enter damaged building earthquake",
                    "earthquake damaged building aftershock risk",
                ],
            ),

            (
                "07.07 Secondary Collapse Risk",
                [
                    "aftershock secondary building collapse risk",
                    "earthquake damaged structure collapse aftershock",
                ],
            ),

            (
                "07.08 Falling Objects",
                [
                    "aftershock falling objects safety",
                    "earthquake aftershock falling debris",
                ],
            ),

            (
                "07.09 Fire Gas and Electrical Hazards",
                [
                    "earthquake aftershock gas electrical fire hazards",
                    "aftershock utility hazards official",
                ],
            ),

            (
                "07.10 Landslides and Rockfalls",
                [
                    "aftershock landslide risk official",
                    "earthquake aftershock rockfall hazard",
                ],
            ),

            (
                "07.11 Tsunami Risk After Aftershock",
                [
                    "aftershock tsunami risk official",
                    "aftershock coastal tsunami safety",
                ],
            ),

            (
                "07.12 Re-Entering Buildings",
                [
                    "earthquake when safe to reenter building",
                    "aftershock building reentry official",
                    "earthquake damaged building inspection",
                ],
            ),

            (
                "07.13 Aftershock Forecasts",
                [
                    "USGS aftershock forecast",
                    "aftershock forecast earthquake official",
                    "aftershock forecast limitations",
                ],
            ),

            (
                "07.14 Aftershock Communication",
                [
                    "earthquake aftershock emergency communication",
                    "aftershock official information monitoring",
                ],
            ),

            (
                "07.15 Psychological Response",
                [
                    "aftershock anxiety stress emergency guidance",
                    "earthquake aftershock psychological support",
                ],
            ),
        ],
    },


    # ========================================================
    # 08 TRAPPED PERSON
    # ========================================================

    "08_trapped_person": {

        "title": "08. TRAPPED PERSON / COLLAPSED STRUCTURE",

        "description": (
            "Safety and emergency communication guidance for people "
            "trapped by earthquake debris or collapsed structures."
        ),

        "sections": [

            (
                "08.01 Immediate Scene Safety",
                [
                    "earthquake collapsed building scene safety",
                    "collapsed structure emergency safety official",
                    "earthquake rubble rescue safety",
                ],
            ),

            (
                "08.02 Secondary Collapse",
                [
                    "collapsed building secondary collapse risk",
                    "earthquake rubble secondary collapse safety",
                    "unstable building rescue safety",
                ],
            ),

            (
                "08.03 Calling Emergency Services",
                [
                    "trapped earthquake person call emergency services",
                    "collapsed building emergency rescue call",
                    "earthquake rescue emergency information",
                ],
            ),

            (
                "08.04 Reporting Location",
                [
                    "trapped person report location rescuers",
                    "collapsed building rescue location information",
                    "earthquake trapped person GPS location",
                ],
            ),

            (
                "08.05 Communicating With Rescuers",
                [
                    "trapped earthquake communicate rescuers",
                    "collapsed building trapped survivor signaling",
                    "trapped person signal rescue official",
                ],
            ),

            (
                "08.06 Conserving Phone Battery",
                [
                    "trapped earthquake conserve phone battery",
                    "emergency trapped person phone battery",
                    "disaster communication battery conservation",
                ],
            ),

            (
                "08.07 Text Messages",
                [
                    "earthquake emergency text message trapped person",
                    "disaster emergency texting when phone calls fail",
                ],
            ),

            (
                "08.08 Signaling for Help",
                [
                    "trapped earthquake signal for help",
                    "collapsed building bang pipe signal rescuers",
                    "earthquake trapped person whistle signaling",
                ],
            ),

            (
                "08.09 Dust and Airway Protection",
                [
                    "collapsed building dust inhalation trapped survivor",
                    "earthquake rubble dust airway protection",
                    "trapped person dust mask emergency",
                ],
            ),

            (
                "08.10 Injury While Trapped",
                [
                    "trapped earthquake injured person first aid",
                    "collapsed building bleeding trapped person",
                    "trapped person fracture earthquake",
                ],
            ),

            (
                "08.11 Crush Injury",
                [
                    "earthquake crush injury trapped person official",
                    "crush injury collapsed building emergency",
                    "crush syndrome disaster rescue",
                ],
            ),

            (
                "08.12 Fire Gas Smoke and Electrical Hazards",
                [
                    "collapsed building gas leak fire electrical hazard",
                    "earthquake trapped person smoke gas danger",
                ],
            ),

            (
                "08.13 Flooding and Water Intrusion",
                [
                    "collapsed building flooding trapped survivor",
                    "earthquake trapped person water hazard",
                ],
            ),

            (
                "08.14 Do Not Attempt Dangerous Rescue",
                [
                    "earthquake rubble rescue do not enter unstable building",
                    "untrained person collapsed building rescue danger",
                    "earthquake rescue safety professional responders",
                ],
            ),

            (
                "08.15 Multiple Trapped People",
                [
                    "collapsed building multiple trapped people emergency",
                    "earthquake trapped survivors communication",
                ],
            ),

            (
                "08.16 Children and Vulnerable People",
                [
                    "trapped child earthquake rescue safety",
                    "earthquake trapped elderly disabled rescue",
                ],
            ),

            (
                "08.17 Rescue Team Arrival",
                [
                    "earthquake trapped survivor rescue team arrival",
                    "collapsed building rescue responder guidance",
                ],
            ),

            (
                "08.18 Post-Rescue Safety",
                [
                    "collapsed building survivor after rescue medical care",
                    "earthquake trapped person after rescue",
                ],
            ),
        ],
    },


    # ========================================================
    # 09 FAMILY REUNIFICATION
    # ========================================================

    "09_family_reunification": {

        "title": "09. FAMILY REUNIFICATION",

        "description": (
            "Emergency family communication, missing-person support, "
            "shelter registration, family tracing, and reunification."
        ),

        "sections": [

            (
                "09.01 Immediate Family Communication",
                [
                    "disaster family communication plan official",
                    "earthquake family emergency communication",
                    "emergency family contact earthquake",
                ],
            ),

            (
                "09.02 Check-In Messages",
                [
                    "disaster send text check in family",
                    "earthquake texting family communication",
                    "emergency communication text message",
                ],
            ),

            (
                "09.03 Communication Network Congestion",
                [
                    "disaster phone network congestion text messages",
                    "earthquake emergency communications overloaded network",
                ],
            ),

            (
                "09.04 Out-of-Area Emergency Contact",
                [
                    "family disaster out of area contact official",
                    "emergency family communication out of town contact",
                ],
            ),

            (
                "09.05 Family Meeting Points",
                [
                    "earthquake family meeting place disaster plan",
                    "emergency family reunification meeting point",
                ],
            ),

            (
                "09.06 Sharing Location",
                [
                    "disaster share location family safety",
                    "earthquake emergency location sharing",
                ],
            ),

            (
                "09.07 Missing Family Member",
                [
                    "disaster missing family member what to do",
                    "earthquake missing loved one official",
                    "missing person disaster response",
                ],
            ),

            (
                "09.08 Missing Children",
                [
                    "disaster missing child family reunification",
                    "earthquake separated child guardian reunification",
                    "child separated disaster official",
                ],
            ),

            (
                "09.09 Shelters and Registration",
                [
                    "disaster shelter family reunification registration",
                    "earthquake evacuation shelter missing family",
                    "emergency shelter registration disaster",
                ],
            ),

            (
                "09.10 Hospitals and Medical Facilities",
                [
                    "earthquake missing person check hospitals",
                    "disaster family member hospital search",
                    "missing person disaster hospitals",
                ],
            ),

            (
                "09.11 Police and Official Missing Person Services",
                [
                    "disaster missing person police report",
                    "earthquake missing person official reporting",
                    "missing person emergency disaster police",
                ],
            ),

            (
                "09.12 Red Cross Family Reunification",
                [
                    "Red Cross disaster family reunification",
                    "Red Cross missing loved one disaster",
                    "Restoring Family Links disaster",
                ],
            ),

            (
                "09.13 International Family Tracing",
                [
                    "international disaster family tracing Red Cross",
                    "ICRC Restoring Family Links disaster",
                    "cross border family reunification disaster",
                ],
            ),

            (
                "09.14 Privacy and Personal Information",
                [
                    "missing person disaster privacy personal information",
                    "family reunification disaster privacy",
                    "disaster missing person information safety",
                ],
            ),

            (
                "09.15 False Missing Person Information",
                [
                    "disaster misinformation missing persons social media",
                    "missing person disaster misinformation official",
                    "earthquake missing people false information",
                ],
            ),

            (
                "09.16 Scams and Fraud",
                [
                    "disaster family reunification scams",
                    "missing person disaster scam warning",
                    "earthquake disaster fraud missing family",
                ],
            ),

            (
                "09.17 Communication With Children",
                [
                    "disaster separated child family reunification guidance",
                    "earthquake child separated from parents safety",
                ],
            ),

            (
                "09.18 Family Reunification After Evacuation",
                [
                    "evacuation separated family reunification shelter",
                    "earthquake evacuation family reunification",
                ],
            ),
        ],
    },
}


# ============================================================
# OFFICIAL SOURCE PRIORITY
# ============================================================

AUTHORITY_RULES = {

    # International / intergovernmental
    "who.int": 100,
    "unesco.org": 100,
    "ioc.unesco.org": 100,
    "ifrc.org": 100,
    "icrc.org": 100,
    "un.org": 100,

    # United States
    "usgs.gov": 100,
    "earthquake.usgs.gov": 100,
    "noaa.gov": 100,
    "tsunami.gov": 100,
    "fema.gov": 100,
    "ready.gov": 100,
    "weather.gov": 100,

    # Korea
    "kma.go.kr": 100,
    "safekorea.go.kr": 100,
    "nfa.go.kr": 100,
    "police.go.kr": 100,
    "gov.kr": 95,
    "korea.kr": 95,

    # Japan
    "jma.go.jp": 100,
    "bousai.go.jp": 100,

    # Australia
    "ga.gov.au": 100,
    "bom.gov.au": 100,

    # Indonesia
    "bmkg.go.id": 100,
    "bnpb.go.id": 100,

    # New Zealand
    "geonet.org.nz": 100,
    "civildefence.govt.nz": 100,

    # Canada
    "canada.ca": 100,
    "earthquakescanada.nrcan.gc.ca": 100,

    # United Kingdom
    "gov.uk": 100,

    # General government
    ".gov": 90,
    ".gov.uk": 90,
    ".gouv.fr": 90,
    ".go.jp": 90,
    ".go.kr": 90,
    ".go.id": 90,
    ".gov.au": 90,
    ".govt.nz": 90,

    # Universities
    ".edu": 70,
    ".ac.uk": 70,
}


# ============================================================
# SOURCE AUTHORITY
# ============================================================

def authority_score(url: str) -> int:

    hostname = urlparse(url).hostname or ""

    hostname = hostname.lower()

    best = 0

    for domain, score in AUTHORITY_RULES.items():

        if hostname == domain:
            best = max(best, score)

        elif hostname.endswith(domain):
            best = max(best, score)

    return best


def source_type(score: int) -> str:

    if score >= 100:
        return "Official government / international organization"

    if score >= 90:
        return "Government"

    if score >= 70:
        return "Academic / educational"

    if score >= 40:
        return "Secondary source"

    return "Unverified / low authority"


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


def cache_file(url: str) -> Path:

    return (
        CACHE_DIR
        / f"{sha256(url)}.cache"
    )


def polite_delay():

    time.sleep(
        random.uniform(
            MIN_DELAY,
            MAX_DELAY,
        )
    )


# ============================================================
# URL FILTER
# ============================================================

def should_accept_url(url: str) -> bool:

    score = authority_score(url)

    # For emergency material, prefer authoritative sources.
    # However, allow lower authority if search engines find
    # something potentially useful.
    return score >= 40


# ============================================================
# SEARCH
# ============================================================

def search_web(query: str) -> list[dict]:

    if DDGS is None:

        logger.error(
            "ddgs is not installed."
        )

        return []

    logger.info(
        "Searching: %s",
        query,
    )

    results = []

    try:

        with DDGS() as ddgs:

            search_results = ddgs.text(
                query,
                max_results=MAX_SEARCH_RESULTS,
            )

            for result in search_results:

                url = result.get(
                    "href",
                    "",
                )

                title = clean_text(
                    result.get(
                        "title",
                        "",
                    )
                )

                snippet = clean_text(
                    result.get(
                        "body",
                        "",
                    )
                )

                if not url:
                    continue

                if not should_accept_url(
                    url
                ):
                    logger.debug(
                        "Rejected low-authority result: %s",
                        url,
                    )
                    continue

                results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                })

    except Exception as exc:

        logger.warning(
            "Search failed: %s",
            exc,
        )

        return []

    polite_delay()

    return results


# ============================================================
# DOWNLOAD
# ============================================================

def download(url: str) -> bytes | None:

    cache = cache_file(url)

    if cache.exists():

        try:

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
                "Downloading %s "
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

            if status in (
                401,
                403,
                451,
            ):

                logger.warning(
                    "Access denied: HTTP %s: %s",
                    status,
                    url,
                )

                return None

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
                    "Temporary HTTP %s. "
                    "Waiting %.1f seconds.",
                    status,
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
                    "Cache write failed: %s",
                    exc,
                )

            polite_delay()

            return data

        except requests.RequestException as exc:

            last_error = exc

            logger.warning(
                "Download failed: %s",
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
        "Could not download %s: %s",
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

    # Remove things that aren't useful for RAG.
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

    # Prefer article/main content.
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

        line = clean_text(line)

        if not line:
            continue

        lines.append(line)

    text = "\n".join(lines)

    return text[:MAX_TEXT_CHARS_PER_SOURCE]


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

    except Exception:
        return ""

    pages = []

    for page in reader.pages:

        try:

            text = page.extract_text()

            if text:
                pages.append(text)

        except Exception as exc:

            logger.debug(
                "PDF page extraction failed: %s",
                exc,
            )

    text = "\n".join(pages)

    text = clean_text(text)

    return text[:MAX_TEXT_CHARS_PER_SOURCE]


# ============================================================
# SOURCE CONTENT
# ============================================================

def get_content(
    url: str,
    data: bytes,
) -> str:

    lower = url.lower()

    if (
        lower.endswith(".pdf")
        or b"%PDF" in data[:10]
    ):

        return extract_pdf(data)

    return extract_html(data)


# ============================================================
# SOURCE DEDUPLICATION
# ============================================================

def normalize_url(url: str) -> str:

    parsed = urlparse(url)

    return (
        parsed.scheme.lower()
        + "://"
        + parsed.netloc.lower()
        + parsed.path.rstrip("/")
    )


def is_duplicate_source(
    existing: list[Source],
    new_url: str,
    content: str,
) -> bool:

    normalized = normalize_url(
        new_url
    )

    content_hash = sha256(
        content[:10000]
    )

    for source in existing:

        if (
            normalize_url(source.url)
            == normalized
        ):
            return True

        if sha256(
            source.content[:10000]
        ) == content_hash:

            return True

    return False


# ============================================================
# SOURCE COLLECTION
# ============================================================

def collect_sources_for_section(
    topic_key: str,
    subsection: str,
    queries: list[str],
) -> list[Source]:

    collected = []

    logger.info("")
    logger.info("=" * 70)
    logger.info(
        "%s | %s",
        topic_key,
        subsection,
    )
    logger.info("=" * 70)

    # Search each query.
    for query in queries:

        results = search_web(
            query
        )

        for result in results:

            url = result["url"]

            if is_duplicate_source(
                collected,
                url,
                result["snippet"],
            ):

                continue

            score = authority_score(
                url
            )

            # Only download reasonably useful sources.
            if score < 40:
                continue

            data = download(
                url
            )

            if not data:
                continue

            content = get_content(
                url,
                data,
            )

            if not content:
                logger.warning(
                    "No readable text: %s",
                    url,
                )

                continue

            if is_duplicate_source(
                collected,
                url,
                content,
            ):

                continue

            source = Source(
                topic=topic_key,
                subsection=subsection,
                title=result["title"],
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

            collected.append(
                source
            )

            logger.info(
                "Accepted source "
                "(score=%d): %s",
                score,
                url,
            )

            if (
                len(collected)
                >= MAX_SOURCES_PER_SUBSECTION
            ):
                break

        if (
            len(collected)
            >= MAX_SOURCES_PER_SUBSECTION
        ):
            break

    # Highest authority first.
    collected.sort(
        key=lambda s: (
            -s.authority_score,
            len(s.content),
        )
    )

    return collected


# ============================================================
# WRITE OUTPUT
# ============================================================

def write_topic_file(
    topic_key: str,
    topic_data: dict,
    all_sources: list[Source],
):

    output = (
        DOCS_DIR
        / f"{topic_key}.txt"
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
            topic_data["title"]
            + "\n"
        )

        f.write(
            "=" * 80
            + "\n\n"
        )

        f.write(
            "PURPOSE\n"
        )

        f.write(
            topic_data[
                "description"
            ]
            + "\n\n"
        )

        f.write(
            "IMPORTANT RAG SAFETY RULE\n"
        )

        f.write(
            "This document contains relatively static "
            "emergency preparedness and response guidance. "
            "It must not be used as the sole source for "
            "current emergency status. Current tsunami "
            "warnings, earthquake activity, evacuation "
            "orders, shelter availability, rescue status, "
            "and missing-person information should be "
            "retrieved from current official sources.\n\n"
        )

        f.write(
            f"COLLECTED: {utc_now()}\n"
        )

        f.write(
            f"SOURCES: {len(all_sources)}\n\n"
        )

        # Group by subsection.
        grouped = {}

        for source in all_sources:

            grouped.setdefault(
                source.subsection,
                [],
            ).append(source)

        for subsection, sources in grouped.items():

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

            for index, source in enumerate(
                sources,
                start=1,
            ):

                f.write(
                    "-" * 70
                    + "\n"
                )

                f.write(
                    f"SOURCE {index}\n"
                )

                f.write(
                    f"TITLE: {source.title}\n"
                )

                f.write(
                    f"URL: {source.url}\n"
                )

                f.write(
                    f"DOMAIN: {source.domain}\n"
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
                    f"{source.retrieved_at}\n"
                )

                f.write(
                    "\n"
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

    logger.info(
        "Written: %s",
        output,
    )


# ============================================================
# WRITE ERRORS
# ============================================================

def write_errors(
    topic_key: str,
    errors: list[str],
):

    output = (
        DOCS_DIR
        / f"{topic_key}_errors.txt"
    )

    with output.open(
        "w",
        encoding="utf-8",
    ) as f:

        f.write(
            f"{topic_key.upper()} ERRORS\n"
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
    topic_key: str,
    sources: list[Source],
):

    output = (
        DOCS_DIR
        / f"{topic_key}_quality.txt"
    )

    total = len(sources)

    official = sum(
        1
        for s in sources
        if s.authority_score >= 90
    )

    academic = sum(
        1
        for s in sources
        if 70 <= s.authority_score < 90
    )

    secondary = sum(
        1
        for s in sources
        if s.authority_score < 70
    )

    with output.open(
        "w",
        encoding="utf-8",
    ) as f:

        f.write(
            f"QUALITY REPORT — {topic_key}\n"
        )

        f.write(
            "=" * 70
            + "\n\n"
        )

        f.write(
            f"Total sources: {total}\n"
        )

        f.write(
            f"Official / international: "
            f"{official}\n"
        )

        f.write(
            f"Academic / educational: "
            f"{academic}\n"
        )

        f.write(
            f"Secondary / other: "
            f"{secondary}\n\n"
        )

        f.write(
            "RECOMMENDATION\n"
        )

        if total == 0:

            f.write(
                "NO SOURCES COLLECTED. "
                "Do not use this module.\n"
            )

        elif official == 0:

            f.write(
                "WARNING: No high-authority sources "
                "were collected. Review manually.\n"
            )

        else:

            f.write(
                "At least one high-authority source "
                "was collected. Manual review is still "
                "recommended before production use.\n"
            )


# ============================================================
# RUN ONE TOPIC
# ============================================================

def run_topic(
    topic_key: str,
    topic_data: dict,
):

    logger.info("")
    logger.info(
        "########################################################"
    )

    logger.info(
        "STARTING %s",
        topic_data["title"],
    )

    logger.info(
        "########################################################"
    )

    all_sources = []

    errors = []

    for subsection, queries in (
        topic_data["sections"]
    ):

        try:

            sources = collect_sources_for_section(
                topic_key,
                subsection,
                queries,
            )

            if not sources:

                message = (
                    f"No sources found for "
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
                f"Failed subsection "
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

    # Sort.
    all_sources.sort(
        key=lambda s: (
            s.subsection,
            -s.authority_score,
            s.title.lower(),
        )
    )

    write_topic_file(
        topic_key,
        topic_data,
        all_sources,
    )

    write_errors(
        topic_key,
        errors,
    )

    write_quality_report(
        topic_key,
        all_sources,
    )

    logger.info(
        "%s completed: %d sources",
        topic_key,
        len(all_sources),
    )


# ============================================================
# MAIN
# ============================================================

def main():

    logger.info(
        "=" * 70
    )

    logger.info(
        "EARTHQUAKE HELPER — TOPICS 06–09"
    )

    logger.info(
        "=" * 70
    )

    logger.info(
        "Topics to collect: %d",
        len(TOPICS),
    )

    logger.info(
        "Output directory: %s",
        DOCS_DIR,
    )

    logger.info(
        "Cache directory: %s",
        CACHE_DIR,
    )

    logger.info(
        "WARNING: Collection may take a long time "
        "because polite delays are intentionally enabled."
    )

    for topic_key, topic_data in TOPICS.items():

        try:

            run_topic(
                topic_key,
                topic_data,
            )

        except Exception as exc:

            logger.exception(
                "TOPIC FAILED: %s",
                topic_key,
            )

            error_file = (
                DOCS_DIR
                / f"{topic_key}_errors.txt"
            )

            with error_file.open(
                "a",
                encoding="utf-8",
            ) as f:

                f.write(
                    "\n"
                    f"[{utc_now()}] "
                    f"FATAL TOPIC ERROR: "
                    f"{exc}\n"
                )

    logger.info("")
    logger.info(
        "=" * 70
    )

    logger.info(
        "ALL TOPICS FINISHED"
    )

    logger.info(
        "=" * 70
    )

    logger.info(
        "Generated:"
    )

    for topic_key in TOPICS:

        logger.info(
            "  docs/%s.txt",
            topic_key,
        )


if __name__ == "__main__":
    main()