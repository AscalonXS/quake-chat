"""
Earthquake Helper - Topic 03
Environmental Hazards Information Gatherer

Purpose:
    Search for authoritative earthquake/environmental hazard information,
    retrieve the relevant pages/PDFs, extract their text, and produce
    RAG-friendly TXT knowledge.

Output:
    docs/03_environmental_hazards.txt
    docs/03_environmental_hazards_errors.txt
    cache/

Important:
    This is an information gathering tool, NOT a web crawler intended to
    bypass access controls.

    It:
      - uses search engines to discover relevant sources
      - retrieves publicly accessible pages
      - retries temporary server errors
      - caches successful downloads
      - extracts HTML and PDF text
      - scores source authority
      - preserves provenance
      - keeps lower-authority sources rather than silently discarding them

    It does NOT:
      - bypass CAPTCHA
      - bypass authentication
      - bypass robots/access restrictions
      - attempt credential attacks
      - circumvent 403/401/451 responses
"""

import os
import re
import time
import random
import hashlib
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

try:
    from ddgs import DDGS
except ImportError:
    print("Missing dependency: ddgs")
    print("Install with:")
    print("    pip install ddgs")
    raise


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DOCS_DIR = os.path.join(BASE_DIR, "docs")
CACHE_DIR = os.path.join(BASE_DIR, "cache")

OUTPUT_FILE = os.path.join(
    DOCS_DIR,
    "03_environmental_hazards.txt"
)

ERROR_FILE = os.path.join(
    DOCS_DIR,
    "03_environmental_hazards_errors.txt"
)

os.makedirs(DOCS_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)


# ------------------------------------------------------------
# Network behavior
# ------------------------------------------------------------

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

MAX_SOURCES_PER_SECTION = 6

MAX_CONTENT_CHARS_PER_SOURCE = 50000


# ------------------------------------------------------------
# HTTP headers
# ------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/157.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,"
        "application/pdf;q=0.8,"
        "*/*;q=0.7"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}


# ============================================================
# TOPIC STRUCTURE
# ============================================================

