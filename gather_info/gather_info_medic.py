from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
import hashlib
import random
import re
import time

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from pypdf import PdfReader


# ============================================================
# CONFIGURATION
# ============================================================

TOPIC_ID = "02"
TOPIC_NAME = "Injuries and First Aid"

BASE_DIR = Path(__file__).resolve().parent.parent

DOCS_DIR = BASE_DIR / "docs"
CACHE_DIR = BASE_DIR / "cache"

OUTPUT_FILE = DOCS_DIR / "02_injuries_first_aid.txt"
ERROR_FILE = DOCS_DIR / "02_injuries_first_aid_errors.txt"

DOCS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# DOWNLOAD SETTINGS
# ============================================================

# Deliberately slow/polite.
MIN_DELAY = 3
MAX_DELAY = 8

MAX_RETRIES = 5

# Connection timeout, read timeout
REQUEST_TIMEOUT = (20, 120)

MAX_RESULTS_PER_QUERY = 8
MAX_SOURCES_PER_SECTION = 6

MAX_CHARS_PER_SOURCE = 15000
MIN_TEXT_LENGTH = 300


# ============================================================
# SOURCE AUTHORITY
# ============================================================

# Higher number = stronger source.
#
# IMPORTANT:
# These scores are used for ranking, NOT for rejecting
# search results.
#
# Therefore even an unknown source can be collected,
# but authoritative sources will appear first.

TRUSTED_DOMAINS = {

    # --------------------------------------------------------
    # International
    # --------------------------------------------------------

    "who.int": 10,
    "ilcor.org": 10,

    # --------------------------------------------------------
    # United States
    # --------------------------------------------------------

    "redcross.org": 10,
    "heart.org": 10,
    "cpr.heart.org": 10,
    "cdc.gov": 10,

    "fema.gov": 9,
    "ready.gov": 9,

    # --------------------------------------------------------
    # Korea
    # --------------------------------------------------------

    "safekorea.go.kr": 10,
    "korea.kr": 9,
    "kacpr.org": 9,

    # --------------------------------------------------------
    # United Kingdom
    # --------------------------------------------------------

    "nhs.uk": 9,
    "gov.uk": 9,

    # --------------------------------------------------------
    # Medical organizations
    # --------------------------------------------------------

    "mayoclinic.org": 8,
    "clevelandclinic.org": 8,
    "hopkinsmedicine.org": 8,
    "medlineplus.gov": 9,

    # --------------------------------------------------------
    # Universities
    # --------------------------------------------------------

    "harvard.edu": 8,
    "stanford.edu": 8,
    "ucla.edu": 8,
    "umich.edu": 8,
}


# ============================================================
# RESEARCH SECTIONS
# ============================================================

