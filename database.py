from pymongo import ASCENDING, MongoClient
from pymongo.errors import PyMongoError

from config import MONGODB_DATABASE, MONGODB_URI


client = MongoClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=5000,
)
database = client[MONGODB_DATABASE]

news_collection = database["news"]
daily_briefings_collection = database["daily_briefings"]


def connect_to_database() -> None:
    try:
        client.admin.command("ping")
    except PyMongoError as error:
        raise ConnectionError(
            "Could not connect to MongoDB. Check that MongoDB is running and "
            "that MONGODB_URI is correct."
        ) from error


def create_indexes() -> None:
    news_collection.create_index(
        [("url", ASCENDING)],
        unique=True,
        name="unique_news_url",
    )
    daily_briefings_collection.create_index(
        [("briefing_date", ASCENDING)],
        unique=True,
        name="unique_briefing_date",
    )
