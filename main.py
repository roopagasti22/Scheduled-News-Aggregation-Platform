from datetime import date
import logging
import re

from bson import ObjectId
from flask import Flask, jsonify, render_template, request
from pymongo import DESCENDING
from pymongo.errors import PyMongoError

from database import (
    client,
    connect_to_database,
    create_indexes,
    daily_briefings_collection,
    news_collection,
)
from models import serialize_document
from news_service import ARTICLE_CATEGORIES
from scheduler import (
    get_schedule_status,
    set_schedule_interval,
    start_scheduler,
)


app = Flask(__name__)
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@app.get("/")
def dashboard():
    return render_template("index.html")


def _error(message: str, status_code: int):
    return jsonify({"error": message}), status_code


def _read_limit():
    raw_limit = request.args.get("limit", str(DEFAULT_PAGE_SIZE))
    try:
        limit = int(raw_limit)
    except ValueError:
        return None, _error("limit must be a whole number.", 400)

    if not 1 <= limit <= MAX_PAGE_SIZE:
        return None, _error(f"limit must be between 1 and {MAX_PAGE_SIZE}.", 400)
    return limit, None


@app.get("/health")
def health_check():
    try:
        client.admin.command("ping")
    except PyMongoError:
        return jsonify({"status": "unavailable", "error": "Database is unavailable."}), 503

    return jsonify({"status": "ok", "database": "connected"}), 200


@app.route("/scheduler", methods=["GET", "POST"])
def scheduler_settings():
    if request.method == "GET":
        return jsonify(get_schedule_status()), 200

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error("Send a JSON object with interval_minutes.", 400)

    interval_minutes = payload.get("interval_minutes")
    if isinstance(interval_minutes, bool) or not isinstance(interval_minutes, int):
        return _error("interval_minutes must be 1, 5, 60, or 1440.", 400)

    try:
        return jsonify(set_schedule_interval(interval_minutes)), 200
    except ValueError as error:
        return _error(str(error), 400)
    except RuntimeError as error:
        return _error(str(error), 503)


@app.get("/news")
def get_latest_news():
    limit, error_response = _read_limit()
    if error_response:
        return error_response

    try:
        articles = news_collection.find().sort("published_at", DESCENDING).limit(limit)
        return jsonify([serialize_document(article) for article in articles]), 200
    except PyMongoError:
        return _error("Could not retrieve news from the database.", 503)


@app.get("/news/search")
def search_news():
    keyword = request.args.get("keyword", "").strip()
    if not keyword:
        return _error("The keyword query parameter is required.", 400)

    limit, error_response = _read_limit()
    if error_response:
        return error_response

    escaped_keyword = re.escape(keyword)
    query = {
        "$or": [
            {"title": {"$regex": escaped_keyword, "$options": "i"}},
            {"description": {"$regex": escaped_keyword, "$options": "i"}},
            {"category": {"$regex": escaped_keyword, "$options": "i"}},
        ]
    }

    try:
        articles = news_collection.find(query).sort(
            "published_at",
            DESCENDING,
        ).limit(limit)
        return jsonify([serialize_document(article) for article in articles]), 200
    except PyMongoError:
        return _error("Could not search news in the database.", 503)


@app.get("/news/category/<category>")
def get_news_by_category(category: str):
    matching_category = next(
        (
            known_category
            for known_category in ARTICLE_CATEGORIES
            if known_category.casefold() == category.casefold()
        ),
        None,
    )
    if matching_category is None:
        return _error("Invalid news category.", 400)

    limit, error_response = _read_limit()
    if error_response:
        return error_response

    try:
        articles = news_collection.find(
            {"category": matching_category}
        ).sort("published_at", DESCENDING).limit(limit)
        return jsonify([serialize_document(article) for article in articles]), 200
    except PyMongoError:
        return _error("Could not retrieve news for that category.", 503)


@app.get("/news/<article_id>")
def get_news_article(article_id: str):
    if not ObjectId.is_valid(article_id):
        return _error("Article id must be a valid MongoDB ObjectId.", 400)

    try:
        article = news_collection.find_one({"_id": ObjectId(article_id)})
    except PyMongoError:
        return _error("Could not retrieve the article from the database.", 503)

    if article is None:
        return _error("Article not found.", 404)
    return jsonify(serialize_document(article)), 200


@app.get("/briefings")
def get_briefings():
    limit, error_response = _read_limit()
    if error_response:
        return error_response

    try:
        briefings = daily_briefings_collection.find().sort(
            "briefing_date",
            DESCENDING,
        ).limit(limit)
        return jsonify([serialize_document(briefing) for briefing in briefings]), 200
    except PyMongoError:
        return _error("Could not retrieve briefings from the database.", 503)


@app.get("/briefings/<briefing_date>")
def get_briefing_by_date(briefing_date: str):
    try:
        parsed_date = date.fromisoformat(briefing_date)
    except ValueError:
        return _error("Date must use YYYY-MM-DD format.", 400)

    try:
        briefing = daily_briefings_collection.find_one(
            {"briefing_date": parsed_date.isoformat()}
        )
    except PyMongoError:
        return _error("Could not retrieve the briefing from the database.", 503)

    if briefing is None:
        return _error("Briefing not found.", 404)
    return jsonify(serialize_document(briefing)), 200


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    connect_to_database()
    create_indexes()
    scheduler = start_scheduler()
    try:
        app.run(host="127.0.0.1", port=5000)
    finally:
        scheduler.shutdown(wait=False)