RESEARCH_SECTIONS = {

    "02.01 First Aid Priorities and Scene Safety": [
        "first aid scene safety injured person emergency response",
        "earthquake injured person first aid scene safety",
        "trauma first aid priorities emergency response",
    ],

    "02.02 Initial Assessment and Triage": [
        "first aid initial assessment ABCDE trauma",
        "trauma triage life threatening injuries first aid",
        "mass casualty earthquake injury triage",
    ],

    "02.03 Life-Threatening Bleeding": [
        "first aid life threatening bleeding direct pressure tourniquet",
        "severe bleeding first aid emergency",
        "trauma hemorrhage first aid",
    ],

    "02.04 Shock": [
        "first aid shock symptoms emergency treatment",
        "traumatic shock first aid",
        "hemorrhagic shock first aid emergency",
    ],

    "02.05 Unconsciousness": [
        "unconscious person first aid emergency",
        "unresponsive person first aid trauma",
        "loss of consciousness first aid",
    ],

    "02.06 Cardiac Arrest CPR and AED": [
        "adult CPR AED first aid guidelines",
        "cardiac arrest first aid CPR AED",
        "basic life support CPR AED guidelines",
    ],

    "02.07 Breathing Problems and Airway Obstruction": [
        "airway obstruction choking first aid adult",
        "breathing difficulty first aid emergency",
        "trauma airway emergency first aid",
    ],

    "02.08 Head Injury and Concussion": [
        "head injury concussion danger signs emergency",
        "traumatic brain injury first aid danger signs",
        "earthquake head injury emergency",
    ],

    "02.09 Neck and Spinal Injury": [
        "suspected spinal injury first aid do not move",
        "neck injury trauma first aid",
        "spinal injury emergency first aid",
    ],

    "02.10 Fractures": [
        "fracture broken bone first aid",
        "open fracture first aid emergency",
        "broken bone emergency first aid",
    ],

    "02.11 Dislocations": [
        "dislocation first aid do not put back",
        "joint dislocation emergency first aid",
    ],

    "02.12 Sprains and Strains": [
        "sprain strain first aid",
        "ankle sprain first aid emergency",
    ],

    "02.13 Cuts Lacerations and Puncture Wounds": [
        "cuts lacerations first aid wound care",
        "puncture wound first aid",
        "deep wound emergency first aid",
    ],

    "02.14 Crush Injuries": [
        "crush injury first aid emergency",
        "earthquake crush injury first aid",
        "crush syndrome disaster medicine",
    ],

    "02.15 Amputations": [
        "traumatic amputation first aid bleeding",
        "amputated limb emergency first aid",
    ],

    "02.16 Burns": [
        "burn first aid cool running water",
        "thermal burn first aid emergency",
        "earthquake fire burn injuries first aid",
    ],

    "02.17 Electrical Injuries": [
        "electrical injury first aid emergency",
        "electric shock first aid",
        "electrical burns emergency medical care",
    ],

    "02.18 Chemical Exposure": [
        "chemical burn first aid emergency",
        "chemical exposure first aid decontamination",
    ],

    "02.19 Eye Injuries": [
        "eye injury foreign object first aid",
        "chemical eye exposure first aid",
        "eye trauma emergency first aid",
    ],

    "02.20 Chest Injuries": [
        "chest injury trauma first aid emergency",
        "blunt chest trauma emergency signs",
        "penetrating chest injury first aid",
    ],

    "02.21 Abdominal Injuries": [
        "abdominal trauma first aid emergency",
        "blunt abdominal injury danger signs",
        "abdominal injury trauma emergency",
    ],

    "02.22 Nose and Mouth Bleeding": [
        "nosebleed first aid emergency",
        "mouth bleeding trauma first aid",
        "facial injury bleeding first aid",
    ],

    "02.23 Smoke Dust and Inhalation Injuries": [
        "smoke inhalation injury first aid",
        "dust inhalation earthquake emergency",
        "inhalation injury emergency signs",
    ],

    "02.24 Hypothermia and Cold Exposure": [
        "hypothermia first aid emergency",
        "cold exposure first aid",
        "disaster hypothermia emergency",
    ],

    "02.25 Heat Illness": [
        "heat exhaustion heat stroke first aid",
        "heat stroke emergency first aid",
    ],

    "02.26 Pain and Swelling": [
        "injury swelling pain first aid cold pack",
        "acute injury pain first aid",
    ],

    "02.27 Infection and Wound Care": [
        "wound cleaning infection prevention first aid",
        "open wound first aid infection",
        "puncture wound tetanus medical care",
    ],

    "02.28 Children": [
        "child injury first aid emergency",
        "pediatric trauma first aid",
        "child head injury emergency signs",
    ],

    "02.29 Older Adults": [
        "older adult falls injury first aid",
        "elderly trauma emergency first aid",
    ],

    "02.30 Pregnancy": [
        "pregnancy trauma emergency first aid",
        "pregnant person injury emergency",
        "pregnancy abdominal trauma emergency",
    ],

    "02.31 People With Disabilities": [
        "disability emergency first aid injured person",
        "accessible emergency response injured person",
    ],

    "02.32 When NOT to Move an Injured Person": [
        "trauma first aid do not move injured person",
        "suspected spinal injury do not move",
        "serious injury safe movement first aid",
    ],

    "02.33 When Emergency Medical Services Are Required": [
        "when to call emergency medical services serious injury",
        "life threatening injury emergency signs",
        "first aid emergency warning signs",
    ],

    "02.34 Earthquake Multiple-Injury Situations": [
        "earthquake mass casualty injuries first aid",
        "earthquake trauma crush burns bleeding",
        "disaster first aid multiple casualties",
    ],

    "02.35 Aftercare and Monitoring": [
        "head injury monitor symptoms after injury",
        "first aid monitoring injured person",
        "injury symptoms may appear later emergency",
    ],
}


# ============================================================
# HTTP SESSION
# ============================================================

session = requests.Session()

session.headers.update({

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
        "en-US,en;q=0.9,ko;q=0.8"
    ),

    "Connection": "keep-alive",

    "DNT": "1",
})


