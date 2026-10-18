# Daily Global Tech News Scheduler

A beginner-friendly Python and MongoDB project that collects technology news
and prepares a daily briefing.

## Stage 2: Project settings

This stage adds environment-based settings and lists the libraries the project
uses.

### Setup

Use Python 3.10 or newer. From the project folder, create and activate a virtual
environment in PowerShell, then install the requirements:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
pip install -r requirements.txt
```

Edit `.env` for your local machine. It is ignored by Git; commit only
`.env.example`, which contains no real credentials.

### Environment variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `MONGODB_URI` | MongoDB server connection string | `mongodb://localhost:27017` |
| `MONGODB_DATABASE` | Database used by the app | `tech_news` |
| `NEWS_API_URL` | GNews search endpoint | `https://gnews.io/api/v4/search` |
| `NEWS_API_KEY` | Your GNews key, stored only in `.env` | Empty; add your key |
| `NEWS_SEARCH_QUERY` | Search terms sent to GNews | Technology, AI, cybersecurity, and quantum terms |
| `NEWS_MAX_RESULTS` | Maximum articles requested, from 1 to 100 | `10` |
| `NEWS_SCHEDULE_HOUR` | Daily run hour, from 0 to 23 | `6` |
| `NEWS_SCHEDULE_MINUTE` | Daily run minute, from 0 to 59 | `0` |
| `NEWS_TIMEZONE` | Timezone used by the scheduler | `UTC` |

The schedule hour, minute, and maximum result count are parsed as integers and
checked when `config.py` loads. Invalid values raise a clear configuration
error instead of silently choosing different settings.

## Stage 3: MongoDB connection

`database.py` creates handles for the `news` and `daily_briefings` collections.
Call `connect_to_database()` to test the MongoDB connection, then call
`create_indexes()` to make article URLs and briefing dates unique. MongoDB
creates the database and collections when the first data or index is written.

Start your local MongoDB server before testing this stage. The connection check
uses a five-second server-selection timeout and reports a safe, actionable
message if the server cannot be reached.

## Stage 4: Fetch, categorize, and store news

