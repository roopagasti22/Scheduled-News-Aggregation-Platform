import re
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import NEWS_TIMEZONE
from database import create_indexes, daily_briefings_collection, news_collection


MAX_STORIES_PER_SECTION = 2
ARTICLE_LOOKBACK = timedelta(days=3)

SECTION_CATEGORIES = {
    "AI": ("AI",),
    "AGENTIC AI": ("Agentic AI",),
    "QUANTUM COMPUTING": ("Quantum Computing",),
    "CLOUD & SOFTWARE": ("Cloud", "Programming", "Developer Tools"),
    "CYBERSECURITY": ("Cybersecurity",),
    "TECHNOLOGY BUSINESS": ("Startups", "Technology Companies"),
}

PRIORITY_CATEGORIES = {
    "AI",
    "Agentic AI",
    "Quantum Computing",
    "Cloud",
    "Cybersecurity",
    "Programming",
    "Developer Tools",
    "Startups",
    "Technology Companies",
}

IMPACT_KEYWORDS = (
    "announces",
    "launches",
    "releases",
    "acquires",
    "raises",
    "breach",
    "vulnerability",
    "outage",
    "regulation",
    "breakthrough",
)

WHY_IT_MATTERS = {
    "AI": "AI research and products can change how people work and how software is built.",
    "Agentic AI": "AI agents may automate multi-step tasks, creating new opportunities and risks.",
    "Quantum Computing": "Quantum advances could affect future computing and encryption.",
    "Cloud": "Cloud changes can affect the cost, reliability, and scale of online services.",
    "Cybersecurity": "Security developments can affect the safety of organizations and their users.",
    "Programming": "Programming changes can influence how developers build and maintain software.",
    "Developer Tools": "Developer tools can improve how teams write, test, and ship software.",
    "Startups": "Startup developments can signal new products, investment, and job opportunities.",
    "Technology Companies": "Major company decisions can influence products and the wider technology industry.",
    "Other Technology": "This story may indicate a technology change worth following.",
}

LEARNING_TOPICS = {
    "AI": "Try building a small application that calls an AI API and evaluates its output.",
    "Agentic AI": "Learn how an AI agent uses tools, follows steps, and handles failure.",
    "Quantum Computing": "Study qubits, superposition, and the difference between quantum and classical bits.",
    "Cloud": "Deploy a small web application and learn how cloud hosting and monitoring work.",
    "Cybersecurity": "Practice identifying common web vulnerabilities in a safe learning lab.",
    "Programming": "Explore the programming language or software release mentioned in the news.",
    "Developer Tools": "Try a developer tool from the news on a small personal coding task.",
    "Startups": "Learn how product teams validate an idea and explain a simple business model.",
    "Technology Companies": "Compare how a major technology company builds and supports its products.",
    "Other Technology": "Choose one unfamiliar technical term from today's stories and research it.",
}

CAREER_SKILLS = {
    "AI": "AI and machine-learning fundamentals, data literacy, and responsible AI evaluation.",
    "Agentic AI": "Python, API integration, tool-use design, and testing AI workflows.",
    "Quantum Computing": "Linear algebra, quantum information fundamentals, and Python-based simulation.",
    "Cloud": "Cloud fundamentals, deployment, networking, and reliability monitoring.",
    "Cybersecurity": "Secure coding, threat awareness, and incident-response fundamentals.",
    "Programming": "The programming language and software practices highlighted by today's stories.",
    "Developer Tools": "Version control, automated testing, and developer productivity tools.",
    "Startups": "Product thinking, communication, market research, and practical software skills.",
    "Technology Companies": "Software engineering fundamentals and knowledge of the company's product area.",
    "Other Technology": "Build strong programming fundamentals and follow the technology area in the story.",
}