# ============================================================
# DOMAIN FUNCTIONS
# ============================================================

def get_domain(url):

    try:

        hostname = urlparse(url).hostname

        if not hostname:
            return ""

        hostname = hostname.lower()

        if hostname.startswith("www."):
            hostname = hostname[4:]

        return hostname

    except Exception:

        return ""


def domain_score(domain):

    # Exact match.

    if domain in TRUSTED_DOMAINS:

        return TRUSTED_DOMAINS[domain]

    # Subdomain.

    for trusted_domain, score in TRUSTED_DOMAINS.items():

        if domain.endswith(
            "." + trusted_domain
        ):

            return score

    # Government domains.

    if domain.endswith(".gov"):

        return 8

    if domain.endswith(".gov.uk"):

        return 8

    if domain.endswith(".go.kr"):

        return 8

    # Universities.

    if domain.endswith(".edu"):

        return 7

    if domain.endswith(".ac.uk"):

        return 7

    # Unknown sources are NOT rejected.

    return 3


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text):

    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    text = re.sub(
        r"\n\s*\n+",
        "\n\n",
        text
    )

    junk = [
        r"cookie policy",
        r"accept cookies",
        r"manage cookies",
        r"subscribe to newsletter",
        r"sign up for our newsletter",
    ]

    for pattern in junk:

        text = re.sub(
            pattern,
            "",
            text,
            flags=re.IGNORECASE
        )

    return text.strip()


# ============================================================
# POLITE DELAY
# ============================================================

def polite_delay():

    delay = random.uniform(
        MIN_DELAY,
        MAX_DELAY
    )

    print(
        f"[WAIT] {delay:.1f}s"
    )

    time.sleep(delay)


# ============================================================
# CACHE
# ============================================================

def cache_filename(url):

    digest = hashlib.sha256(
        url.encode("utf-8")
    ).hexdigest()

    return CACHE_DIR / (
        digest + ".bin"
    )


# ============================================================
# ERROR LOG
# ============================================================

def log_error(
    url,
    error
):

    timestamp = (
        datetime.now()
        .astimezone()
        .isoformat()
    )

    with open(
        ERROR_FILE,
        "a",
        encoding="utf-8"
    ) as f:

        f.write(
            f"TIME: {timestamp}\n"
        )

        f.write(
            f"URL: {url}\n"
        )

        f.write(
            f"ERROR: {error}\n"
        )

        f.write(
            "-" * 70
            + "\n"
        )


# ============================================================
# DOWNLOAD
# ============================================================

def download_url(url):

    cache_file = cache_filename(
        url
    )

    # --------------------------------------------------------
    # USE CACHE
    # --------------------------------------------------------

    if cache_file.exists():

        print(
            "[CACHE] "
            "Using existing download"
        )

        return cache_file.read_bytes()


    # --------------------------------------------------------
    # RETRIES
    # --------------------------------------------------------

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        try:

            print(
                f"[DOWNLOAD] "
                f"{attempt}/{MAX_RETRIES}"
            )

            response = session.get(
                url,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True
            )

            status = response.status_code

            print(
                f"[HTTP {status}]"
            )

            # ------------------------------------------------
            # SUCCESS
            # ------------------------------------------------

            if 200 <= status < 300:

                data = response.content

                if len(data) < 100:

                    raise RuntimeError(
                        "Response is too small"
                    )

                # Save immediately.

                cache_file.write_bytes(
                    data
                )

                print(
                    f"[SAVED] "
                    f"{len(data):,} bytes"
                )

                return data

            # ------------------------------------------------
            # TEMPORARY ERRORS
            # ------------------------------------------------

            if status in {
                408,
                425,
                429,
                500,
                502,
                503,
                504,
            }:

                wait = min(
                    60,
                    5 * (2 ** (attempt - 1))
                )

                wait += random.uniform(
                    0,
                    5
                )

                print(
                    f"[TEMPORARY ERROR] "
                    f"HTTP {status}"
                )

                print(
                    f"[RETRY] "
                    f"Waiting {wait:.1f}s"
                )

                time.sleep(wait)

                continue

            # ------------------------------------------------
            # EXPLICIT ACCESS DENIAL
            # ------------------------------------------------

            if status in {
                401,
                403,
                451
            }:

                raise RuntimeError(
                    f"Automated access refused "
                    f"with HTTP {status}"
                )

            # ------------------------------------------------
            # OTHER HTTP ERROR
            # ------------------------------------------------

            raise RuntimeError(
                f"HTTP {status}"
            )

        except (
            requests.Timeout,
            requests.ConnectionError
        ) as e:

            print(
                f"[NETWORK ERROR] "
                f"{type(e).__name__}"
            )

            if attempt == MAX_RETRIES:

                log_error(
                    url,
                    repr(e)
                )

                return None

            wait = min(
                60,
                5 * (2 ** (attempt - 1))
            )

            wait += random.uniform(
                0,
                5
            )

            print(
                f"[RETRY] "
                f"Waiting {wait:.1f}s"
            )

            time.sleep(wait)

        except Exception as e:

            print(
                f"[ERROR] {e}"
            )

            log_error(
                url,
                repr(e)
            )

            return None

    return None


