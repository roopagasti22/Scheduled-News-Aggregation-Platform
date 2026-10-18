from datetime import datetime, timezone
import re
from typing import Any

import requests
from pymongo.errors import DuplicateKeyError

from config import (
    NEWS_API_KEY,
    NEWS_API_URL,
    NEWS_MAX_RESULTS,
    NEWS_SEARCH_QUERY,
)
from database import create_indexes, news_collection


CATEGORY_KEYWORDS = {
    "Agentic AI": ("agentic ai", "ai agent", "autonomous agent"),
    "Quantum Computing": ("quantum", "qubit"),
    "Cybersecurity": ("cybersecurity", "ransomware", "data breach", "vulnerability"),
    "Cloud": ("cloud computing", "cloud", "aws", "azure", "google cloud"),
    "Developer Tools": ("developer tool", "code editor", "ide", "github copilot"),
    "Programming": ("programming", "programming language", "python", "javascript"),
    "Startups": ("startup", "venture capital", "funding round"),
    "Technology Companies": (
        "google",
        "microsoft",
        "apple",
        "amazon",
        "meta",
        "nvidia",
    ),
    "AI": ("artificial intelligence", "machine learning", "generative ai", "ai"),
}
ARTICLE_CATEGORIES = tuple(CATEGORY_KEYWORDS) + ("Other Technology",)


class NewsServiceError(Exception):
    """Base error for news collection problems."""


class NewsAPIError(NewsServiceError):
    """The news API could not provide a successful response."""


class InvalidNewsResponseError(NewsServiceError):
    """The news API response did not have the expected structure."""


def categorize_article(title: str, description: str) -> str:
    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        f"{title} {description}".casefold(),
    )

    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(f" {keyword} " in f" {text} " for keyword in keywords):
            return category

    return "Other Technology"


def _parse_published_at(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidNewsResponseError("An article has an invalid published date.")

    try:
        published_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise InvalidNewsResponseError(
            "An article has an invalid published date."
        ) from error

    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)

    return published_at


def _normalize_article(article: Any) -> dict[str, Any]:
    if not isinstance(article, dict):
        raise InvalidNewsResponseError("An article is not a JSON object.")

    title = article.get("title")
    url = article.get("url")
    description = article.get("description") or ""
    source_data = article.get("source") or {}
    author = article.get("author")

    if not isinstance(title, str) or not title.strip():
        raise InvalidNewsResponseError("An article is missing its title.")
    if not isinstance(url, str) or not url.strip():
        raise InvalidNewsResponseError("An article is missing its URL.")
    if not isinstance(description, str):
        raise InvalidNewsResponseError("An article has an invalid description.")
    if not isinstance(source_data, dict):
        raise InvalidNewsResponseError("An article has an invalid source.")
    if author is not None and not isinstance(author, str):
        raise InvalidNewsResponseError("An article has an invalid author.")

    source_name = source_data.get("name", "Unknown source")
    if not isinstance(source_name, str):
        raise InvalidNewsResponseError("An article has an invalid source name.")

    return {
        "title": title.strip(),
        "description": description.strip(),
        "source": source_name,
        "author": author,
        "url": url.strip(),
        "category": categorize_article(title, description),
        "published_at": _parse_published_at(article.get("publishedAt")),
        "collected_at": datetime.now(timezone.utc),
    }


def fetch_news() -> list[dict[str, Any]]:
    if not NEWS_API_KEY:
        raise NewsAPIError("NEWS_API_KEY is not configured.")

    try:
        response = requests.get(
            NEWS_API_URL,
            params={
                "q": NEWS_SEARCH_QUERY,
                "lang": "en",
                "max": NEWS_MAX_RESULTS,
                "apikey": NEWS_API_KEY,
            },
            timeout=10,
        )
        response.raise_for_status()
    except requests.Timeout as error:
        raise NewsAPIError("The news API request timed out.") from error
    except requests.RequestException as error:
        raise NewsAPIError("The news API request failed.") from error

    try:
        payload = response.json()
    except ValueError as error:
        raise InvalidNewsResponseError(
            "The news API returned invalid JSON."
        ) from error

    if not isinstance(payload, dict) or not isinstance(payload.get("articles"), list):
        raise InvalidNewsResponseError(
            "The news API response does not contain an articles list."
        )

    return [_normalize_article(article) for article in payload["articles"]]


def store_articles(articles: list[dict[str, Any]]) -> int:
    create_indexes()
    stored_count = 0

    for article in articles:
        try:
            news_collection.insert_one(article)
            stored_count += 1
        except DuplicateKeyError:
            continue

    return stored_count


def collect_and_store_news() -> int:
    return store_articles(fetch_news())