RESEARCH_SECTIONS = [
    (
        "03.01",
        "Structural Collapse and Falling Debris",
        [
            "earthquake structural collapse falling debris safety",
            "earthquake damaged buildings falling objects safety",
            "earthquake debris hazards emergency safety",
        ],
    ),

    (
        "03.02",
        "Aftershocks and Secondary Collapse",
        [
            "earthquake aftershocks damaged buildings secondary collapse",
            "earthquake aftershock safety damaged structures",
            "aftershock building collapse hazards",
        ],
    ),

    (
        "03.03",
        "Gas Leaks and Natural Gas Hazards",
        [
            "earthquake gas leak natural gas safety",
            "earthquake smell gas what to do",
            "earthquake damaged gas lines emergency safety",
        ],
    ),

    (
        "03.04",
        "Electrical Hazards and Downed Power Lines",
        [
            "earthquake downed power lines electrical hazards",
            "earthquake electrical safety damaged wiring",
            "earthquake fallen power lines safety",
        ],
    ),

    (
        "03.05",
        "Fire and Explosion Hazards",
        [
            "earthquake fire explosion hazards safety",
            "earthquake fires gas explosion emergency",
            "earthquake fire prevention damaged buildings",
        ],
    ),

    (
        "03.06",
        "Water Leaks and Flooding",
        [
            "earthquake broken water pipes flooding safety",
            "earthquake water leak building safety",
            "earthquake flooding infrastructure damage",
        ],
    ),

    (
        "03.07",
        "Damaged Roads Bridges and Tunnels",
        [
            "earthquake damaged roads bridges tunnels safety",
            "earthquake bridge collapse road hazards",
            "earthquake transportation infrastructure damage",
        ],
    ),

    (
        "03.08",
        "Landslides and Rockfalls",
        [
            "earthquake landslide rockfall hazards safety",
            "earthquake slope failure landslide emergency",
            "earthquake rockfall road safety",
        ],
    ),

    (
        "03.09",
        "Tsunami and Coastal Hazards",
        [
            "earthquake tsunami coastal safety evacuation",
            "earthquake tsunami warning signs safety",
            "earthquake coastal flooding tsunami emergency",
        ],
    ),

    (
        "03.10",
        "Hazardous Materials and Chemical Releases",
        [
            "earthquake hazardous materials chemical spill safety",
            "earthquake chemical release emergency response",
            "earthquake industrial chemical hazards",
        ],
    ),

    (
        "03.11",
        "Sewage and Contaminated Water",
        [
            "earthquake sewage contamination water safety",
            "earthquake contaminated drinking water",
            "earthquake wastewater damage health hazards",
        ],
    ),

    (
        "03.12",
        "Broken Glass and Sharp Debris",
        [
            "earthquake broken glass sharp debris safety",
            "earthquake debris cleanup safety",
            "earthquake broken windows injury prevention",
        ],
    ),

    (
        "03.13",
        "Dust and Airborne Particles",
        [
            "earthquake dust airborne particles safety",
            "earthquake building collapse dust inhalation",
            "earthquake debris dust respiratory hazard",
        ],
    ),

    (
        "03.14",
        "Carbon Monoxide",
        [
            "earthquake carbon monoxide safety generators",
            "earthquake carbon monoxide poisoning emergency",
            "earthquake generator indoor carbon monoxide",
        ],
    ),

    (
        "03.15",
        "Unsafe Buildings and Re-entry",
        [
            "earthquake unsafe building reentry safety",
            "earthquake damaged building do not enter",
            "earthquake building inspection reentry",
        ],
    ),

    (
        "03.16",
        "Elevators and Entrapment Hazards",
        [
            "earthquake elevator safety trapped elevator",
            "earthquake elevator emergency safety",
            "earthquake damaged elevator do not use",
        ],
    ),

    (
        "03.17",
        "Transportation Hazards",
        [
            "earthquake transportation hazards vehicles roads",
            "earthquake driving safety damaged roads",
            "earthquake public transportation emergency safety",
        ],
    ),

    (
        "03.18",
        "Industrial and Construction Site Hazards",
        [
            "earthquake construction site hazards",
            "earthquake industrial facility safety hazards",
            "earthquake construction equipment collapse hazards",
        ],
    ),

    (
        "03.19",
        "Winter and Cold-Weather Hazards",
        [
            "earthquake winter cold weather emergency hazards",
            "earthquake hypothermia cold weather disaster",
            "earthquake winter power outage safety",
        ],
    ),

    (
        "03.20",
        "Extreme Heat After Earthquake",
        [
            "earthquake extreme heat emergency safety",
            "earthquake heat illness disaster response",
            "earthquake heat wave emergency shelter safety",
        ],
    ),

    (
        "03.21",
        "Biological and Sanitation Hazards",
        [
            "earthquake sanitation biological hazards emergency",
            "earthquake disease sanitation disaster response",
            "earthquake hygiene waste sanitation safety",
        ],
    ),

    (
        "03.22",
        "Animals and Wildlife Hazards",
        [
            "earthquake animals wildlife hazards safety",
            "earthquake displaced animals emergency safety",
            "earthquake wildlife encounters disaster",
        ],
    ),

    (
        "03.23",
        "Secondary Fires",
        [
            "earthquake secondary fires safety",
            "earthquake post earthquake fire hazards",
            "earthquake fires after shaking emergency",
        ],
    ),

    (
        "03.24",
        "Hazardous Infrastructure",
        [
            "earthquake damaged infrastructure hazards",
            "earthquake utilities infrastructure safety",
            "earthquake bridges pipelines power infrastructure hazards",
        ],
    ),

    (
        "03.25",
        "Environmental Hazard Warning Signs",
        [
            "earthquake environmental hazard warning signs",
            "earthquake danger signs evacuation",
            "earthquake hazardous conditions warning signs",
        ],
    ),

    (
        "03.26",
        "When to Evacuate",
        [
            "earthquake when to evacuate emergency safety",
            "earthquake evacuation guidance official",
            "earthquake evacuation warning signs",
        ],
    ),

    (
        "03.27",
        "When NOT to Enter an Area",
        [
            "earthquake areas unsafe do not enter",
            "earthquake damaged building restricted area",
            "earthquake hazardous area exclusion zone safety",
        ],
    ),

    (
        "03.28",
        "Reporting Environmental Hazards",
        [
            "earthquake report gas leak downed power line hazards",
            "earthquake report damaged infrastructure emergency",
            "earthquake emergency hazard reporting authorities",
        ],
    ),
]


# ============================================================
# AUTHORITY SCORING
# ============================================================