# ============================================================
# HTML EXTRACTION
# ============================================================

def extract_html_text(
    data
):

    try:

        soup = BeautifulSoup(
            data,
            "html.parser"
        )

        # Remove irrelevant elements.

        for tag in soup([
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "aside",
            "form",
            "noscript",
            "svg",
            "iframe",
        ]):

            tag.decompose()

        # Prefer article/main.

        main = (
            soup.find("article")
            or soup.find("main")
            or soup.body
        )

        if main is None:

            return None

        text = main.get_text(
            separator="\n"
        )

        text = clean_text(
            text
        )

        if len(text) < MIN_TEXT_LENGTH:

            return None

        return text[
            :MAX_CHARS_PER_SOURCE
        ]

    except Exception as e:

        raise RuntimeError(
            f"HTML extraction failed: {e}"
        )


# ============================================================
# PDF EXTRACTION
# ============================================================

def extract_pdf_text(
    data
):

    pdf_hash = hashlib.sha256(
        data
    ).hexdigest()

    temp_pdf = (
        CACHE_DIR
        / f"{pdf_hash}.pdf"
    )

    temp_pdf.write_bytes(
        data
    )

    try:

        reader = PdfReader(
            str(temp_pdf)
        )

        pages = []

        for page_number, page in enumerate(
            reader.pages,
            start=1
        ):

            try:

                text = page.extract_text()

                if text:

                    pages.append(
                        f"[PAGE {page_number}]\n"
                        f"{text}"
                    )

            except Exception as e:

                print(
                    f"[PDF PAGE ERROR] "
                    f"{page_number}: {e}"
                )

        text = "\n\n".join(
            pages
        )

        text = clean_text(
            text
        )

        if len(text) < MIN_TEXT_LENGTH:

            return None

        return text[
            :MAX_CHARS_PER_SOURCE
        ]

    finally:

        try:

            temp_pdf.unlink()

        except Exception:

            pass


# ============================================================
# CONTENT EXTRACTION
# ============================================================

def extract_content(
    url,
    data
):

    # PDF by extension.

    if url.lower().endswith(
        ".pdf"
    ):

        return extract_pdf_text(
            data
        )

    # PDF by file signature.

    if data[:4] == b"%PDF":

        return extract_pdf_text(
            data
        )

    # Otherwise HTML.

    return extract_html_text(
        data
    )


# ============================================================
# SEARCH
# ============================================================

def search_web(
    query
):

    results = []

    print()
    print(
        f"[SEARCH] {query}"
    )

    try:

        with DDGS() as ddgs:

            search_results = ddgs.text(
                query,
                max_results=MAX_RESULTS_PER_QUERY
            )

            for result in search_results:

                url = result.get(
                    "href",
                    ""
                )

                if not url:

                    continue

                domain = get_domain(
                    url
                )

                score = domain_score(
                    domain
                )

                # ------------------------------------------------
                # IMPORTANT:
                #
                # We DO NOT reject unknown sources.
                #
                # They receive score 3 and are ranked below
                # authoritative sources.
                # ------------------------------------------------

                results.append({

                    "title":
                        result.get(
                            "title",
                            ""
                        ),

                    "url":
                        url,

                    "domain":
                        domain,

                    "score":
                        score,

                    "snippet":
                        result.get(
                            "body",
                            ""
                        ),
                })

    except Exception as e:

        print(
            f"[SEARCH ERROR] {e}"
        )

        log_error(
            f"SEARCH: {query}",
            repr(e)
        )

    return results


# ============================================================
# NORMALIZE TEXT
# ============================================================

def normalize_text(
    text
):

    text = text.lower()

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    text = re.sub(
        r"[^a-z0-9 ]",
        "",
        text
    )

    return text.strip()


