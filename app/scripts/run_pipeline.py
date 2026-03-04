import json
import re
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import feedparser
import requests

DATA_PATH = Path("data.json")
GOOGLE_TRENDS_RSS_US = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"

MAX_TOPICS_PER_RUN = 8
MAX_SOURCES_PER_TOPIC = 5

# Block entertainment/sports/pop-culture
BLOCKED_TOPICS = [
    "taylor swift", "swift", "eras tour",
    "nfl", "nba", "mlb", "nhl", "super bowl",
    "oscars", "grammys",
    "movie", "tv", "netflix",
    "celebrity", "concert", "tour", "album", "song",
]

# Require these kinds of keywords to be considered "hard news"
NEWS_KEYWORDS = [
    "war", "conflict", "strike", "attack", "missile", "drone",
    "iran", "israel", "gaza", "palestine", "lebanon",
    "ukraine", "russia", "nato",
    "china", "taiwan",
    "congress", "senate", "house", "white house", "president", "election", "primary", "vote",
    "supreme court", "court", "ruling", "law", "bill",
    "economy", "inflation", "prices", "jobs", "interest rates", "fed",
]

# Trusted sources only (NO Al Jazeera)
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
    "ft.com",
    "economist.com",
    "cnbc.com",
    "abcnews.go.com",
    "cbsnews.com",
    "nbcnews.com",
    "usatoday.com",
    "politico.com",
    "axios.com",
]
BLOCKED_SOURCES = ["aljazeera.com"]


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


def is_news_topic(title: str) -> bool:
    t = title.lower().strip()

    # Block obvious non-news
    if any(b in t for b in BLOCKED_TOPICS):
        return False

    # Require at least one news keyword
    return any(k in t for k in NEWS_KEYWORDS)


def is_trusted_source(url: str) -> bool:
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]

        if any(b in domain for b in BLOCKED_SOURCES):
            return False

        return any(a in domain for a in TRUSTED_SOURCES)
    except Exception:
        return False


def fetch_trending_titles():
    feed = feedparser.parse(GOOGLE_TRENDS_RSS_US)
    titles = []
    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        if title:
            titles.append(title)

    # Hard-news fallback ONLY (no sports/celebs)
    if not titles:
        titles = [
            "Iran Israel war latest",
            "Congress war powers vote",
            "Ukraine Russia latest",
            "U.S. economy inflation update",
            "Oil prices Middle East",
            "Gaza ceasefire talks",
        ]

    return titles


def fetch_sources_from_gdelt(topic: str, max_results: int = 10):
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

    # de-dupe
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

    # If we couldn't find trusted sources, SKIP the topic.
    # This prevents random low-quality/foreign sites from entering your site.
    if not sources:
        return False

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
    print(f"Got {len(trending)} trending titles.")

    trending_news = [t for t in trending if is_news_topic(t)]
    print(f"Kept {len(trending_news)} after news filtering.")

    added_count = 0
    for title in trending_news:
        if added_count >= MAX_TOPICS_PER_RUN:
            break

        try:
            sources = fetch_sources_from_gdelt(title, max_results=10)
            added = add_topic(data, title, sources)
            if added:
                added_count += 1
                print(f"Added: {title} (trusted sources: {len(sources)})")
            else:
                print(f"Skipped: {title} (no trusted sources or duplicate)")
        except Exception as e:
            print(f"Error for '{title}': {e}")

    save_data_atomic(data)
    print(f"Done. Added {added_count} new topics.")


if __name__ == "__main__":
    main()
