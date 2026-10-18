const state = {
  category: "",
  keyword: "",
  limit: 10,
  loadingMore: false,
  lastCompletedRun: undefined,
};

const categoryColors = {
  "AI": "dot-violet",
  "Agentic AI": "dot-blue",
  "Quantum Computing": "dot-cyan",
  "Cloud": "dot-orange",
  "Cybersecurity": "dot-red",
  "Programming": "dot-green",
  "Developer Tools": "dot-yellow",
  "Startups": "dot-pink",
  "Technology Companies": "dot-gray",
  "Other Technology": "dot-gray",
};

const $ = (selector) => document.querySelector(selector);

function makeElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

async function getJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `Request failed (${response.status}).`);
  }
  return data;
}

function formatDate(value, options = { month: "short", day: "numeric", year: "numeric" }) {
  if (!value) return "Date unavailable";
  const parsedDate = new Date(value);
  if (Number.isNaN(parsedDate.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat(undefined, options).format(parsedDate);
}

function formatRelativeDate(value) {
  if (!value) return "Recently collected";
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return "Recently collected";
  const hours = Math.max(0, Math.floor((Date.now() - timestamp) / 3600000));
  if (hours < 1) return "Just now";
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days} days ago`;
  return formatDate(value, { month: "short", day: "numeric" });
}

function updateConnection(isOnline, label) {
  const dot = $("#health-dot");
  dot.classList.toggle("online", isOnline);
  dot.classList.toggle("offline", !isOnline);
  $("#health-label").textContent = label;
}

async function loadHealth() {
  try {
    await getJson("/health");
    updateConnection(true, "All systems operational");
  } catch {
    updateConnection(false, "Connection unavailable");
  }
}

function formatLocalDateTime(value) {
  if (!value) return "not scheduled";
  const parsedDate = new Date(value);
  if (Number.isNaN(parsedDate.getTime())) return "not scheduled";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(parsedDate);
}

function selectScheduleOption(minutes) {
  document.querySelectorAll(".schedule-option").forEach((button) => {
    button.classList.toggle("selected", Number(button.dataset.interval) === minutes);
  });
}

function refreshDisplayedNews() {
  loadNews();
  loadBriefing($("#briefing-date").value || setTodayDate());
  loadAnalytics();
}

async function loadAnalytics() {
  const bars = $("#analytics-bars");
  try {
    const articles = await getJson("/news?limit=100");
    const categoryCounts = new Map();
    const sources = new Set();
    let aiAndSecurityCount = 0;

    for (const article of articles) {
      const category = article.category || "Other Technology";
      categoryCounts.set(category, (categoryCounts.get(category) || 0) + 1);
      if (article.source) sources.add(article.source);
      if (["AI", "Agentic AI", "Cybersecurity"].includes(category)) {
        aiAndSecurityCount += 1;
      }
    }

    const categories = [...categoryCounts.entries()]
      .sort((left, right) => right[1] - left[1])
      .slice(0, 5);
    const maximum = Math.max(1, ...categories.map(([, count]) => count));
    bars.replaceChildren();

    if (categories.length === 0) {
      bars.append(makeElement("div", "analytics-empty", "No topic data is available yet."));
    } else {
      for (const [category, count] of categories) {
        const row = makeElement("div", "analytics-row");
        const label = makeElement("span", "analytics-category", category);
        const track = makeElement("div", "analytics-track");
        const fill = makeElement("span", `analytics-fill ${categoryColors[category] || "dot-gray"}`);
        fill.style.width = `${Math.max(8, (count / maximum) * 100)}%`;
        track.append(fill);
        row.append(label, track, makeElement("strong", "analytics-count", String(count)));
        bars.append(row);
      }
    }

    $("#analytics-focus").textContent = `${aiAndSecurityCount}/${articles.length}`;
    $("#analytics-sources").textContent = String(sources.size);
    $("#analytics-updated").textContent = `Updated ${new Intl.DateTimeFormat(undefined, {
      hour: "numeric",
      minute: "2-digit",
    }).format(new Date())}`;
  } catch (error) {
    bars.replaceChildren(makeElement("div", "analytics-empty", error.message));
    $("#analytics-focus").textContent = "—";
    $("#analytics-sources").textContent = "—";
    $("#analytics-updated").textContent = "Analytics unavailable";
  }
}

async function loadSchedule() {
  try {
    const schedule = await getJson("/scheduler");
    selectScheduleOption(schedule.interval_minutes);
    if (!schedule.running) {
      $("#schedule-status").textContent = "Scheduler is not running.";
      return;
    }

    const nextRun = formatLocalDateTime(schedule.next_run_time);
    if (schedule.last_run_status === "running") {
      $("#schedule-status").textContent = `Collecting news now · next run ${nextRun}`;
    } else if (schedule.last_run_status === "failed") {
      $("#schedule-status").textContent = `Last collection failed · next run ${nextRun}`;
    } else if (schedule.last_run_completed_at) {
      $("#schedule-status").textContent =
        `Next run ${nextRun} · last run stored ${schedule.last_articles_stored ?? 0} new stories`;
    } else {
      $("#schedule-status").textContent = `Next automatic collection ${nextRun}`;
    }

    const completedRun = schedule.last_run_completed_at;
    if (state.lastCompletedRun !== undefined && completedRun &&
        completedRun !== state.lastCompletedRun) {
      refreshDisplayedNews();
    }
    state.lastCompletedRun = completedRun;
  } catch (error) {
    $("#schedule-status").textContent = error.message;
  }
}

async function updateSchedule(intervalMinutes) {
  const buttons = [...document.querySelectorAll(".schedule-option")];
  buttons.forEach((button) => { button.disabled = true; });
  $("#schedule-status").textContent = "Updating automatic schedule…";

  try {
    const response = await fetch("/scheduler", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ interval_minutes: intervalMinutes }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
    selectScheduleOption(data.interval_minutes);
    $("#schedule-status").textContent =
      `Schedule updated · next run ${formatLocalDateTime(data.next_run_time)}`;
  } catch (error) {
    $("#schedule-status").textContent = error.message;
    loadSchedule();
  } finally {
    buttons.forEach((button) => { button.disabled = false; });
  }
}

function clearStoryList() {
  $("#news-list").replaceChildren();
  $("#news-error").classList.add("hidden");
}

function createStoryCard(article) {
  const card = makeElement("article", "story-card");
  const topline = makeElement("div", "story-topline");
  const category = makeElement("span", "story-category");
  category.append(makeElement("span", `topic-dot ${categoryColors[article.category] || "dot-gray"}`));
  category.append(document.createTextNode(article.category || "Technology"));
  topline.append(category, makeElement("span", "story-time", formatRelativeDate(article.published_at)));

  const title = makeElement("h3");
  const titleLink = makeElement("a", "", article.title || "Untitled story");
  titleLink.href = article.url || "#";
  titleLink.target = "_blank";
  titleLink.rel = "noopener noreferrer";
  title.append(titleLink);

  const description = makeElement("p", "", article.description || "This story has no description from its source.");
  const footer = makeElement("div", "story-foot");
  footer.append(makeElement("span", "source-name", article.source || "Unknown source"));
  const readLink = makeElement("a", "read-link", "Read source ↗");
  readLink.href = article.url || "#";
  readLink.target = "_blank";
  readLink.rel = "noopener noreferrer";
  footer.append(readLink);
  card.append(topline, title, description, footer);
  return card;
}

function currentNewsUrl() {
  const params = new URLSearchParams({ limit: String(state.limit) });
  if (state.keyword) {
    params.set("keyword", state.keyword);
    return `/news/search?${params}`;
  }
  if (state.category) {
    return `/news/category/${encodeURIComponent(state.category)}?${params}`;
  }
  return `/news?${params}`;
}

async function loadNews() {
  clearStoryList();
  $("#empty-news").classList.add("hidden");
  $("#load-more").classList.add("hidden");
  $("#news-list").append(makeElement("div", "loading-card", "Loading stories…"));

  try {
    const articles = await getJson(currentNewsUrl());
    clearStoryList();
    $("#feed-count").textContent = `${articles.length} ${articles.length === 1 ? "STORY" : "STORIES"}`;
    $("#feed-heading").textContent = state.keyword
      ? `SEARCH: ${state.keyword.toUpperCase()}`
      : state.category
        ? state.category.toUpperCase()
        : "TODAY’S PICKS";

    if (articles.length === 0) {
      $("#empty-news").classList.remove("hidden");
      return;
    }

    for (const article of articles) {
      $("#news-list").append(createStoryCard(article));
    }
    $("#load-more").classList.remove("hidden");
  } catch (error) {
    clearStoryList();
    $("#news-error").textContent = error.message;
    $("#news-error").classList.remove("hidden");
  }
}

function createBriefingStory(story) {
  const wrapper = makeElement("div", "briefing-story");
  const link = makeElement("a", "", story.title || "Untitled story");
  link.href = story.url || "#";
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  wrapper.append(link);
  if (story.summary) wrapper.append(makeElement("p", "", story.summary));
  return wrapper;
}

function showBriefingError(message) {
  $("#briefing-sections").replaceChildren(makeElement("p", "briefing-empty", message));
  $("#briefing-summary").textContent = "Briefing information is not available right now.";
  $("#learning-text").textContent = "Try refreshing after the briefing has been generated.";
  $("#career-text").textContent = "Career signals will appear when a briefing is available.";
}

async function loadBriefing(dateValue) {
  const sections = $("#briefing-sections");
  sections.replaceChildren(makeElement("div", "briefing-loading", "Loading briefing…"));
  try {
    const briefing = await getJson(`/briefings/${encodeURIComponent(dateValue)}`);
    $("#briefing-date-label").textContent = briefing.briefing_date || dateValue;
    $("#briefing-summary").textContent =
      `${briefing.total_news || 0} stories reviewed across ${Object.keys(briefing.categories || {}).length} topic areas.`;
    $("#learning-text").textContent = briefing.learning_of_the_day || "No learning suggestion was saved.";
    $("#career-text").textContent = briefing.career_opportunity || "No career signal was saved.";
    $("#stat-stories").textContent = String(briefing.total_news || 0);
    $("#stat-topics").textContent = String(Object.keys(briefing.categories || {}).length);

    sections.replaceChildren();
    const groups = briefing.top_news || {};
    for (const [name, stories] of Object.entries(groups)) {
      const section = makeElement("section", "briefing-section");
      const heading = makeElement("div", "briefing-section-heading");
      heading.append(makeElement("span", "", name));
      heading.append(makeElement("span", "", String(stories.length)));
      section.append(heading);
      if (stories.length === 0) {
        section.append(makeElement("div", "briefing-empty", "No stories in this section today."));
      } else {
        for (const story of stories) section.append(createBriefingStory(story));
      }
      sections.append(section);
    }
    if (Object.keys(groups).length === 0) {
      sections.append(makeElement("p", "briefing-empty", "No sections are available."));
    }
  } catch (error) {
    $("#stat-stories").textContent = "—";
    $("#stat-topics").textContent = "—";
    showBriefingError(error.message === "Briefing not found."
      ? "No briefing was saved for this date."
      : error.message);
  }
}

function setCategory(category) {
  state.category = category;
  state.keyword = "";
  $("#search-input").value = "";
  state.limit = 10;
  document.querySelectorAll(".filter-chip").forEach((chip) => {
    chip.classList.toggle("selected", chip.dataset.category === category);
  });
  document.querySelectorAll(".topic-link").forEach((link) => {
    link.classList.toggle("selected", link.dataset.category === category);
  });
  loadNews();
}

function setTodayDate() {
  const now = new Date();
  const localDate = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 10);
  $("#briefing-date").value = localDate;
  $("#edition-date").textContent = formatDate(localDate, { month: "long", day: "numeric", year: "numeric" }).toUpperCase();
  return localDate;
}

$("#search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  state.keyword = $("#search-input").value.trim();
  state.category = "";
  state.limit = 10;
  document.querySelectorAll(".filter-chip, .topic-link").forEach((item) => {
    item.classList.toggle("selected", item.dataset.category === "");
  });
  loadNews();
});

document.querySelectorAll(".filter-chip, .topic-link").forEach((button) => {
  button.addEventListener("click", () => setCategory(button.dataset.category));
});

$("#briefing-date").addEventListener("change", (event) => {
  if (event.target.value) loadBriefing(event.target.value);
});

$("#refresh-button").addEventListener("click", () => {
  loadHealth();
  refreshDisplayedNews();
});

document.querySelectorAll(".schedule-option").forEach((button) => {
  button.addEventListener("click", () => updateSchedule(Number(button.dataset.interval)));
});

$("#load-more").addEventListener("click", () => {
  if (state.loadingMore) return;
  state.loadingMore = true;
  state.limit = Math.min(state.limit + 10, 100);
  loadNews().finally(() => {
    state.loadingMore = false;
    if (state.limit >= 100) {
      $("#load-more").classList.add("hidden");
      $("#load-more").textContent = "Maximum number of stories loaded";
    }
  });
});

$("#clear-filters").addEventListener("click", () => setCategory(""));

const today = setTodayDate();
loadHealth();
loadNews();
loadBriefing(today);
loadAnalytics();
loadSchedule();
window.setInterval(loadSchedule, 10000);
