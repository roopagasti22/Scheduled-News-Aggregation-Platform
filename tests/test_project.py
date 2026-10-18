import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import requests
from bson import ObjectId
from pymongo.errors import DuplicateKeyError, ServerSelectionTimeoutError

import briefing_service
import main
import news_service
import scheduler


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeCursor:
    def __init__(self, documents):
        self.documents = documents
        self.limit_value = None

    def sort(self, *_args):
        self.sort_arguments = _args
        return self

    def limit(self, limit):
        self.limit_value = limit
        return self

    def __iter__(self):
        return iter(self.documents[:self.limit_value])


class NewsCollectionTests(unittest.TestCase):
    def test_categories_match_specialized_topics_before_ai(self):
        self.assertEqual(
            news_service.categorize_article("AI agent launches", "An AI tool"),
            "Agentic AI",
        )
        self.assertEqual(
            news_service.categorize_article("Quantum chip", "A qubit advance"),
            "Quantum Computing",
        )
        self.assertEqual(
            news_service.categorize_article("AI model", "Machine learning news"),
            "AI",
        )

    @patch.object(news_service, "NEWS_API_KEY", "test-key")
    @patch.object(news_service.requests, "get")
    def test_fetch_news_normalizes_gnews_json(self, get):
        get.return_value = FakeResponse(
            {
                "articles": [
                    {
                        "title": "Quantum computer launches",
                        "description": "A new qubit design.",
                        "source": {"name": "Example News"},
                        "url": "https://example.test/quantum",
                        "publishedAt": "2026-10-18T10:00:00Z",
                    }
                ]
            }
        )

        articles = news_service.fetch_news()

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["category"], "Quantum Computing")
        self.assertEqual(articles[0]["source"], "Example News")
        self.assertIsNone(articles[0]["author"])
        self.assertEqual(
            articles[0]["published_at"],
            datetime(2026, 10, 18, 10, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(get.call_args.kwargs["params"]["apikey"], "test-key")

    @patch.object(news_service, "NEWS_API_KEY", "test-key")
    @patch.object(news_service.requests, "get")
    def test_fetch_news_reports_timeout(self, get):
        get.side_effect = requests.Timeout

        with self.assertRaisesRegex(news_service.NewsAPIError, "timed out"):
            news_service.fetch_news()

    @patch.object(news_service, "create_indexes")
    @patch.object(news_service, "news_collection")
    def test_store_articles_skips_duplicate_url(self, collection, create_indexes):
        article = {"url": "https://example.test/story"}
        collection.insert_one.side_effect = [Mock(), DuplicateKeyError("duplicate")]

        stored_count = news_service.store_articles([article, article])

        self.assertEqual(stored_count, 1)
        create_indexes.assert_called_once_with()
        self.assertEqual(collection.insert_one.call_count, 2)


class BriefingTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 18, 6, 0, tzinfo=timezone.utc)
        self.recent_article = {
            "title": "AI company launches a major breakthrough",
            "description": "A useful first sentence. A second sentence.",
            "source": "Example News",
            "url": "https://example.test/ai",
            "category": "AI",
            "published_at": self.now - timedelta(hours=2),
            "collected_at": self.now - timedelta(hours=1),
        }

    def test_score_prioritizes_recent_impactful_story(self):
        older_article = dict(
            self.recent_article,
            published_at=self.now - timedelta(days=2),
        )

        self.assertGreater(
            briefing_service.score_article(self.recent_article, self.now),
            briefing_service.score_article(older_article, self.now),
        )

    @patch.object(briefing_service, "create_indexes")
    @patch.object(briefing_service, "daily_briefings_collection")
    @patch.object(briefing_service, "news_collection")
    @patch.object(briefing_service, "NEWS_TIMEZONE", "Asia/Kolkata")
    def test_generate_briefing_saves_and_prints(self, news, briefings, create_indexes):
        news.find.return_value = [
            self.recent_article,
            dict(
                self.recent_article,
                title="AI company launches a major breakthrough!",
                url="https://example.test/duplicate",
            ),
        ]
        output = StringIO()

        with redirect_stdout(output):
            result = briefing_service.generate_daily_briefing(self.now)

        self.assertEqual(
            result["briefing_date"],
            self.now.astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat(),
        )
        self.assertEqual(result["total_news"], 2)
        self.assertEqual(len(result["top_news"]["AI"]), 1)
        self.assertIn("LEARNING OF THE DAY", output.getvalue())
        self.assertIn("CAREER OPPORTUNITY", output.getvalue())
        create_indexes.assert_called_once_with()
        saved_update = briefings.update_one.call_args
        self.assertTrue(saved_update.kwargs["upsert"])
        self.assertIn("$setOnInsert", saved_update.args[1])


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = main.app.test_client()
        self.article_id = ObjectId()
        self.article = {
            "_id": self.article_id,
            "title": "Python cloud tools",
            "description": "A developer tools update.",
            "source": "Example News",
            "url": "https://example.test/tools",
            "category": "Cloud",
            "published_at": datetime(2026, 10, 18, tzinfo=timezone.utc),
        }
        self.briefing = {
            "_id": ObjectId(),
            "briefing_date": "2026-10-18",
            "generated_at": datetime(2026, 10, 18, tzinfo=timezone.utc),
            "top_news": {
                "CLOUD & SOFTWARE": [
                    {"published_at": datetime(2026, 10, 18, tzinfo=timezone.utc)}
                ]
            },
        }
        self.news = Mock()
        self.news.find.return_value = FakeCursor([self.article])
        self.news.find_one.return_value = self.article
        self.briefings = Mock()
        self.briefings.find.return_value = FakeCursor([self.briefing])
        self.briefings.find_one.return_value = self.briefing
        self.patches = [
            patch.object(main, "news_collection", self.news),
            patch.object(main, "daily_briefings_collection", self.briefings),
            patch.object(main, "client"),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_dashboard_page_loads(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"TechPulse", response.data)
        self.assertIn(b"Latest stories", response.data)
        self.assertIn(b"Today", response.data)

    def test_news_and_briefing_responses_are_json_serializable(self):
        response = self.client.get("/news?limit=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json[0]["_id"], str(self.article_id))

        response = self.client.get("/briefings")
        self.assertEqual(response.status_code, 200)
        nested_date = response.json[0]["top_news"]["CLOUD & SOFTWARE"][0][
            "published_at"
        ]
        self.assertEqual(nested_date, "2026-10-18T00:00:00+00:00")

    def test_invalid_input_and_missing_records_have_expected_status(self):
        self.assertEqual(self.client.get("/news?limit=101").status_code, 400)
        self.assertEqual(self.client.get("/news/category/unknown").status_code, 400)
        self.assertEqual(self.client.get("/news/search").status_code, 400)
        self.assertEqual(
            self.client.get("/briefings/2026-99-99").status_code,
            400,
        )
        self.news.find_one.return_value = None
        self.assertEqual(
            self.client.get("/news/000000000000000000000001").status_code,
            404,
        )

    def test_database_unavailable_health_response_is_safe(self):
        main.client.admin.command.side_effect = ServerSelectionTimeoutError(
            "internal connection detail"
        )

        response = self.client.get("/health")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json,
            {"status": "unavailable", "error": "Database is unavailable."},
        )
        self.assertNotIn("internal", str(response.json))

    @patch.object(main, "get_schedule_status")
    def test_scheduler_settings_are_available_to_dashboard(self, get_status):
        get_status.return_value = {
            "running": True,
            "interval_minutes": 5,
            "next_run_time": "2026-10-18T10:05:00+00:00",
        }

        response = self.client.get("/scheduler")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["interval_minutes"], 5)

    @patch.object(main, "set_schedule_interval")
    def test_scheduler_settings_accepts_supported_interval(self, set_interval):
        set_interval.return_value = {
            "running": True,
            "interval_minutes": 60,
            "interval_label": "Every hour",
        }

        response = self.client.post(
            "/scheduler",
            json={"interval_minutes": 60},
        )

        self.assertEqual(response.status_code, 200)
        set_interval.assert_called_once_with(60)

    def test_scheduler_settings_rejects_invalid_interval(self):
        response = self.client.post(
            "/scheduler",
            json={"interval_minutes": 10},
        )

        self.assertEqual(response.status_code, 400)


class SchedulerTests(unittest.TestCase):
    @patch.object(scheduler, "generate_daily_briefing")
    @patch.object(scheduler, "collect_and_store_news")
    def test_daily_job_collects_then_generates_briefing(self, collect, generate):
        collect.return_value = 2

        scheduler.run_daily_job()

        collect.assert_called_once_with()
        generate.assert_called_once_with()

    @patch.object(scheduler, "generate_daily_briefing")
    @patch.object(scheduler, "collect_and_store_news")
    def test_daily_job_does_not_generate_after_collection_failure(
        self,
        collect,
        generate,
    ):
        collect.side_effect = news_service.NewsServiceError("API unavailable")

        scheduler.run_daily_job()

        generate.assert_not_called()

    @patch.object(scheduler, "_scheduler")
    def test_setting_schedule_interval_reschedules_job(self, active_scheduler):
        active_scheduler.running = True
        active_scheduler.get_job.return_value = Mock(
            next_run_time=datetime(2026, 10, 18, 10, 5, tzinfo=timezone.utc)
        )

        with patch.object(scheduler, "_schedule_mode", "daily"), patch.object(
            scheduler,
            "_schedule_interval_minutes",
            1440,
        ):
            status = scheduler.set_schedule_interval(5)

        active_scheduler.reschedule_job.assert_called_once_with(
            "daily_tech_news_briefing",
            trigger="interval",
            minutes=5,
        )
        self.assertEqual(status["interval_minutes"], 5)
        self.assertEqual(status["interval_label"], "Every 5 minutes")

    def test_setting_unsupported_schedule_interval_fails(self):
        with self.assertRaises(ValueError):
            scheduler.set_schedule_interval(10)


if __name__ == "__main__":
    unittest.main()
