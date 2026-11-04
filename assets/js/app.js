(function () {
  "use strict";

  var REPO = "matrixmuskan/muskan-movies";
  var STORAGE_KEY = "muskan-movies-feedback";
  var WEEK_FORMAT = new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });

  var state = {
    picks: [],
    entries: [],
  };

  var app = document.getElementById("app");
  var notice = document.getElementById("notice");

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function safeHttps(url) {
    try {
      var parsed = new URL(url);
      if (parsed.protocol !== "https:") return "";
      return parsed.href;
    } catch (err) {
      return "";
    }
  }

  function readLocal() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      var parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed.filter(isEntry) : [];
    } catch (err) {
      return [];
    }
  }

  function writeLocal(entries) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  }

  function isEntry(entry) {
    return entry && typeof entry.id === "string" && typeof entry.action === "string" && typeof entry.timestamp === "string";
  }

  function mergeFeedback(remote, local) {
    var remoteKeys = {};
    remote.forEach(function (entry) {
      remoteKeys[entry.id + "|" + entry.timestamp] = true;
    });
    var pending = local.filter(function (entry) {
      return !remoteKeys[entry.id + "|" + entry.timestamp];
    });
    writeLocal(pending);
    return remote.concat(pending);
  }

  function latestById(entries) {
    var map = {};
    entries.forEach(function (entry) {
      var current = map[entry.id];
      if (!current || entry.timestamp >= current.timestamp) map[entry.id] = entry;
    });
    return map;
  }

  function ratingFor(entries, id) {
    var rating = null;
    var stamp = "";
    entries.forEach(function (entry) {
      if (entry.id !== id || entry.rating == null) return;
      if (entry.timestamp >= stamp) {
        rating = entry.rating;
        stamp = entry.timestamp;
      }
    });
    return rating;
  }

  function placement(pick, latest) {
    var action = latest ? latest.action : null;
    if (action === "keep" || (!latest && pick.status === "kept")) return "kept";
    if (action === "discard" || (!latest && pick.status === "discarded")) return "history";
    if (action === "rate" || (!latest && pick.status === "seen")) return "history";
    return "week";
  }

  function historyKind(pick, latest) {
    if (latest && latest.action === "discard") return "Discarded";
    if (latest && latest.action === "rate") return "Seen";
    if (!latest && pick.status === "discarded") return "Discarded";
    if (!latest && pick.status === "seen") return "Seen";
    return "";
  }

  function typeLabel(type) {
    return type === "series" ? "Series" : "Movie";
  }

  function formatWeek(iso) {
    return WEEK_FORMAT.format(new Date(iso + "T00:00:00Z"));
  }

  function formatRating(value) {
    if (typeof value !== "number") return "IMDb —";
    return "IMDb " + value.toFixed(1);
  }

  function ratingNode(pick) {
    var text = formatRating(pick.imdb_rating);
    var href = safeHttps(pick.imdb_url);
    if (!href) return document.createTextNode(text);
    var link = document.createElement("a");
    link.className = "imdb";
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = text;
    return link;
  }

  function metaWithRating(className, prefix, pick) {
    var line = el("p", className);
    line.appendChild(document.createTextNode(prefix));
    line.appendChild(ratingNode(pick));
    return line;
  }

  function starIcon() {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 20 20");
    svg.setAttribute("aria-hidden", "true");
    var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("fill", "currentColor");
    path.setAttribute("d", "M10 1.8l2.2 4.6 5 .7-3.6 3.5.9 5.1L10 13.3 5.5 15.7l.9-5.1L2.8 7.1l5-.7L10 1.8z");
    svg.appendChild(path);
    return svg;
  }

  function stars(pick, current) {
    var group = el("div", "stars");
    group.setAttribute("role", "group");
    group.setAttribute("aria-label", "Rate " + pick.title);
    for (var value = 1; value <= 5; value += 1) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "star";
      button.dataset.star = String(value);
      button.setAttribute("aria-label", "Rate " + value + (value === 1 ? " star" : " stars"));
      button.setAttribute("aria-pressed", current === value ? "true" : "false");
      button.appendChild(starIcon());
      group.appendChild(button);
    }
    return group;
  }

  function actionRow(pick, current) {
    var row = el("div", "card-actions");
    var keep = document.createElement("button");
    keep.type = "button";
    keep.className = "ghost";
    keep.dataset.action = "keep";
    keep.textContent = "Keep";
    var discard = document.createElement("button");
    discard.type = "button";
    discard.className = "ghost";
    discard.dataset.action = "discard";
    discard.textContent = "Discard";
    row.appendChild(keep);
    row.appendChild(discard);
    row.appendChild(stars(pick, current));
    return row;
  }

  function posterLink(pick, className) {
    var href = safeHttps(pick.trailer_url);
    var poster = href ? document.createElement("a") : el("div");
    poster.className = className;
    if (href) {
      poster.href = href;
      poster.target = "_blank";
      poster.rel = "noopener noreferrer";
      poster.setAttribute("aria-label", "Play trailer: " + pick.title);
    }
    var src = safeHttps(pick.poster_url);
    if (src) {
      var img = document.createElement("img");
      img.src = src;
      img.alt = "";
      img.addEventListener("error", function () {
        img.remove();
      });
      poster.appendChild(img);
    }
    return poster;
  }

  function playLink(pick) {
    var href = safeHttps(pick.trailer_url);
    if (!href) return null;
    var link = document.createElement("a");
    link.className = "play";
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    var icon = el("span", "play-icon");
    icon.setAttribute("aria-hidden", "true");
    link.appendChild(icon);
    link.appendChild(document.createTextNode("Play trailer"));
    return link;
  }

  function renderHero(pick) {
    var hero = el("section", "hero");
    hero.setAttribute("aria-label", "Top pick");
    if (!pick) {
      var empty = el("div", "hero-copy");
      empty.appendChild(el("p", "kicker", "This week"));
      empty.appendChild(el("h1", null, "Nothing queued"));
      empty.appendChild(el("p", "hero-hook", "Every pick this week has been kept, discarded, or rated."));
      hero.appendChild(empty);
      return hero;
    }

    var poster = posterLink(pick, "hero-poster");
    var image = poster.querySelector("img");
    if (image) image.setAttribute("fetchpriority", "high");
    hero.appendChild(poster);

    var copy = el("div", "hero-copy");
    copy.appendChild(el("p", "kicker", "Top pick · " + formatWeek(pick.week)));
    copy.appendChild(el("h1", null, pick.title));
    copy.appendChild(metaWithRating("hero-meta", [pick.year, pick.language, typeLabel(pick.type)].join(" · ") + " · ", pick));
    var heroHook = el("p", "hero-hook", pick.hook);
    copy.appendChild(heroHook);
    copy.appendChild(el("p", "hero-watch", pick.where_to_watch));
    if (pick.kid_safe) copy.appendChild(el("p", "badge", "Kid-safe"));

    var actions = el("div", "hero-actions");
    actions.dataset.id = pick.id;
    var play = playLink(pick);
    if (play) actions.appendChild(play);
    var keep = document.createElement("button");
    keep.type = "button";
    keep.className = "ghost";
    keep.dataset.action = "keep";
    keep.textContent = "Keep";
    var discard = document.createElement("button");
    discard.type = "button";
    discard.className = "ghost";
    discard.dataset.action = "discard";
    discard.textContent = "Discard";
    actions.appendChild(keep);
    actions.appendChild(discard);
    actions.appendChild(stars(pick, ratingFor(state.entries, pick.id)));
    copy.appendChild(actions);
    hero.appendChild(copy);
    return hero;
  }

  function renderCard(pick, kind) {
    var card = el("article", "card");
    card.dataset.id = pick.id;

    var wrap = el("div", "poster-wrap");
    var poster = posterLink(pick, "poster");
    var image = poster.querySelector("img");
    if (image) image.loading = "lazy";
    wrap.appendChild(poster);
    card.appendChild(wrap);

    var body = el("div", "card-body");
    body.appendChild(el("h3", null, pick.title));
    body.appendChild(el("p", "meta", pick.year + " · " + pick.language));
    body.appendChild(metaWithRating("meta", typeLabel(pick.type) + " · ", pick));
    var hook = el("p", "hook", pick.hook);
    hook.title = pick.hook;
    body.appendChild(hook);
    var watch = el("p", "watch", pick.where_to_watch);
    watch.title = pick.where_to_watch;
    body.appendChild(watch);
    if (pick.kid_safe) body.appendChild(el("p", "badge", "Kid-safe"));
    if (kind === "kept") body.appendChild(el("p", "placement", "Kept"));
    if (kind === "history") body.appendChild(el("p", "placement", historyKind(pick, latestById(state.entries)[pick.id])));

    var toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "details-toggle";
    toggle.textContent = "Details";
    toggle.setAttribute("aria-expanded", "false");
    body.appendChild(toggle);
    body.appendChild(actionRow(pick, ratingFor(state.entries, pick.id)));
    card.appendChild(body);
    return card;
  }

  function emptyCopy(kind) {
    if (kind === "kept") return "Nothing kept yet.";
    if (kind === "history") return "Nothing here yet.";
    return "Nothing left this week.";
  }

  function renderRow(picks, kind) {
    var row = el("div", "row");
    row.tabIndex = 0;
    if (!picks.length) {
      row.appendChild(el("p", "status-line", emptyCopy(kind)));
      return row;
    }
    picks.forEach(function (pick) {
      row.appendChild(renderCard(pick, kind));
    });
    return row;
  }

  function section(title, aside, picks, kind) {
    var block = el("section", "section");
    var head = el("div", "section-head");
    head.appendChild(el("h2", null, title));
    if (aside) head.appendChild(el("p", null, aside));
    block.appendChild(head);
    block.appendChild(renderRow(picks, kind));
    return block;
  }

  function render() {
    var scrollY = window.scrollY;
    var latest = latestById(state.entries);
    var active = [];
    var kept = [];
    var history = [];

    function byRecent(a, b) {
      var aStamp = (latest[a.id] && latest[a.id].timestamp) || "";
      var bStamp = (latest[b.id] && latest[b.id].timestamp) || "";
      return bStamp.localeCompare(aStamp);
    }

    state.picks.forEach(function (pick) {
      var where = placement(pick, latest[pick.id]);
      if (where === "kept") kept.push(pick);
      else if (where === "history") history.push(pick);
      else active.push(pick);
    });

    kept.sort(byRecent);
    history.sort(byRecent);

    var newest = state.picks.map(function (pick) { return pick.week; }).sort().pop() || "";
    var thisWeek = active.filter(function (pick) { return pick.week === newest; });
    var olderWeeks = active.map(function (pick) { return pick.week; }).filter(function (week, index, all) {
      return week !== newest && all.indexOf(week) === index;
    }).sort().reverse();

    app.replaceChildren();
    app.appendChild(renderHero(thisWeek[0] || null));

    var sections = el("div", "sections");
    sections.appendChild(section("This Week", newest ? formatWeek(newest) : "", thisWeek, "week"));
    olderWeeks.forEach(function (week) {
      var picks = active.filter(function (pick) { return pick.week === week; });
      sections.appendChild(section("Week of " + formatWeek(week), "", picks, "week"));
    });
    sections.appendChild(section("Kept", "", kept, "kept"));

    var historyBlock = el("details", "history");
    var summary = document.createElement("summary");
    var label = el("span", "label");
    label.appendChild(document.createTextNode("History"));
    summary.appendChild(label);
    summary.appendChild(el("span", "count", String(history.length)));
    historyBlock.appendChild(summary);
    historyBlock.appendChild(renderRow(history, "history"));
    sections.appendChild(historyBlock);

    app.appendChild(sections);
    window.scrollTo(0, scrollY);
  }

  function feedbackUrl(entry) {
    var payload = {
      id: entry.id,
      action: entry.action,
      rating: entry.rating,
      timestamp: entry.timestamp,
    };
    var body = "Feedback from the picks site.\n\n```json\n" + JSON.stringify(payload, null, 2) + "\n```\n";
    var url = new URL("https://github.com/" + REPO + "/issues/new");
    url.searchParams.set("title", "feedback: " + entry.id);
    url.searchParams.set("labels", "feedback");
    url.searchParams.set("body", body);
    return url.href;
  }

  function showNotice(pick, entry, url) {
    var verb = entry.action === "keep" ? "Kept" : entry.action === "discard" ? "Discarded" : "Rated";
    notice.hidden = false;
    notice.replaceChildren();
    notice.appendChild(document.createTextNode(verb + " " + pick.title + " on this phone. "));
    var link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Open the GitHub issue";
    notice.appendChild(link);
    notice.appendChild(document.createTextNode(" to save it in the repo."));
  }

  function apply(id, action, rating) {
    var pick = state.picks.find(function (item) { return item.id === id; });
    if (!pick) return;
    var entry = {
      id: id,
      action: action,
      rating: rating,
      timestamp: new Date().toISOString(),
    };
    var local = readLocal();
    local.push(entry);
    writeLocal(local);
    state.entries = mergeFeedback(state.entries.filter(function (item) {
      return item.issue != null;
    }), local);
    render();
    var url = feedbackUrl(entry);
    showNotice(pick, entry, url);
    var tab = window.open(url, "_blank");
    if (tab) tab.opener = null;
  }

  function onClick(event) {
    var star = event.target.closest("[data-star]");
    if (star) {
      var starHost = star.closest("[data-id]");
      if (starHost) apply(starHost.dataset.id, "rate", Number(star.dataset.star));
      return;
    }
    var action = event.target.closest("[data-action]");
    if (action) {
      var host = action.closest("[data-id]");
      if (host) apply(host.dataset.id, action.dataset.action, null);
      return;
    }
    var toggle = event.target.closest(".details-toggle");
    if (!toggle) return;
    var card = toggle.closest(".card");
    var open = !card.classList.contains("is-open");
    app.querySelectorAll(".card.is-open").forEach(function (node) {
      node.classList.remove("is-open");
      var button = node.querySelector(".details-toggle");
      if (button) {
        button.setAttribute("aria-expanded", "false");
        button.textContent = "Details";
      }
    });
    card.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.textContent = open ? "Hide" : "Details";
  }

  function load() {
    Promise.all([
      fetch("data/picks.json", { cache: "no-store" }).then(function (response) {
        if (!response.ok) throw new Error("picks");
        return response.json();
      }),
      fetch("data/feedback.json", { cache: "no-store" }).then(function (response) {
        if (!response.ok) throw new Error("feedback");
        return response.json();
      }),
    ]).then(function (results) {
      var picksDoc = results[0];
      state.picks = Array.isArray(picksDoc) ? picksDoc : (Array.isArray(picksDoc.picks) ? picksDoc.picks : []);
      var remote = Array.isArray(results[1].entries) ? results[1].entries.filter(isEntry) : [];
      state.entries = mergeFeedback(remote, readLocal());
      render();
    }).catch(function () {
      app.replaceChildren(el("p", "status-line", "Could not load picks."));
    });
  }

  app.addEventListener("click", onClick);
  load();
})();