# ============================================================
# DUPLICATE DETECTION
# ============================================================

def is_duplicate(
    text,
    existing_texts
):

    normalized = normalize_text(
        text[:3000]
    )

    for existing in existing_texts:

        other = normalize_text(
            existing[:3000]
        )

        if normalized == other:

            return True

        if (
            len(normalized) > 500
            and len(other) > 500
        ):

            length = min(
                len(normalized),
                len(other)
            )

            matches = sum(
                a == b
                for a, b in zip(
                    normalized[:length],
                    other[:length]
                )
            )

            similarity = (
                matches / length
            )

            if similarity >= 0.95:

                return True

    return False


# ============================================================
# GATHER SECTION
# ============================================================

def gather_section(
    section_name,
    queries
):

    print()
    print("=" * 70)

    print(
        section_name
    )

    print("=" * 70)

    candidates = []

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    for query in queries:

        results = search_web(
            query
        )

        candidates.extend(
            results
        )

        polite_delay()

    # --------------------------------------------------------
    # REMOVE DUPLICATE URLS
    # --------------------------------------------------------

    unique = {}

    for result in candidates:

        url = result["url"]

        if url not in unique:

            unique[url] = result

    candidates = list(
        unique.values()
    )

    # --------------------------------------------------------
    # AUTHORITY FIRST
    # --------------------------------------------------------

    candidates.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    print()
    print(
        f"[CANDIDATES] "
        f"{len(candidates)}"
    )

    documents = []
    existing_texts = []

    # --------------------------------------------------------
    # PROCESS SOURCES
    # --------------------------------------------------------

    for candidate in candidates:

        if len(documents) >= (
            MAX_SOURCES_PER_SECTION
        ):

            break

        print()
        print("-" * 70)

        print(
            f"TITLE: "
            f"{candidate['title']}"
        )

        print(
            f"DOMAIN: "
            f"{candidate['domain']}"
        )

        print(
            f"AUTHORITY: "
            f"{candidate['score']}/10"
        )

        print(
            f"URL: "
            f"{candidate['url']}"
        )

        # ----------------------------------------------------
        # DOWNLOAD
        # ----------------------------------------------------

        data = download_url(
            candidate["url"]
        )

        if data is None:

            print(
                "[SKIP] Download failed"
            )

            polite_delay()

            continue

        # ----------------------------------------------------
        # EXTRACT
        # ----------------------------------------------------

        try:

            text = extract_content(
                candidate["url"],
                data
            )

        except Exception as e:

            print(
                f"[EXTRACTION ERROR] "
                f"{e}"
            )

            log_error(
                candidate["url"],
                repr(e)
            )

            polite_delay()

            continue

        if not text:

            print(
                "[SKIP] "
                "No useful text found"
            )

            log_error(
                candidate["url"],
                "No useful text extracted"
            )

            polite_delay()

            continue

        # ----------------------------------------------------
        # DUPLICATE
        # ----------------------------------------------------

        if is_duplicate(
            text,
            existing_texts
        ):

            print(
                "[SKIP] Duplicate content"
            )

            polite_delay()

            continue

        # ----------------------------------------------------
        # ACCEPT
        # ----------------------------------------------------

        existing_texts.append(
            text
        )

        documents.append({

            "title":
                candidate["title"],

            "url":
                candidate["url"],

            "domain":
                candidate["domain"],

            "authority_score":
                candidate["score"],

            "snippet":
                candidate["snippet"],

            "content":
                text,
        })

        print(
            "[ACCEPTED]"
        )

        polite_delay()

    print()
    print(
        f"[SECTION COMPLETE] "
        f"{len(documents)} sources"
    )

    return documents


# ============================================================
# WRITE OUTPUT
# ============================================================

