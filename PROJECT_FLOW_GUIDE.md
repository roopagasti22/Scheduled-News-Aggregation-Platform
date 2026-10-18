# Daily Global Tech News Scheduler — Project Guide

This guide explains how the project collects technology news, saves it to
MongoDB, prepares a briefing, and serves the saved data through Flask APIs.
It is written as a walkthrough for a first Python backend project.

## 1. Complete project flow

```text
App starts
   │
   ├── Connect to MongoDB and create unique indexes
   ├── Start APScheduler in the background
   └── Start the Flask web server

At the configured schedule time:
   APScheduler
       │ calls
       ▼
   run_daily_job()
       │
       ├── collect_and_store_news()
       │      ├── fetch_news() calls the GNews REST API
       │      ├── Python validates and normalizes its JSON
       │      ├── Python categorizes each article
       │      └── MongoDB stores new articles; duplicate URLs are skipped
       │
       └── generate_daily_briefing()
              ├── Reads recent articles from MongoDB
              ├── Scores and selects stories for briefing sections
              ├── Saves the briefing to MongoDB
              └── Prints the briefing in the terminal

Browser or Postman
       │ sends GET request to Flask
       ▼
   Flask reads MongoDB and returns JSON
```

The API and dashboard read stories that have already been collected. A
`GET /news` request does **not** call GNews or start a collection run. News
collection is performed by the scheduled job (or by running the collection
function manually from Python).

### Startup, step by step

When you run `python main.py`, the `if __name__ == "__main__"` block in
`main.py` performs these actions in order:

1. Sets up application logging.
2. Calls `connect_to_database()` to ping MongoDB. If MongoDB is unavailable,
   startup reports an error instead of pretending it connected.
3. Calls `create_indexes()` to create the unique indexes used for duplicate
   protection.
4. Calls `start_scheduler()` to start the background schedule.
5. Calls `app.run(...)` to start the Flask server on
   `http://127.0.0.1:5000/`.

The scheduler and Flask server run inside the same Python application process.
The dashboard is served by Flask; it is not a separate frontend server.

### What happens during one scheduled run?

1. `run_daily_job()` marks the job as running.
2. `collect_and_store_news()` calls `fetch_news()`.
3. `fetch_news()` sends an HTTP GET request to GNews using settings from
   environment variables, including `NEWS_API_KEY`. The key should be stored
   in the private `.env` file, not written in source code.
4. Python checks the HTTP response and JSON structure, then validates article
   fields such as title, URL, source, description, and publication date.
5. Python assigns a category using the keyword rules in
   `news_service.py`.
6. `store_articles()` attempts to insert each normalized article into the
   MongoDB `tech_news.news` collection.
7. If collection succeeds, `generate_daily_briefing()` reads recent documents,
   ranks eligible articles, fills briefing sections, and saves the result to
   `tech_news.daily_briefings`.
8. The job records its completion status. The dashboard polls `/scheduler`;
   after it notices a completed run, it reloads the visible news and briefing.

If fetching or saving news fails, the job logs a failure and does not generate
a briefing from a failed collection run. A briefing can contain fewer stories
than were collected: it selects only the higher-scoring eligible articles and
limits each section.

## 2. Why use a scheduler, and how does it call Python?

A scheduler automates work that should happen at a certain time or interval.
Without it, a person would have to remember to run the collection and briefing
commands every day. APScheduler lets the application perform those steps
automatically while the application process is running.

### How the trigger works in this project

In `scheduler.py`, `create_scheduler()` creates an APScheduler
`BackgroundScheduler`. It adds a job with:

- The Python function to call: `run_daily_job`
- A cron trigger using the configured hour and minute
- The configured timezone
- A stable job ID: `daily_tech_news_briefing`

`start_scheduler()` starts that scheduler. APScheduler keeps track of the next
scheduled time in a background thread. When the trigger time arrives, its
executor calls the registered Python function, effectively doing the
equivalent of:

```python
run_daily_job()
```

You do not have to call that function from a browser request. The scheduler
calls it when its trigger is due. That function then calls the news collector
and, if collection succeeds, the briefing generator.

### Default time and dashboard interval choices

The default configuration is **6:00 AM UTC**:

