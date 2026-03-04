import json
import os
import re
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import feedparser
import requests

DATA_PATH = Path("data.json")
GOOGLE_TRENDS_RSS_US = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"

MAX_TOPICS_PER_RUN = 8
MAX_SOURCES_PER_TOPIC = 5

# 1) Allow only topics that look like hard news (keywords)
NEWS_KEYWORDS = [
    "war", "conflict", "strike", "attack", "missile", "drone",
    "election", "primary", "vote", "ballot",
    "government", "congress", "senate", "house", "white house", "president",
    "policy", "law", "court", "supreme", "ruling", "bill",
    "military", "security", "diplomacy", "sanctions",
    "iran", "israel", "gaza", "palestine", "lebanon",
    "ukraine", "russia", "nato",
    "china", "taiwan",
    "economy", "inflation", "prices", "jobs", "interest rates",
]

# 2) Only keep sources from these domains (and explicitly exclude Al Jazeera)
TRUSTED_SOURCES = [
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "bbc.co.uk",
    "npr.org",
    "nytimes.com",
    "washingtonpost.com",
    "wsj.com",
    "bloomberg.com",
    "economist.com",
    "ft.com",
    "cnbc.com",
    "abcnews.go.com",
    "cbsnews.com",
    "nbcnews.com",
    "usatoday.com",
    "politico.com",
    "axios.com",
]

BLOCKED_SOURCES = [
    "aljazeera.com",
]


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
    tmp = DATA_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(DATA_PATH)


def is_trusted_source(url: str) -> bool:
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]

        # hard block list
        for blocked in BLOCKED_SOURCES:
            if blocked in domain:
                return False

        for allowed in TRUSTED_SOURCES:
            if allowed in domain:
                return True

        return False
    except Exception:
        return False


def is_news_topic(title: str) -> bool:
    t = title.lower().strip()

    # block obvious non-news
    for b in BLOCKED_TOPICS:
        if b in t:
            return False

    # require at least one news keyword
    return any(k in t for k in NEWS_KEYWORDS)


def fetch_trending_titles():
    feed = feedparser.parse(GOOGLE_TRENDS_RSS_US)
    titles = []
    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        if title:
            titles.append(title)
    return titles


def fetch_sources_from_gdelt(topic: str, max_results: int = 5):
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
        if not is_trusted_source(u):
            continue

        title = art.get("title") or topic
        domain = urlparse(u).netloc.replace("www.", "")
        sources.append({"title": f"{title} ({domain})", "url": u})

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

    existing_slugs = {t.get("slug") for t in data.get("topics", [])}
    if slug in existing_slugs:
        return False

    # If no trusted sources, keep topic but include a safe search link
    if not sources:
        sources = [{
            "title": f"Search: {title}",
            "url": f"https://www.google.com/search?q={quote_plus(title)}"
        }]

    topic = {
        "slug": slug,
        "title": title,
        "summary": "Sources collected. (Next: we’ll add student-friendly summaries.)",
        "why_it_matters": "Use the sources below to research what’s happening and understand the context.",
        "sources": sources[:MAX_SOURCES_PER_TOPIC],
    }

    data["topics"] = [topic] + data.get("topics", [])
    return True


def main():
    data = load_data()

    trending = fetch_trending_titles()
    print(f"Got {len(trending)} trending titles from Google Trends.")

    # Filter to hard news only
    trending_news = [t for t in trending if is_news_topic(t)]
    print(f"Kept {len(trending_news)} titles after news-topic filtering.")

    added_count = 0

    for title in trending_news:
        if added_count >= MAX_TOPICS_PER_RUN:
            break

        try:
            sources = fetch_sources_from_gdelt(title, max_results=MAX_SOURCES_PER_TOPIC)
            added = add_topic(data, title, sources)
            if added:
                added_count += 1
                print(f"Added: {title} (trusted sources: {len(sources)})")
            else:
                print(f"Skipped duplicate: {title}")

        except Exception as e:
            print(f"GDELT error for '{title}': {e}")
            added = add_topic(data, title, sources=[])
            if added:
                added_count += 1
                print(f"Added with fallback search link: {title}")

    save_data_atomic(data)
    print(f"Done. Added {added_count} new topics.")


if __name__ == "__main__":
    main()
