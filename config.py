import os

from dotenv import load_dotenv


load_dotenv()


def _read_integer_setting(
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    value = os.getenv(name, str(default))

    try:
        parsed_value = int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a whole number.") from error

    if not minimum <= parsed_value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")

    return parsed_value


MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "tech_news")

NEWS_API_URL = os.getenv(
    "NEWS_API_URL",
    "https://gnews.io/api/v4/search",
)
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
NEWS_SEARCH_QUERY = os.getenv(
    "NEWS_SEARCH_QUERY",
    "technology OR artificial intelligence OR agentic AI OR quantum computing "
    "OR cloud computing OR cybersecurity OR software OR startups",
)
NEWS_MAX_RESULTS = _read_integer_setting(
    "NEWS_MAX_RESULTS",
    default=10,
    minimum=1,
    maximum=100,
)

NEWS_SCHEDULE_HOUR = _read_integer_setting(
    "NEWS_SCHEDULE_HOUR",
    default=6,
    minimum=0,
    maximum=23,
)
NEWS_SCHEDULE_MINUTE = _read_integer_setting(
    "NEWS_SCHEDULE_MINUTE",
    default=0,
    minimum=0,
    maximum=59,
)
NEWS_TIMEZONE = os.getenv("NEWS_TIMEZONE", "UTC")