- `NEWS_SCHEDULE_HOUR=6`
- `NEWS_SCHEDULE_MINUTE=0`
- `NEWS_TIMEZONE=UTC` (default)

Change the timezone if 6:00 AM should mean a local time, for example
`NEWS_TIMEZONE=Asia/Kolkata`. The configured time is interpreted in that
timezone.

The dashboard can change the active job to every 1 minute, 5 minutes, 1 hour,
or 1 day. These changes are held in memory and are not saved between app
restarts. After restarting, the schedule returns to the configured daily
hour/minute. Frequent GNews requests may use up the API plan's quota.

The Flask dashboard's **Refresh briefing** button reloads the displayed data;
it does not itself fetch news from GNews. A scheduled collection or a deliberate
manual Python collection is needed to fetch new external data.

## 3. What if the application is stopped at the scheduled time?

The scheduler is part of the running Python process. If the application is
stopped at 7:00 AM when the job is due:

1. APScheduler is not running, so it cannot call `run_daily_job()`.
2. No API request is sent to GNews at that time.
3. No articles or briefing are created by that missed run.
4. When the application starts again, it creates a new in-memory scheduler.
5. It schedules the **next upcoming** run. For a daily 7:00 AM schedule,
   restarting after 7:00 AM normally means the next run is 7:00 AM the
   following day.

This application does not use a persistent APScheduler job store or an
automatic catch-up-on-startup task. Although the configured job has a
one-hour misfire grace period, that is not a promise to recover work missed
while the entire application process was stopped; the scheduler was not alive
to track that trigger. The grace period can apply when an active scheduler is
temporarily unable to dispatch a due job.

### If a run was missed

- Start the app again so the API and next scheduled run become available.
- To collect immediately, deliberately run the collection function once from
  the project directory:

  ```powershell
  .\.venv\Scripts\python.exe -c "from news_service import collect_and_store_news; print('New articles stored:', collect_and_store_news())"
  ```

- If you also need a briefing immediately, run the briefing generator:

  ```powershell
  .\.venv\Scripts\python.exe -c "from briefing_service import generate_daily_briefing; generate_daily_briefing()"
  ```

These are manual commands: the current REST API does not expose a route that
starts a collection run.

For reliable always-on production scheduling, the process must be hosted on an
always-running machine or service. That is beyond this beginner project; simply
closing the terminal or stopping the app also stops its in-process scheduler.

## 4. How does the project prevent duplicate news?

The project uses MongoDB to enforce article uniqueness, rather than relying
only on Python to check first.

### Article duplicate protection: unique URL index

`database.py` creates a unique MongoDB index on the `url` field in the `news`
collection:

```python
news_collection.create_index(
    [("url", ASCENDING)],
    unique=True,
    name="unique_news_url",
)
```

When `store_articles()` inserts an article:

1. MongoDB checks the URL against the unique index.
2. If that URL is new, MongoDB inserts the document.
3. If that URL already exists, MongoDB rejects the insert with
   `DuplicateKeyError`.
4. `store_articles()` catches that specific duplicate error and skips that
   article, then continues with the remaining articles.

The returned count means **new documents inserted**, not the total number of
articles returned by GNews. Therefore, `New articles stored: 0` can mean that
the API returned stories, but every URL was already in MongoDB.

This matches exact URL strings. If two publishers provide different URLs for
the same underlying story, the database can treat them as different articles.
The briefing generator separately normalizes titles and avoids repeating a
matching title in its selected briefing, but that title check does not delete
or merge documents in the `news` collection.

### Briefing duplicate protection: unique date index

MongoDB also has a unique index on `briefing_date` in `daily_briefings`.
The briefing generator uses an upsert for that date. Running the briefing more
than once for the same day updates that day's briefing rather than creating
another briefing document for the same date.

## 5. How data travels from GNews to MongoDB, Flask, and Postman

Here is the complete request-and-data path:

### A. GNews API → Python

`news_service.fetch_news()` sends an HTTP GET request to the configured GNews
endpoint. It sends the search query, language, maximum result count, and API
key as request parameters.

GNews returns JSON containing an `articles` list. Python checks the HTTP status
and handles network timeouts, request failures, invalid JSON, and unexpected
response shapes. Each article is validated and converted to the fields the
project expects:

```json
{
  "title": "Example technology headline",
  "description": "The source's description of the story.",
  "source": "Example News",
  "author": null,
  "url": "https://example.com/news/story",
  "category": "AI",
  "published_at": "2026-10-18T10:00:00+00:00",
  "collected_at": "2026-10-18T10:05:00+00:00"
}
```

Python classifies the article by matching editable keywords against its title
and description. For example, a title or description containing `quantum` or
`qubit` is categorized as Quantum Computing, according to the configured rule
order.

### B. Python → MongoDB

`collect_and_store_news()` passes the normalized articles to
`store_articles()`. PyMongo sends insert operations to MongoDB:

- Database: `tech_news` by default
- Article collection: `news`
- Briefing collection: `daily_briefings`

MongoDB stores article documents and assigns each one an `_id` ObjectId. The
unique URL index prevents the same URL from being inserted a second time.

After collection, `generate_daily_briefing()` reads eligible recent documents,
scores and groups selected stories, and writes a briefing document for the
configured local date.

### C. Postman → Flask REST API → MongoDB → Postman

Postman sends an HTTP request to Flask. For example:

```http
GET http://127.0.0.1:5000/news?limit=10
```

The route in `main.py` queries the MongoDB `news` collection, sorts the
documents by publication date, applies the limit, converts MongoDB-specific
values to JSON-safe strings, and returns a JSON response with an HTTP status
code.

So the read path is:

```text
Postman --HTTP GET--> Flask route --PyMongo query--> MongoDB
Postman <--JSON + HTTP status---------------------- Flask
```

The news collection path is different:

```text
Scheduled Python job --HTTP GET--> GNews
Scheduled Python job --PyMongo inserts--> MongoDB
```

Postman is a tool for sending and inspecting HTTP requests; it does not itself
fetch the GNews articles or write to MongoDB unless an API route is explicitly
implemented to do that. In this project, the listed news and briefing routes
are read routes.

### Useful Postman requests

Start `main.py`, then send these requests in Postman:

| Method | URL | What it returns |
| --- | --- | --- |
| `GET` | `http://127.0.0.1:5000/health` | API and MongoDB health |
| `GET` | `http://127.0.0.1:5000/news?limit=10` | Latest saved articles |
| `GET` | `http://127.0.0.1:5000/news/search?keyword=python` | Articles matching a keyword |
| `GET` | `http://127.0.0.1:5000/news/category/AI` | Saved AI articles |
| `GET` | `http://127.0.0.1:5000/news/<article_id>` | One saved article by its MongoDB ID |
| `GET` | `http://127.0.0.1:5000/briefings` | Saved briefing history |
| `GET` | `http://127.0.0.1:5000/briefings/2026-10-18` | Briefing for one date |

For GET requests, no request body is required. Flask returns an error response
with an appropriate HTTP status if input is invalid, a record is missing, or
MongoDB cannot be reached.

## 6. Which file is responsible for each part?

| File | Responsibility |
| --- | --- |
| `config.py` | Reads settings such as API key, MongoDB URI, run time, and timezone |
| `news_service.py` | Calls GNews, validates/normalizes articles, categorizes, and stores articles |
| `database.py` | Connects to MongoDB and creates collections/indexes |
| `briefing_service.py` | Scores articles, builds briefing sections, and saves/prints the briefing |
| `scheduler.py` | Registers and runs the background scheduled Python function |
| `main.py` | Starts Flask and defines REST API routes |
| `models.py` | Converts ObjectIds and dates into JSON-serializable values |
| `templates/index.html` | Provides the TechPulse dashboard page structure |
| `static/app.js` | Loads API data and powers search, filters, analytics, and scheduler controls |
| `static/styles.css` | Styles the responsive dashboard |

## 7. Key ideas to remember

1. **GNews is the external source.** Python requests its JSON; Postman does not
   collect the articles.
2. **MongoDB is persistent storage.** The dashboard and API read saved
   documents from it.
3. **The scheduler only runs while the application process is alive.**
4. **The unique URL index is the main duplicate-article safeguard.**
5. **A zero insert count is not necessarily an error.** It may mean every
   returned article was already stored.
6. **A dashboard refresh reloads stored data.** It does not trigger a new
   external news request.
7. **Postman tests Flask endpoints.** Flask queries MongoDB and returns JSON.