HIGH_AUTHORITY_DOMAINS = {
    "usgs.gov": 10,
    "fema.gov": 10,
    "ready.gov": 10,
    "cdc.gov": 10,
    "epa.gov": 10,
    "osha.gov": 10,
    "noaa.gov": 10,
    "weather.gov": 10,
    "redcross.org": 9,
    "who.int": 10,
    "un.org": 9,
    "ifrc.org": 9,

    # Korea
    "safekorea.go.kr": 10,
    "korea.kr": 9,
    "mois.go.kr": 10,
    "kma.go.kr": 10,
    "korea.kr": 9,
    "nfa.go.kr": 10,
    "119.go.kr": 10,
    "keco.or.kr": 9,
}

MEDIUM_AUTHORITY_DOMAIN_SUFFIXES = [
    ".gov",
    ".go.kr",
    ".ac.kr",
    ".edu",
    ".edu.kr",
    ".ac.uk",
    ".int",
]


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("environmental_hazards")


def log_error(message):
    timestamp = datetime.now(timezone.utc).isoformat()

    with open(
        ERROR_FILE,
        "a",
        encoding="utf-8"
    ) as f:
        f.write(
            f"[{timestamp}] {message}\n"
        )


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def normalize_url(url):
    """
    Remove tracking parameters and normalize URLs.
    """

    if not url:
        return ""

    url = url.strip()

    url = re.sub(
        r"[?&](utm_[^&]+|fbclid|gclid)=[^&]*",
        "",
        url,
        flags=re.IGNORECASE
    )

    return url.rstrip("/")


def domain_from_url(url):
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def authority_score(url):
    """
    Give a rough authority score.

    This does NOT mean:
        10 = guaranteed correct
        0 = false

    It is only a source-priority signal.
    """

    domain = domain_from_url(url)

    if domain.startswith("www."):
        domain = domain[4:]

    if domain in HIGH_AUTHORITY_DOMAINS:
        return HIGH_AUTHORITY_DOMAINS[domain]

    for suffix in MEDIUM_AUTHORITY_DOMAIN_SUFFIXES:
        if domain.endswith(suffix):
            return 7

    return 3


def source_category(url):
    domain = domain_from_url(url)

    if (
        domain.endswith(".gov")
        or domain.endswith(".go.kr")
        or domain in HIGH_AUTHORITY_DOMAINS
    ):
        return "government / public authority"

    if (
        domain.endswith(".edu")
        or domain.endswith(".ac.kr")
        or domain.endswith(".ac.uk")
    ):
        return "academic"

    if domain.endswith(".int"):
        return "international organization"

    if "redcross.org" in domain or "ifrc.org" in domain:
        return "humanitarian organization"

    return "general web source"


def clean_text(text):
    """
    Normalize extracted text while preserving useful paragraph structure.
    """

    if not text:
        return ""

    text = text.replace("\xa0", " ")

    # Remove excessive spaces
    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    # Collapse excessive blank lines
    text = re.sub(
        r"\n\s*\n\s*\n+",
        "\n\n",
        text
    )

    return text.strip()


def content_hash(text):
    return hashlib.sha256(
        text.encode("utf-8", errors="ignore")
    ).hexdigest()


def url_cache_path(url):
    digest = hashlib.sha256(
        url.encode("utf-8")
    ).hexdigest()

    return os.path.join(
        CACHE_DIR,
        digest + ".txt"
    )


def sleep_polite():
    delay = random.uniform(
        MIN_DELAY,
        MAX_DELAY
    )

    logger.info(
        "Waiting %.1f seconds before next request...",
        delay
    )

    time.sleep(delay)


# ============================================================
# SESSION
# ============================================================

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# CACHE
# ============================================================

def load_cache(url):
    path = url_cache_path(url)

    if not os.path.exists(path):
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
            f"Cache read failed: {url} | {e}"
        )

        return None


def save_cache(url, text):
    path = url_cache_path(url)

    try:
        with open(
            path,
            "w",
            encoding="utf-8"
        ) as f:
            f.write(text)

    except Exception as e:
        log_error(
            f"Cache write failed: {url} | {e}"
        )


# ============================================================
# HTML EXTRACTION
# ============================================================