def write_document(
    all_sections
):

    retrieved_at = (
        datetime.now()
        .astimezone()
        .isoformat()
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        # ----------------------------------------------------
        # DOCUMENT HEADER
        # ----------------------------------------------------

        f.write(
            "=" * 70
            + "\n"
        )

        f.write(
            f"TOPIC {TOPIC_ID}: "
            f"{TOPIC_NAME.upper()}\n"
        )

        f.write(
            "=" * 70
            + "\n\n"
        )

        f.write(
            "KNOWLEDGE BASE TYPE:\n"
        )

        f.write(
            "Earthquake emergency injuries "
            "and first aid\n\n"
        )

        f.write(
            "PURPOSE:\n"
        )

        f.write(
            "Information gathered from medical, "
            "emergency, government, public-health, "
            "and other identifiable sources for "
            "use in an earthquake emergency "
            "information RAG system.\n\n"
        )

        f.write(
            "SAFETY NOTE:\n"
        )

        f.write(
            "This is a reference knowledge base. "
            "It must not be used by the chatbot "
            "to diagnose a person. Potentially "
            "life-threatening situations should "
            "be escalated to appropriate local "
            "emergency medical services.\n\n"
        )

        f.write(
            f"RETRIEVED_AT: "
            f"{retrieved_at}\n\n"
        )

        # ----------------------------------------------------
        # SECTIONS
        # ----------------------------------------------------

        for section_name, documents in (
            all_sections.items()
        ):

            f.write(
                "#" * 70
                + "\n"
            )

            f.write(
                section_name
                + "\n"
            )

            f.write(
                "#" * 70
                + "\n\n"
            )

            if not documents:

                f.write(
                    "[NO SUCCESSFULLY "
                    "RETRIEVED SOURCES]\n\n"
                )

                continue

            for index, document in enumerate(
                documents,
                start=1
            ):

                f.write(
                    "[DOCUMENT]\n"
                )

                f.write(
                    f"DOCUMENT_ID: "
                    f"{TOPIC_ID}_"
                    f"{index:03d}\n"
                )

                f.write(
                    f"SECTION: "
                    f"{section_name}\n"
                )

                f.write(
                    f"TITLE: "
                    f"{document['title']}\n"
                )

                f.write(
                    f"SOURCE_DOMAIN: "
                    f"{document['domain']}\n"
                )

                f.write(
                    f"SOURCE_URL: "
                    f"{document['url']}\n"
                )

                f.write(
                    f"AUTHORITY_SCORE: "
                    f"{document['authority_score']}/10\n"
                )

                f.write(
                    f"RETRIEVED_AT: "
                    f"{retrieved_at}\n"
                )

                f.write(
                    "SEARCH_SNIPPET:\n"
                )

                f.write(
                    document["snippet"]
                    + "\n\n"
                )

                f.write(
                    "CONTENT:\n"
                )

                f.write(
                    document["content"]
                    + "\n\n"
                )

                f.write(
                    "[/DOCUMENT]\n\n"
                )


# ============================================================
# MAIN
# ============================================================

def main():

    start_time = time.time()

    print()
    print("=" * 70)

    print(
        "EARTHQUAKE HELPER"
    )

    print(
        f"TOPIC {TOPIC_ID}: "
        f"{TOPIC_NAME}"
    )

    print("=" * 70)

    print()
    print(
        "Retrieval mode:"
    )

    print(
        "  - Slow / polite"
    )

    print(
        "  - Multiple retries"
    )

    print(
        "  - Local caching"
    )

    print(
        "  - HTML extraction"
    )

    print(
        "  - PDF extraction"
    )

    print(
        "  - Authority ranking"
    )

    print(
        "  - Unknown sources retained"
    )

    print(
        "  - Duplicate detection"
    )

    print(
        "  - Error logging"
    )

    print()

    all_sections = {}

    total_sources = 0

    section_count = len(
        RESEARCH_SECTIONS
    )

    # --------------------------------------------------------
    # PROCESS SECTIONS
    # --------------------------------------------------------

    for number, (
        section_name,
        queries
    ) in enumerate(
        RESEARCH_SECTIONS.items(),
        start=1
    ):

        print()
        print(
            f"========== "
            f"SECTION {number}/{section_count} "
            f"=========="
        )

        documents = gather_section(
            section_name,
            queries
        )

        all_sections[
            section_name
        ] = documents

        total_sources += len(
            documents
        )

    # --------------------------------------------------------
    # WRITE
    # --------------------------------------------------------

    write_document(
        all_sections
    )

    elapsed = (
        time.time() - start_time
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print()
    print("=" * 70)

    print(
        "GATHERING COMPLETE"
    )

    print(
        f"Successful sources: "
        f"{total_sources}"
    )

    print(
        f"Elapsed time: "
        f"{elapsed / 60:.1f} minutes"
    )

    print()
    print(
        f"Output:"
    )

    print(
        OUTPUT_FILE
    )

    print()
    print(
        f"Errors:"
    )

    print(
        ERROR_FILE
    )

    print()
    print(
        f"Cache:"
    )

    print(
        CACHE_DIR
    )

    print("=" * 70)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()