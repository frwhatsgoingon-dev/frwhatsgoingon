import json
import re
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import feedparser
import requests

DATA_PATH = Path("data.json")

GOOGLE_TRENDS_RSS_US = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"

MAX_TOPICS_PER_RUN = 8          # how many new topics per day
MAX_SOURCES_PER_TOPIC = 5       # how many links per topic


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:70].strip("-") or "topic"


def load_data():
    if not DATA_PATH.exists():
        return {"topics": []}
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def save_data_atomic(data):
    # Write to a temp file and replace data.json (prevents corruption)
    tmp = DATA_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(DATA_PATH)


def fetch_trending_titles():
    feed = feedparser.parse(GOOGLE_TRENDS_RSS_US)
    titles = []
    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        if title:
            titles.append(title)
    return titles


def fetch_sources_from_gdelt(topic: str, max_results: int = 5):
    # Free news search API: returns a list of articles with URLs + titles
    q = quote_plus(topic)
    url = (
        "https://api.gdeltproject.org/api/v2/doc/doc"
        f"?query={q}&mode=artlist&format=json&maxrecords={max_results}&sort=HybridRel"
    )
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    js = r.json()

    sources = []
    for art in js.get("articles", []):
        u = art.get("url")
        if not u:
            continue
        title = art.get("title") or topic
        domain = urlparse(u).netloc.replace("www.", "")
        sources.append(
            {
                "title": f"{title} ({domain})",
                "url": u,
            }
        )

    # de-dupe by URL
    seen = set()
    deduped = []
    for s in sources:
        if s["url"] in seen:
            continue
        seen.add(s["url"])
        deduped.append(s)
    return deduped


def add_topic(data, title: str, sources):
    slug = slugify(title)

    # Don't add duplicates
    existing_slugs = {t.get("slug") for t in data.get("topics", [])}
    if slug in existing_slugs:
        return False

    topic = {
        "slug": slug,
        "title": title,
        "summary": "Sources collected. (Next: we’ll add student-friendly summaries.)",
        "why_it_matters": "Use the sources below to research what’s happening and understand the context.",
        "sources": sources[:MAX_SOURCES_PER_TOPIC],
    }

    # Add newest topics to the top
    data["topics"] = [topic] + data.get("topics", [])
    return True


def main():
    data = load_data()

    trending = fetch_trending_titles()
    added_count = 0

    for title in trending:
        if added_count >= MAX_TOPICS_PER_RUN:
            break

        try:
            sources = fetch_sources_from_gdelt(title, max_results=MAX_SOURCES_PER_TOPIC)
            if len(sources) < 2:
                # skip topics with too few sources
                continue

            added = add_topic(data, title, sources)
            if added:
                added_count += 1

        except Exception as e:
            # Don’t crash the whole run if one topic fails
            print(f"Skipping topic due to error: {title} -> {e}")

    save_data_atomic(data)
    print(f"Done. Added {added_count} new topics.")


if __name__ == "__main__":
    main()