def extract_html(html):
    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    # Remove things that are generally not useful
    # to a RAG knowledge base.
    for tag in soup([
        "script",
        "style",
        "noscript",
        "svg",
        "nav",
        "footer",
        "header",
        "form",
        "aside",
    ]):
        tag.decompose()

    # Prefer main article-like containers.
    candidates = []

    for selector in [
        "main",
        "article",
        "[role='main']",
        ".content",
        ".main-content",
        "#content",
        "#main-content",
    ]:
        candidates.extend(
            soup.select(selector)
        )

    if candidates:
        # Select the largest candidate.
        element = max(
            candidates,
            key=lambda x: len(x.get_text(" ", strip=True))
        )
    else:
        element = soup.body or soup

    text = element.get_text(
        "\n",
        strip=True
    )

    return clean_text(text)


# ============================================================
# PDF EXTRACTION
# ============================================================

def extract_pdf(content):
    temp_path = os.path.join(
        CACHE_DIR,
        "_temporary_pdf.pdf"
    )

    try:
        with open(
            temp_path,
            "wb"
        ) as f:
            f.write(content)

        reader = PdfReader(temp_path)

        pages = []

        for page_number, page in enumerate(
            reader.pages,
            start=1
        ):
            try:
                page_text = page.extract_text()

                if page_text:
                    pages.append(
                        f"\n[PDF PAGE {page_number}]\n"
                        f"{page_text}"
                    )

            except Exception as e:
                log_error(
                    f"PDF page extraction failed "
                    f"page={page_number} | {e}"
                )

        return clean_text(
            "\n".join(pages)
        )

    finally:
        try:
            os.remove(temp_path)
        except Exception:
            pass


# ============================================================
# FETCH URL
# ============================================================

def fetch_url(url):
    """
    Retrieve a URL with retry handling.

    Explicit access restrictions are NOT bypassed.
    """

    url = normalize_url(url)

    cached = load_cache(url)

    if cached:
        logger.info(
            "Using cached copy: %s",
            url
        )

        return cached

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

            status = response.status_code

            # ------------------------------------------------
            # Successful response
            # ------------------------------------------------

            if status == 200:

                content_type = (
                    response.headers
                    .get("Content-Type", "")
                    .lower()
                )

                if (
                    "application/pdf"
                    in content_type
                    or url.lower().endswith(".pdf")
                ):

                    text = extract_pdf(
                        response.content
                    )

                else:

                    text = extract_html(
                        response.text
                    )

                text = clean_text(text)

                if not text:
                    raise RuntimeError(
                        "Page returned no extractable text."
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
            # Explicit access restriction
            # ------------------------------------------------

            if status in (
                401,
                403,
                451
            ):
                message = (
                    f"Access denied/restricted "
                    f"HTTP {status}: {url}"
                )

                logger.warning(
                    message
                )

                log_error(message)

                return None

            # ------------------------------------------------
            # Temporary errors
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
                    + random.uniform(1, 4)
                )

                logger.warning(
                    "Temporary HTTP %s. "
                    "Retrying in %.1f seconds...",
                    status,
                    wait_time
                )

                time.sleep(
                    wait_time
                )

                continue

            # ------------------------------------------------
            # Other HTTP errors
            # ------------------------------------------------

            message = (
                f"HTTP {status}: {url}"
            )

            logger.warning(
                message
            )

            log_error(message)

            return None

        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError
        ) as e:

            wait_time = min(
                60,
                (2 ** attempt)
                + random.uniform(1, 4)
            )

            logger.warning(
                "Temporary network error: %s",
                e
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
                f"Fetch failed: {url} | {repr(e)}"
            )

            logger.warning(
                message
            )

            log_error(message)

            return None

    log_error(
        f"Maximum retries exceeded: {url}"
    )

    return None


# ============================================================
# SEARCH
# ============================================================

def search_web(query):
    """
    Search the web for candidate sources.

    Search discovery is intentionally separated from retrieval.
    """

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
                    result.get("href", "")
                )

                if not url:
                    continue

                results.append({
                    "title": (
                        result.get("title")
                        or ""
                    ),
                    "url": url,
                    "snippet": (
                        result.get("body")
                        or ""
                    ),
                })

    except Exception as e:

        message = (
            f"Search failed: {query} | {repr(e)}"
        )

        logger.warning(
            message
        )

        log_error(message)

    return results


# ============================================================
# SOURCE SELECTION
# ============================================================

def rank_sources(results):
    """
    Rank discovered sources primarily by authority,
    then by whether the result has useful metadata.
    """

    seen_urls = set()

    ranked = []

    for result in results:

        url = normalize_url(
            result["url"]
        )

        if not url:
            continue

        if url in seen_urls:
            continue

        seen_urls.add(url)

        score = authority_score(
            url
        )

        result["authority_score"] = score
        result["domain"] = domain_from_url(url)
        result["category"] = source_category(url)

        ranked.append(result)

    ranked.sort(
        key=lambda x: (
            -x["authority_score"],
            x["url"]
        )
    )

    return ranked