def _normalise_datetime(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def score_article(
    article: dict[str, Any],
    now: datetime | None = None,
) -> int:
    """Score topic relevance, important events, and freshness with simple points."""
    current_time = _normalise_datetime(now or datetime.now(timezone.utc))
    if current_time is None:
        raise ValueError("now must be a datetime.")

    score = 0
    if article.get("category") in PRIORITY_CATEGORIES:
        score += 3

    title = article.get("title", "")
    if isinstance(title, str):
        title_text = title.casefold()
        matched_impact_terms = sum(
            keyword in title_text for keyword in IMPACT_KEYWORDS
        )
        score += min(matched_impact_terms, 3) * 2

    published_at = _normalise_datetime(article.get("published_at"))
    collected_at = _normalise_datetime(article.get("collected_at"))
    story_time = published_at or collected_at
    if story_time is not None:
        age = current_time - story_time
        if timedelta(0) <= age <= timedelta(days=1):
            score += 2
        elif timedelta(days=1) < age <= timedelta(days=3):
            score += 1

    return score


def _section_for_category(category: Any) -> str | None:
    for section, categories in SECTION_CATEGORIES.items():
        if category in categories:
            return section
    return None


def _title_key(title: Any) -> str:
    if not isinstance(title, str):
        return ""
    return re.sub(r"[^a-z0-9]+", " ", title.casefold()).strip()


def _summary(description: Any) -> str:
    if not isinstance(description, str) or not description.strip():
        return "No summary was provided by the news source."

    sentences = re.split(r"(?<=[.!?])\s+", description.strip())
    return " ".join(sentences[:3])


def _article_for_briefing(article: dict[str, Any]) -> dict[str, Any]:
    category = article.get("category", "Other Technology")
    return {
        "title": article.get("title", "Untitled article"),
        "summary": _summary(article.get("description")),
        "why_it_matters": WHY_IT_MATTERS.get(
            category,
            WHY_IT_MATTERS["Other Technology"],
        ),
        "source": article.get("source", "Unknown source"),
        "url": article.get("url", ""),
        "category": category,
        "published_at": article.get("published_at"),
        "score": article["score"],
    }


def select_top_news(
    articles: list[dict[str, Any]],
    now: datetime | None = None,
) -> dict[str, list[dict[str, Any]]]:
    ranked_articles = []

    for article in articles:
        section = _section_for_category(article.get("category"))
        title_key = _title_key(article.get("title"))
        if section is None or not title_key:
            continue

        ranked_article = dict(article)
        ranked_article["score"] = score_article(article, now)
        ranked_article["section"] = section
        ranked_article["title_key"] = title_key
        ranked_articles.append(ranked_article)

    ranked_articles.sort(
        key=lambda article: (
            article["score"],
            _normalise_datetime(article.get("published_at"))
            or _normalise_datetime(article.get("collected_at"))
            or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )

    selected = {section: [] for section in SECTION_CATEGORIES}
    seen_titles = set()
    for article in ranked_articles:
        section = article["section"]
        if article["title_key"] in seen_titles:
            continue
        if len(selected[section]) >= MAX_STORIES_PER_SECTION:
            continue

        seen_titles.add(article["title_key"])
        selected[section].append(_article_for_briefing(article))

    return selected


def _get_briefing_date(now: datetime) -> date:
    try:
        local_timezone = ZoneInfo(NEWS_TIMEZONE)
    except ZoneInfoNotFoundError as error:
        raise ValueError("NEWS_TIMEZONE must be a valid timezone name.") from error
    return now.astimezone(local_timezone).date()


def _format_briefing(briefing: dict[str, Any]) -> str:
    lines = [
        "DAILY GLOBAL TECH BRIEFING",
        f"Date: {briefing['briefing_date']}",
        f"Articles reviewed: {briefing['total_news']}",
    ]

    story_number = 1
    for section, stories in briefing["top_news"].items():
        lines.extend(["", section])
        if not stories:
            lines.append("- No matching stories were collected for this section.")
            continue

        for story in stories:
            lines.extend(
                [
                    f"{story_number}. {story['title']}",
                    f"   Summary: {story['summary']}",
                    f"   Why it matters: {story['why_it_matters']}",
                    f"   Source: {story['source']} — {story['url']}",
                ]
            )
            story_number += 1

    lines.extend(
        [
            "",
            "LEARNING OF THE DAY",
            briefing["learning_of_the_day"],
            "",
            "CAREER OPPORTUNITY",
            briefing["career_opportunity"],
        ]
    )
    return "\n".join(lines)


def generate_daily_briefing(now: datetime | None = None) -> dict[str, Any]:
    current_time = _normalise_datetime(now or datetime.now(timezone.utc))
    if current_time is None:
        raise ValueError("now must be a datetime.")

    briefing_date = _get_briefing_date(current_time)
    cutoff = current_time - ARTICLE_LOOKBACK
    articles = list(
        news_collection.find(
            {
                "$or": [
                    {"published_at": {"$gte": cutoff}},
                    {"collected_at": {"$gte": cutoff}},
                ]
            }
        )
    )

    category_counts: dict[str, int] = {}
    for article in articles:
        category = article.get("category", "Other Technology")
        category_counts[category] = category_counts.get(category, 0) + 1

    top_news = select_top_news(articles, current_time)
    selected_stories = [
        story
        for stories in top_news.values()
        for story in stories
    ]
    if selected_stories:
        most_represented_category = max(
            selected_stories,
            key=lambda story: story["score"],
        )["category"]
        learning_of_the_day = LEARNING_TOPICS[most_represented_category]
        career_opportunity = CAREER_SKILLS[most_represented_category]
    else:
        learning_of_the_day = (
            "Review the news search settings and category keywords, then try "
            "running collection again."
        )
        career_opportunity = (
            "No clear role or skill trend can be suggested until relevant "
            "technology news is collected."
        )

    briefing = {
        "briefing_date": briefing_date.isoformat(),
        "generated_at": current_time,
        "total_news": len(articles),
        "categories": category_counts,
        "top_news": top_news,
        "learning_of_the_day": learning_of_the_day,
        "career_opportunity": career_opportunity,
    }

    create_indexes()
    daily_briefings_collection.update_one(
        {"briefing_date": briefing["briefing_date"]},
        {
            "$set": briefing,
            "$setOnInsert": {"created_at": current_time},
        },
        upsert=True,
    )
    print(_format_briefing(briefing))
    return briefing
