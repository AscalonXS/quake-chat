"""
Earthquake Helper - Automated Information Gathering
====================================================

This program researches a topic and creates a TXT knowledge document
for a RAG system.

It is NOT a medical diagnosis system and should not be treated as an
emergency authority.

Directory:

project/
│
├── gathering_info/
│   └── gather_topic.py
│
└── docs/
    └── 01_immediate_earthquake_response.txt

Install:

    pip install ddgs requests beautifulsoup4

Run:

    python gather_topic.py
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS


# ============================================================
# PROJECT PATHS
# ============================================================

CURRENT_DIR = Path(__file__).resolve().parent

DOCS_DIR = CURRENT_DIR.parent / "docs"

DOCS_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# TOPIC CONFIGURATION
# ============================================================

TOPIC_ID = "01"

TOPIC_NAME = "Immediate Earthquake Response"

OUTPUT_FILE = (
    DOCS_DIR /
    "01_immediate_earthquake_response.txt"
)


# ============================================================
# RESEARCH QUESTIONS
# ============================================================

# The program will search for information about each of these.

RESEARCH_SECTIONS = {

    "01. During Earthquake Shaking": [
        "what should you do during an earthquake",
        "Drop Cover Hold On earthquake guidance",
        "earthquake safety during shaking official guidance",
    ],

    "02. Indoors": [
        "earthquake safety indoors official guidance",
        "earthquake apartment safety during shaking",
        "earthquake home safety official",
    ],

    "03. High-Rise Buildings": [
        "earthquake high rise building safety",
        "earthquake high rise during shaking official",
        "earthquake elevator safety official",
    ],

    "04. Outdoors": [
        "earthquake safety outdoors official",
        "earthquake falling objects outdoors",
        "earthquake outdoor evacuation guidance",
    ],

    "05. Vehicles": [
        "earthquake driving vehicle safety official",
        "what to do during earthquake while driving",
        "earthquake car safety official",
    ],

    "06. After Earthquake": [
        "what to do immediately after earthquake official",
        "earthquake after shaking stops official guidance",
        "earthquake post disaster safety",
    ],

    "07. Aftershocks": [
        "earthquake aftershock safety official",
        "what to do during aftershocks",
        "aftershock earthquake safety guidance",
    ],

    "08. Damaged Buildings": [
        "earthquake damaged building safety official",
        "when not to enter damaged building earthquake",
        "earthquake structural damage safety",
    ],

    "09. Fire Gas and Electricity": [
        "earthquake gas leak fire electrical hazards official",
        "earthquake gas leak safety",
        "earthquake downed power lines safety",
    ],

    "10. Tsunami": [
        "earthquake tsunami safety official",
        "earthquake near coast tsunami evacuation",
        "tsunami earthquake evacuation official",
    ],

    "11. Children and Schools": [
        "earthquake school classroom safety official",
        "earthquake children safety",
        "earthquake school evacuation guidance",
    ],

    "12. Accessibility": [
        "earthquake disability accessibility emergency guidance",
        "earthquake wheelchair safety official",
        "earthquake emergency preparedness disability",
    ],
}


# ============================================================
# TRUSTED DOMAINS
# ============================================================

# Search results from these domains receive a higher score.

HIGH_TRUST_DOMAINS = {

    "usgs.gov",
    "fema.gov",
    "redcross.org",
    "who.int",
    "ready.gov",
    "safekorea.go.kr",
    "weather.go.kr",
    "kma.go.kr",
    "go.kr",
    "gov",
    "cdc.gov",
}


# ============================================================
# HTTP
# ============================================================

HEADERS = {

    "User-Agent":
        "EarthquakeHelperResearch/1.0 "
        "(educational disaster-safety research)"
}

TIMEOUT = 20


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text: str) -> str:

    text = text.replace(
        "\r\n",
        "\n"
    )

    text = text.replace(
        "\r",
        "\n"
    )

    # Remove excessive spaces
    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    # Remove excessive blank lines
    text = re.sub(
        r"\n\s*\n+",
        "\n\n",
        text
    )

    return text.strip()


# ============================================================
# DOMAIN TRUST
# ============================================================

def get_domain(url: str) -> str:

    hostname = urlparse(url).hostname

    if not hostname:
        return ""

    hostname = hostname.lower()

    if hostname.startswith("www."):
        hostname = hostname[4:]

    return hostname


def domain_score(url: str) -> int:

    domain = get_domain(url)

    for trusted in HIGH_TRUST_DOMAINS:

        if (
            domain == trusted
            or domain.endswith("." + trusted)
        ):
            return 100

    return 20


# ============================================================
# SEARCH
# ============================================================

def search_web(
    query: str,
    max_results: int = 5
):

    print(
        f"    Searching: {query}"
    )

    results = []

    try:

        with DDGS() as ddgs:

            search_results = ddgs.text(
                query,
                max_results=max_results
            )

            for result in search_results:

                url = result.get(
                    "href",
                    ""
                )

                if not url:
                    continue

                results.append({
                    "title": result.get(
                        "title",
                        ""
                    ),

                    "url": url,

                    "snippet": result.get(
                        "body",
                        ""
                    ),

                    "score": domain_score(
                        url
                    )
                })

    except Exception as error:

        print(
            f"    Search error: {error}"
        )

    return results


# ============================================================
# FETCH WEBPAGE
# ============================================================

def fetch_page(url: str):

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT
        )

        response.raise_for_status()

        content_type = response.headers.get(
            "content-type",
            ""
        ).lower()

        if "text/html" not in content_type:

            return None

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # Remove page elements that aren't
        # useful for the knowledge base.

        for tag in soup.find_all([
            "script",
            "style",
            "noscript",
            "nav",
            "footer",
            "header",
            "aside",
            "form",
            "button"
        ]):

            tag.decompose()

        # Prefer actual article/main content.

        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find(
                attrs={
                    "role": "main"
                }
            )
            or soup.body
        )

        if not main:

            return None

        text = main.get_text(
            "\n",
            strip=True
        )

        text = clean_text(
            text
        )

        if len(text) < 300:

            return None

        title = ""

        if soup.title:

            title = soup.title.get_text(
                " ",
                strip=True
            )

        return {
            "title": title,
            "text": text
        }

    except Exception as error:

        print(
            f"      Could not read page: "
            f"{error}"
        )

        return None


# ============================================================
# REMOVE DUPLICATES
# ============================================================

def remove_duplicate_text(
    documents
):

    seen = set()

    unique = []

    for document in documents:

        normalized = re.sub(
            r"\s+",
            " ",
            document["text"]
        ).lower()

        # Use first 1000 chars as a
        # simple duplicate fingerprint.

        fingerprint = normalized[:1000]

        if fingerprint in seen:

            continue

        seen.add(
            fingerprint
        )

        unique.append(
            document
        )

    return unique


# ============================================================
# CREATE SECTION
# ============================================================

def gather_section(
    section_name: str,
    queries: list[str]
):

    print()
    print("=" * 60)
    print(section_name)
    print("=" * 60)

    search_results = []

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    for query in queries:

        results = search_web(
            query,
            max_results=5
        )

        search_results.extend(
            results
        )

        time.sleep(
            1
        )

    # --------------------------------------------------------
    # REMOVE DUPLICATE URLS
    # --------------------------------------------------------

    unique_urls = {}

    for result in search_results:

        url = result["url"]

        if url not in unique_urls:

            unique_urls[url] = result

        else:

            # Keep the result with
            # higher trust score.

            if (
                result["score"]
                >
                unique_urls[url]["score"]
            ):

                unique_urls[url] = result

    search_results = list(
        unique_urls.values()
    )

    # --------------------------------------------------------
    # SORT BY TRUST
    # --------------------------------------------------------

    search_results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    # --------------------------------------------------------
    # FETCH
    # --------------------------------------------------------

    documents = []

    # Limit to top 5 pages per section
    # to prevent enormous RAG documents.

    for result in search_results[:5]:

        print(
            f"    Reading: "
            f"{result['url']}"
        )

        page = fetch_page(
            result["url"]
        )

        if not page:

            continue

        documents.append({

            "title":
                page["title"]
                or result["title"],

            "url":
                result["url"],

            "domain":
                get_domain(
                    result["url"]
                ),

            "trust_score":
                result["score"],

            "text":
                page["text"],

            "retrieved":
                datetime.now(
                    timezone.utc
                ).isoformat()
        })

        time.sleep(
            1
        )

    # --------------------------------------------------------
    # REMOVE DUPLICATES
    # --------------------------------------------------------

    documents = remove_duplicate_text(
        documents
    )

    return documents


# ============================================================
# WRITE TXT
# ============================================================

def write_document(
    collected_sections
):

    generated_at = datetime.now(
        timezone.utc
    ).isoformat()

    output = []

    output.append(
        "EARTHQUAKE HELPER\n"
    )

    output.append(
        "TOPIC 01 — IMMEDIATE EARTHQUAKE RESPONSE\n"
    )

    output.append(
        "=" * 80
    )

    output.append(
        "\n"
    )

    output.append(
        "DOCUMENT PURPOSE\n"
    )

    output.append(
        "This document contains automatically gathered "
        "research material for the Earthquake Helper RAG system.\n"
    )

    output.append(
        f"Generated: {generated_at}\n"
    )

    output.append(
        "IMPORTANT: This material must be reviewed and "
        "validated before being used for life-safety responses.\n"
    )

    output.append(
        "=" * 80
    )

    output.append(
        "\n"
    )

    # --------------------------------------------------------
    # SECTIONS
    # --------------------------------------------------------

    for section_name, documents in collected_sections.items():

        output.append(
            "\n"
        )

        output.append(
            "=" * 80
        )

        output.append(
            f"\n{section_name}\n"
        )

        output.append(
            "=" * 80
        )

        for index, document in enumerate(
            documents,
            start=1
        ):

            output.append(
                f"\n\nSOURCE {index}\n"
            )

            output.append(
                "-" * 80
            )

            output.append(
                f"\nTITLE: "
                f"{document['title']}\n"
            )

            output.append(
                f"SOURCE: "
                f"{document['url']}\n"
            )

            output.append(
                f"DOMAIN: "
                f"{document['domain']}\n"
            )

            output.append(
                f"AUTHORITY SCORE: "
                f"{document['trust_score']}/100\n"
            )

            output.append(
                f"RETRIEVED: "
                f"{document['retrieved']}\n"
            )

            output.append(
                "\nCONTENT\n"
            )

            output.append(
                document["text"]
            )

            output.append(
                "\n"
            )

    output.append(
        "\n"
    )

    output.append(
        "=" * 80
    )

    output.append(
        "\nEND OF DOCUMENT\n"
    )

    OUTPUT_FILE.write_text(
        "".join(output),
        encoding="utf-8"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print("EARTHQUAKE HELPER")
    print("AUTOMATED INFORMATION GATHERING")
    print("TOPIC 01")
    print("=" * 60)

    collected_sections = {}

    for section_name, queries in (
        RESEARCH_SECTIONS.items()
    ):

        documents = gather_section(
            section_name,
            queries
        )

        collected_sections[
            section_name
        ] = documents

        print(
            f"\n    Collected "
            f"{len(documents)} sources."
        )

    # --------------------------------------------------------
    # WRITE
    # --------------------------------------------------------

    write_document(
        collected_sections
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    total_sources = sum(
        len(documents)
        for documents
        in collected_sections.values()
    )

    print()
    print("=" * 60)
    print("DONE")
    print("=" * 60)

    print(
        f"Sections: "
        f"{len(collected_sections)}"
    )

    print(
        f"Sources collected: "
        f"{total_sources}"
    )

    print()
    print(
        f"TXT created at:"
    )

    print(
        OUTPUT_FILE
    )


if __name__ == "__main__":
    main()