# ============================================================
# DUPLICATE CONTENT DETECTION
# ============================================================

def remove_duplicate_sources(sources):
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

        source["content_hash"] = digest

        unique.append(
            source
        )

    return unique


# ============================================================
# COLLECT ONE SECTION
# ============================================================

def collect_section(
    section_id,
    section_name,
    queries
):
    logger.info("")
    logger.info("=" * 70)
    logger.info(
        "SECTION %s - %s",
        section_id,
        section_name
    )
    logger.info("=" * 70)

    discovered = []

    # --------------------------------------------------------
    # Search
    # --------------------------------------------------------

    for query in queries:

        results = search_web(
            query
        )

        discovered.extend(
            results
        )

        sleep_polite()

    # --------------------------------------------------------
    # Rank
    # --------------------------------------------------------

    ranked = rank_sources(
        discovered
    )

    # Limit retrieval.
    selected = ranked[
        :MAX_SOURCES_PER_SECTION
    ]

    logger.info(
        "Selected %d sources.",
        len(selected)
    )

    # --------------------------------------------------------
    # Retrieve
    # --------------------------------------------------------

    retrieved = []

    for source in selected:

        url = source["url"]

        logger.info(
            "Retrieving source: %s",
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

            sleep_polite()

            continue

        source["content"] = content

        retrieved.append(
            source
        )

        sleep_polite()

    # --------------------------------------------------------
    # Deduplicate
    # --------------------------------------------------------

    retrieved = remove_duplicate_sources(
        retrieved
    )

    return retrieved


# ============================================================
# OUTPUT FORMAT
# ============================================================

def write_section(
    output,
    section_id,
    section_name,
    sources
):

    output.write(
        "\n"
        + "=" * 90
        + "\n"
    )

    output.write(
        f"{section_id} {section_name}\n"
    )

    output.write(
        "=" * 90
        + "\n\n"
    )

    if not sources:

        output.write(
            "NO USABLE SOURCES FOUND.\n"
        )

        output.write(
            "This section requires manual research/review.\n\n"
        )

        return

    for index, source in enumerate(
        sources,
        start=1
    ):

        output.write(
            "-" * 80
            + "\n"
        )

        output.write(
            f"SOURCE {index}\n"
        )

        output.write(
            "-" * 80
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
            f"Source category: "
            f"{source.get('category', '')}\n"
        )

        output.write(
            f"Authority score: "
            f"{source.get('authority_score', 0)}/10\n"
        )

        output.write(
            f"Retrieved: "
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
            + "\n\n"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    logger.info("")
    logger.info("=" * 70)
    logger.info(
        "EARTHQUAKE HELPER - TOPIC 03"
    )
    logger.info(
        "ENVIRONMENTAL HAZARDS"
    )
    logger.info("=" * 70)
    logger.info("")

    # Start a fresh output file.
    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as output:

        output.write(
            "EARTHQUAKE HELPER\n"
        )

        output.write(
            "TOPIC 03 - ENVIRONMENTAL HAZARDS\n"
        )

        output.write(
            "=" * 90
            + "\n\n"
        )

        output.write(
            "PURPOSE\n"
        )

        output.write(
            "This document contains gathered information "
            "about environmental hazards associated with "
            "earthquakes and post-earthquake conditions.\n\n"
        )

        output.write(
            "IMPORTANT\n"
        )

        output.write(
            "This is a research/RAG source document. "
            "Emergency responses should prioritize current "
            "instructions from local emergency authorities "
            "and verified authoritative sources.\n\n"
        )

        output.write(
            f"Generated: "
            f"{datetime.now(timezone.utc).isoformat()}\n\n"
        )

        # ----------------------------------------------------
        # Collect every section
        # ----------------------------------------------------

        total_sources = 0

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
    logger.info("=" * 70)
    logger.info(
        "COLLECTION COMPLETE"
    )
    logger.info("=" * 70)

    logger.info(
        "Output: %s",
        OUTPUT_FILE
    )

    logger.info(
        "Total usable sources: %d",
        total_sources
    )

    logger.info(
        "Errors: %s",
        ERROR_FILE
    )


if __name__ == "__main__":
    main()