This stage uses the GNews Search API. Create an account at [GNews](https://gnews.io/)
and put its API key in your local `.env` file as `NEWS_API_KEY`. The key is sent
to GNews as a request parameter and is never included in application error
messages. `NEWS_SEARCH_QUERY` and `NEWS_MAX_RESULTS` let you adjust the articles
requested; the default maximum is 10, which fits GNews' free-plan per-request
limit. The free plan delays news by 12 hours, so the briefing may not include
breaking stories published shortly before its 6:00 AM run.

`news_service.py` makes a request with a 10-second timeout, checks the HTTP
response and JSON shape, and normalizes articles into the fields stored in
MongoDB. It categorizes articles with the editable `CATEGORY_KEYWORDS`
dictionary. `store_articles()` creates the unique indexes and inserts articles;
if the URL already exists, that article is skipped. An empty `articles` list is
a valid response and stores zero articles.

The collector needs both a valid GNews API key and a running MongoDB server.
The API key is not included in `.env.example`; keep it only in `.env`.

## Stage 5: Rank stories and generate the daily briefing

`briefing_service.py` reviews articles published or collected during the last
three days. Its transparent score gives 3 points to a priority category, 2
points for each of up to three impact words in the title (such as “launches” or
“breach”), and 2 points for an article from the last day or 1 point for one from
the previous two days. Higher-scoring and newer stories are considered first.
Repeated normalized titles are skipped, and each section contains at most two
stories.

The service groups categories into the requested briefing sections, uses the
source description as a concise summary, and attaches a category-based
“why it matters” explanation. It also suggests a learning topic and career
skills based on the highest-scoring selected story. This is a simple,
rule-based briefing—not an AI-generated fact check or summary.

`generate_daily_briefing()` stores the briefing in `daily_briefings`, using the
configured timezone for its date. Re-running it for the same date updates that
date's briefing rather than creating a second one. It also prints the briefing
in the terminal. This module is ready for the scheduler to call in a later
stage.

## Stage 6: Read-only REST API

`main.py` provides a small Flask API. Start it with MongoDB running:

```powershell
python main.py
```

The server listens on `http://127.0.0.1:5000`. These endpoints return JSON:

| Method and path | Purpose |
| --- | --- |
| `GET /health` | Check the API and MongoDB connection |
| `GET /news` | List latest news; optional `?limit=20` |
| `GET /news/<id>` | Retrieve an article by its MongoDB ObjectId |
| `GET /news/category/<category>` | Filter news by a supported category |
| `GET /news/search?keyword=python` | Search title, description, and category |
| `GET /briefings` | List recent briefings; optional `?limit=20` |
| `GET /briefings/YYYY-MM-DD` | Retrieve a briefing for a date |

The optional `limit` must be between 1 and 100. Invalid limits, categories,
article IDs, dates, and missing search keywords return HTTP 400. A valid but
unknown article or briefing returns HTTP 404. Database availability errors
return HTTP 503 with a short message. MongoDB `ObjectId` and date values are
converted to strings for JSON responses. Use Postman to send these GET
requests; no request body is required.

### Test in Postman

1. Start the app with `python main.py`.
2. Create a GET request in Postman and enter a URL, such as
   `http://127.0.0.1:5000/news?limit=5`.
3. Select **Send**. Check the HTTP status and JSON response body.
4. Try `http://127.0.0.1:5000/news/search?keyword=python` and
   `http://127.0.0.1:5000/news/category/AI`.
5. Copy an article `_id` from the news response to try `/news/<id>`. Use a
   briefing date such as `/briefings/2026-10-18` to request a specific date.

Example successful response for `GET /health`:

```json
{
  "status": "ok",
  "database": "connected"
}
```

Example successful response for `GET /news` (article fields can vary):

```json
[
  {
    "_id": "67123456789abcdef0123456",
    "title": "Example technology headline",
    "description": "A short description from the news source.",
    "source": "Example News",
    "author": null,
    "url": "https://example.com/news",
    "category": "AI",
    "published_at": "2026-10-18T05:00:00+00:00",
    "collected_at": "2026-10-18T06:00:00+00:00"
  }
]
```

Example error response for an invalid category (HTTP 400):

```json
{
  "error": "Invalid news category."
}
```

### TechPulse browser dashboard

Open `http://127.0.0.1:5000/` while the Flask app is running. The responsive
TechPulse dashboard shows the database/API connection, recent MongoDB stories,
topic filters, keyword search, a saved daily briefing, scheduler controls, and
a live coverage chart built from the latest 100 stories. The chart summarizes
topic counts and distinct publishers. Select a briefing date to view an earlier
one. Story links open the original publisher in a new tab. The page uses
vanilla JavaScript to call the same REST endpoints that Postman uses; no
separate frontend server or build step is needed.

The **Automatic news refresh** controls can set the running scheduler to every
1 minute, 5 minutes, 1 hour, or 1 day. The browser checks scheduler status and
refreshes the visible stories and selected date's briefing after each job
finishes. This selection is in memory and resets to the configured daily
schedule when the app restarts. The app must remain running. Frequent GNews
requests may exceed your provider's plan quota; use the one-minute option only
for a short test.

`GET /scheduler` reports the active schedule and the previous job result.
`POST /scheduler` accepts JSON such as `{"interval_minutes": 5}`. Only 1, 5,
60, and 1440 minutes are supported; changing it requires the scheduler to be
running.

## Stage 7: Daily scheduler

`scheduler.py` uses APScheduler to run the collection and briefing workflow
every day at `NEWS_SCHEDULE_HOUR:NEWS_SCHEDULE_MINUTE` in `NEWS_TIMEZONE`.
Defaults are 6:00 AM UTC. Set a timezone such as `Asia/Kolkata` in `.env` if
you want the run at 6:00 AM local time. The app process must stay running for
the in-process scheduler to execute.

Starting `python main.py` checks MongoDB, creates the indexes, starts the
scheduler, then starts Flask. The daily job fetches and stores news before
generating the briefing. If collection fails, it logs a safe error and does
not create a briefing from an incomplete collection run. If MongoDB fails
during saving, it logs a safe message. A duplicate scheduler run is prevented
by `max_instances=1`, and missed runs have a one-hour grace period. When the
Flask server stops, its scheduler is shut down too.

For a quick demonstration without waiting until the scheduled time, run
collection and briefing manually using the Stage 4 and Stage 5 commands.

## Stage 8: Test and demonstrate the project

Run the automated tests from the project folder:

```powershell
python -m unittest discover -s tests -v
```

The tests use mocked news responses and MongoDB collections. They check
categorization, API response normalization, duplicate handling, briefing
selection and persistence, REST status codes, JSON serialization, and the
scheduled job flow. They do not require a live API key or running MongoDB.

### Inspect data in MongoDB Compass

1. Start MongoDB and open MongoDB Compass.
2. Connect with the same `MONGODB_URI` configured in `.env` (for local MongoDB,
   `mongodb://localhost:27017`).
3. Open the `tech_news` database.
4. Select `news` to inspect article documents, including their category, URL,
   and dates.
5. Select `daily_briefings` to inspect generated briefing documents and their
   selected stories.

### Final demonstration checklist

1. Activate the project virtual environment and start MongoDB.
2. Run `python main.py`; explain that it checks the database, creates indexes,
   starts the daily scheduler, and starts the REST API.
3. For an immediate demonstration, run the Stage 4 collection command and the
   Stage 5 briefing command in separate PowerShell terminals.
4. Show the `news` and `daily_briefings` collections in MongoDB Compass.
5. In Postman, call `/health`, `/news`, `/news/category/AI`, and
   `/news/search?keyword=python`.
6. Copy an article ID from `/news` and retrieve it with `/news/<id>`.
7. Retrieve generated briefing history with `/briefings` and a specific date
   with `/briefings/YYYY-MM-DD`.
8. Explain the complete flow: scheduler → GNews → validation and categories →
   MongoDB → relevance scoring → briefing → MongoDB and REST API.
9. Explain that stopping the app stops its in-process scheduler.

Never show or share the contents of `.env` during a demonstration. The
`.gitignore` excludes `.env` and `.env.*`, while `.env.example` remains
shareable and contains no real key.

### Learning concepts covered

The stages use variables, strings, numbers, lists, dictionaries, tuples, sets,
functions, parameters, return values, loops, conditionals, modules, exceptions,
JSON, environment variables, HTTP requests, date/time, and scheduling.
MongoDB practice includes databases, collections, documents, ObjectIds,
inserts, finds, updates, filters, sorting, and unique indexes. Deleting records
is not part of the application because this project only needs to collect and
read news.