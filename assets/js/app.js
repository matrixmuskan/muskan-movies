(function () {
  "use strict";

  var CACHE_KEY = "muskan-movies-feedback";
  var QUEUE_KEY = "muskan-movies-feedback-queue";
  var TOKEN_PLACEHOLDER = "__MOVIES_FEEDBACK_TOKEN__";
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
  var flushBusy = false;
  var flushAgain = false;
  var trailerReturn = null;
  var sheetReturn = null;
  var TOUCH_LAYOUT = window.matchMedia("(max-width: 799px), (hover: none)");
  var UNLOCK_KEY = "muskan-movies-unlock";

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

  function isEntry(entry) {
    return entry && typeof entry.id === "string" && typeof entry.action === "string" && typeof entry.timestamp === "string";
  }

  function readList(key) {
    try {
      var parsed = JSON.parse(localStorage.getItem(key) || "[]");
      return Array.isArray(parsed) ? parsed.filter(isEntry) : [];
    } catch (err) {
      return [];
    }
  }

  function writeList(key, entries) {
    localStorage.setItem(key, JSON.stringify(entries));
  }

  function entryKey(entry) {
    return entry.id + "|" + entry.timestamp;
  }

  function uniqueEntries(entries) {
    var seen = {};
    return entries.filter(function (entry) {
      var key = entryKey(entry);
      if (seen[key]) return false;
      seen[key] = true;
      return true;
    });
  }

  // Confirmed taps (cache) plus taps still waiting for a 201 (queue, marked pending).
  function knownEntries() {
    var pending = readList(QUEUE_KEY).map(function (entry) {
      var copy = Object.assign({}, entry);
      copy.pending = true;
      return copy;
    });
    return uniqueEntries(pending.concat(readList(CACHE_KEY)));
  }

  function feedbackCfg() {
    var cfg = window.MOVIES_FEEDBACK || {};
    var token = typeof cfg.token === "string" ? cfg.token : "";
    if (!token || token === TOKEN_PLACEHOLDER) return null;
    return {
      repo: cfg.repo || "matrixmuskan/muskan-movies-feedback",
      token: token,
    };
  }

  function apiUrl(path) {
    var cfg = feedbackCfg();
    return "https://api.github.com/repos/" + cfg.repo + "/contents/" + path.split("/").map(encodeURIComponent).join("/");
  }

  function apiHeaders() {
    return {
      Authorization: "Bearer " + feedbackCfg().token,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "Content-Type": "application/json",
    };
  }

  function b64(str) {
    var bytes = new TextEncoder().encode(str);
    var binary = "";
    var size = 0x8000;
    for (var index = 0; index < bytes.length; index += size) {
      binary += String.fromCharCode.apply(null, bytes.subarray(index, index + size));
    }
    return btoa(binary);
  }

  function decodeContent(content) {
    var binary = atob(String(content).replace(/\n/g, ""));
    var bytes = new Uint8Array(binary.length);
    for (var index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    return new TextDecoder().decode(bytes);
  }

  function pathFor(entry) {
    return "feedback/" + entry.timestamp.slice(0, 4) + "/" + entry.timestamp.replace(/:/g, "-") + "-" + entry.id + ".json";
  }

  function putEntry(item) {
    if (!feedbackCfg()) return Promise.resolve(0);
    var body = {
      id: item.id,
      action: item.action,
      rating: item.rating == null ? null : item.rating,
      timestamp: item.timestamp,
    };
    return fetch(apiUrl(item.path), {
      method: "PUT",
      headers: apiHeaders(),
      body: JSON.stringify({
        message: "feedback " + item.id + " " + item.action,
        content: b64(JSON.stringify(body, null, 2) + "\n"),
        branch: "main",
      }),
    }).then(function (response) {
      return response.status;
    }, function () {
      return 0;
    });
  }

  function confirm(item) {
    var saved = {
      id: item.id,
      action: item.action,
      rating: item.rating == null ? null : item.rating,
      timestamp: item.timestamp,
      confirmed: Date.now(),
    };
    writeList(CACHE_KEY, uniqueEntries(readList(CACHE_KEY).concat([saved])));
    writeList(QUEUE_KEY, readList(QUEUE_KEY).filter(function (entry) {
      return entryKey(entry) !== entryKey(item);
    }));
    state.entries = knownEntries();
  }

  function flush() {
    if (flushBusy) {
      flushAgain = true;
      return;
    }
    if (!feedbackCfg()) return;
    flushBusy = true;
    var queue = readList(QUEUE_KEY);
    var index = 0;

    function next() {
      if (index >= queue.length) {
        flushBusy = false;
        if (flushAgain) {
          flushAgain = false;
          flush();
        }
        return;
      }
      var item = queue[index];
      index += 1;
      putEntry(item).then(function (status) {
        if (status === 201 || status === 200 || status === 422) {
          confirm(item);
          next();
          return;
        }
        flushBusy = false;
        if (status === 0 || status === 401 || status === 403 || status === 429 || status >= 500) {
          window.setTimeout(flush, 4000);
        }
      });
    }

    next();
  }

  function listDir(path) {
    return fetch(apiUrl(path), { headers: apiHeaders(), cache: "no-store" }).then(function (response) {
      if (response.status === 404) return [];
      if (!response.ok) throw new Error(String(response.status));
      return response.json();
    }).then(function (data) {
      return Array.isArray(data) ? data : [];
    });
  }

  function readRemoteFile(path) {
    return fetch(apiUrl(path), { headers: apiHeaders(), cache: "no-store" }).then(function (response) {
      if (!response.ok) throw new Error(String(response.status));
      return response.json();
    }).then(function (doc) {
      if (!doc || typeof doc.content !== "string") return null;
      var parsed = JSON.parse(decodeContent(doc.content));
      return isEntry(parsed) ? parsed : null;
    });
  }

  function loadRemote() {
    if (!feedbackCfg()) return Promise.resolve(null);
    return listDir("feedback").then(function (years) {
      var dirs = years.filter(function (item) {
        return item && item.type === "dir" && /^\d{4}$/.test(item.name);
      });
      return Promise.all(dirs.map(function (dir) {
        return listDir(dir.path);
      }));
    }).then(function (groups) {
      var files = [];
      groups.forEach(function (items) {
        items.forEach(function (item) {
          if (item && item.type === "file" && /\.json$/.test(item.name)) files.push(item.path);
        });
      });
      return Promise.all(files.map(function (path) {
        return readRemoteFile(path).catch(function () { return null; });
      }));
    }).then(function (entries) {
      return entries.filter(Boolean);
    });
  }

  // The contents listing can lag a fresh write, so a tap confirmed on this device
  // survives a listing that does not show it yet. After the grace period the server is the record.
  var LISTING_GRACE_MS = 15 * 60 * 1000;

  function reconcile(remote) {
    var onServer = {};
    remote.forEach(function (entry) {
      onServer[entryKey(entry)] = true;
    });
    var now = Date.now();
    var recent = readList(CACHE_KEY).filter(function (entry) {
      return !onServer[entryKey(entry)] && typeof entry.confirmed === "number" && now - entry.confirmed < LISTING_GRACE_MS;
    });
    writeList(CACHE_KEY, uniqueEntries(remote.concat(recent)));
    writeList(QUEUE_KEY, readList(QUEUE_KEY).filter(function (entry) {
      return !onServer[entryKey(entry)];
    }));
    state.entries = knownEntries();
  }

  // Latest action per title wins. A pending local tap beats every server entry until it is confirmed.
  function latestById(entries) {
    var map = {};
    entries.forEach(function (entry) {
      var current = map[entry.id];
      if (!current) {
        map[entry.id] = entry;
        return;
      }
      if (entry.pending && !current.pending) {
        map[entry.id] = entry;
        return;
      }
      if (current.pending && !entry.pending) return;
      if (entry.timestamp >= current.timestamp) map[entry.id] = entry;
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
    if (pick.status === "removed") return "history";
    var action = latest ? latest.action : null;
    if (action === "keep" || (!latest && pick.status === "kept")) return "kept";
    if (action === "discard" || (!latest && pick.status === "discarded")) return "history";
    if (action === "rate" || (!latest && pick.status === "seen")) return "history";
    return "week";
  }

  function historyKind(pick, latest) {
    if (pick.status === "removed") return "Removed";
    if (latest && latest.action === "discard") return "Discarded";
    if (latest && latest.action === "rate") return "Seen";
    if (!latest && pick.status === "discarded") return "Discarded";
    if (!latest && pick.status === "seen") return "Seen";
    return "";
  }

  function typeLabel(type) {
    return type === "series" ? "Series" : "Movie";
  }

  function trailerNote(pick) {
    var lang = typeof pick.trailer_lang === "string" ? pick.trailer_lang.trim() : "";
    if (!lang || lang.toLowerCase() === "hindi") return null;
    return el("p", "trailer-lang", "Trailer: " + lang);
  }

  function endorsementLine(pick, className) {
    var list = Array.isArray(pick.endorsements) ? pick.endorsements.filter(function (item) {
      return item && typeof item.name === "string" && item.name.trim() && safeHttps(item.url);
    }) : [];
    if (!list.length) return null;
    var line = el("p", className);
    line.appendChild(document.createTextNode("Recommended by "));
    list.forEach(function (item, index) {
      if (index) line.appendChild(document.createTextNode(", "));
      var link = document.createElement("a");
      link.href = safeHttps(item.url);
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = item.name.trim();
      line.appendChild(link);
    });
    return line;
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

  function posterControl(pick, className) {
    var href = safeHttps(pick.trailer_url);
    var poster = href ? document.createElement("button") : el("div");
    poster.className = className;
    if (href) {
      poster.type = "button";
      poster.dataset.trailer = pick.id;
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

  function playControl(pick) {
    if (!safeHttps(pick.trailer_url)) return null;
    var button = document.createElement("button");
    button.type = "button";
    button.className = "play";
    button.dataset.trailer = pick.id;
    var icon = el("span", "play-icon");
    icon.setAttribute("aria-hidden", "true");
    button.appendChild(icon);
    button.appendChild(document.createTextNode("Play trailer"));
    return button;
  }

  function youtubeId(url) {
    try {
      var parsed = new URL(url);
      var host = parsed.hostname.replace(/^www\./, "").replace(/^m\./, "");
      var id = "";
      if (host === "youtu.be") id = parsed.pathname.split("/").filter(Boolean)[0] || "";
      else if (host === "youtube.com" || host === "youtube-nocookie.com") {
        if (parsed.pathname === "/watch") id = parsed.searchParams.get("v") || "";
        else {
          var parts = parsed.pathname.split("/");
          var slot = ["embed", "shorts", "v"].map(function (name) { return parts.indexOf(name); }).find(function (index) { return index >= 0; });
          if (slot >= 0) id = parts[slot + 1] || "";
        }
      }
      return /^[A-Za-z0-9_-]{11}$/.test(id) ? id : "";
    } catch (err) {
      return "";
    }
  }

  function closeTrailer() {
    var dialog = document.getElementById("trailer");
    if (!dialog || dialog.hidden) return;
    dialog.hidden = true;
    document.getElementById("trailer-frame").src = "";
    document.body.classList.remove("trailer-open");
    if (trailerReturn && trailerReturn.focus) trailerReturn.focus();
    trailerReturn = null;
  }

  function openTrailer(pick, source) {
    var href = safeHttps(pick.trailer_url);
    if (!href) return;
    var id = youtubeId(href);
    if (!id) {
      var tab = window.open(href, "_blank", "noopener");
      if (tab) tab.opener = null;
      return;
    }
    var dialog = document.getElementById("trailer");
    var frame = document.getElementById("trailer-frame");
    document.getElementById("trailer-title").textContent = pick.title;
    frame.title = "Trailer: " + pick.title;
    frame.src = "https://www.youtube-nocookie.com/embed/" + id + "?autoplay=1&rel=0&playsinline=1";
    trailerReturn = source || null;
    dialog.hidden = false;
    document.body.classList.add("trailer-open");
    document.getElementById("trailer-close").focus();
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

    var poster = posterControl(pick, "hero-poster");
    var image = poster.querySelector("img");
    if (image) image.setAttribute("fetchpriority", "high");
    var frame = el("div", "poster-wrap");
    frame.appendChild(poster);
    frame.appendChild(el("span", "type-tag", typeLabel(pick.type)));
    hero.appendChild(frame);

    var copy = el("div", "hero-copy");
    var head = el("div", "hero-head");
    head.appendChild(el("p", "kicker", "Top pick · " + formatWeek(pick.week)));
    head.appendChild(el("h1", null, pick.title));
    head.appendChild(metaWithRating("hero-meta", [pick.year, pick.language, typeLabel(pick.type)].join(" · ") + " · ", pick));
    copy.appendChild(head);
    var heroHook = el("p", "hero-hook", pick.hook);
    copy.appendChild(heroHook);
    copy.appendChild(el("p", "hero-watch", pick.where_to_watch));
    var heroEndorsed = endorsementLine(pick, "endorsed hero-endorsed");
    if (heroEndorsed) copy.appendChild(heroEndorsed);
    var heroTrailer = trailerNote(pick);
    if (heroTrailer) copy.appendChild(heroTrailer);
    if (pick.kid_safe) copy.appendChild(el("p", "badge", "Kid-safe"));

    var actions = el("div", "hero-actions");
    actions.dataset.id = pick.id;
    var play = playControl(pick);
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
    var poster = posterControl(pick, "poster");
    var image = poster.querySelector("img");
    if (image) image.loading = "lazy";
    wrap.appendChild(poster);
    wrap.appendChild(el("span", "type-tag", typeLabel(pick.type)));
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
    var endorsed = endorsementLine(pick, "endorsed");
    if (endorsed) body.appendChild(endorsed);
    var note = trailerNote(pick);
    if (note) body.appendChild(note);
    if (pick.kid_safe) body.appendChild(el("p", "badge", "Kid-safe"));
    if (kind === "kept") body.appendChild(el("p", "placement", "Kept"));
    if (kind === "history") body.appendChild(el("p", "placement", historyKind(pick, latestById(state.entries)[pick.id])));
    if (kind === "history" && pick.status === "removed" && pick.removed_reason) {
      body.appendChild(el("p", "removed-reason", pick.removed_reason));
    }

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

  function apply(id, action, rating) {
    var pick = state.picks.find(function (item) { return item.id === id; });
    if (!pick) return;
    if (action !== "keep" && action !== "discard" && action !== "rate") return;
    if (action === "rate" && !(rating >= 1 && rating <= 5)) return;
    var entry = {
      id: id,
      action: action,
      rating: action === "rate" ? rating : null,
      timestamp: new Date().toISOString(),
    };
    entry.path = pathFor(entry);
    var queue = readList(QUEUE_KEY);
    queue.push(entry);
    writeList(QUEUE_KEY, queue);
    state.entries = knownEntries();
    render();
    flush();
  }

  function pickById(id) {
    return state.picks.find(function (item) { return item.id === id; });
  }

  function closeSheet() {
    var sheet = document.getElementById("sheet");
    if (!sheet || sheet.hidden) return;
    sheet.hidden = true;
    document.getElementById("sheet-body").replaceChildren();
    document.body.classList.remove("sheet-open");
    if (sheetReturn && sheetReturn.isConnected && sheetReturn.focus) sheetReturn.focus();
    sheetReturn = null;
  }

  function openSheet(pick, source) {
    var body = document.getElementById("sheet-body");
    body.replaceChildren();
    var heading = el("h2", null, pick.title);
    heading.id = "sheet-title";
    body.appendChild(heading);
    body.appendChild(metaWithRating("sheet-meta", [pick.year, pick.language, typeLabel(pick.type)].join(" · ") + " · ", pick));
    body.appendChild(el("p", "sheet-hook", pick.hook));
    body.appendChild(el("p", "sheet-watch", pick.where_to_watch));
    var endorsed = endorsementLine(pick, "endorsed sheet-endorsed");
    if (endorsed) body.appendChild(endorsed);
    var note = trailerNote(pick);
    if (note) body.appendChild(note);
    if (pick.kid_safe) body.appendChild(el("p", "badge", "Kid-safe"));
    if (pick.status === "removed" && pick.removed_reason) body.appendChild(el("p", "removed-reason", pick.removed_reason));
    var actions = el("div", "sheet-actions");
    actions.dataset.id = pick.id;
    var play = playControl(pick);
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
    body.appendChild(actions);
    sheetReturn = source || null;
    document.getElementById("sheet").hidden = false;
    document.body.classList.add("sheet-open");
    document.getElementById("sheet-close").focus();
  }

  function onClick(event) {
    var trailer = event.target.closest("[data-trailer]");
    if (trailer) {
      var trailerPick = pickById(trailer.dataset.trailer);
      var fromSheet = !!trailer.closest("#sheet");
      if (fromSheet) closeSheet();
      if (trailerPick) openTrailer(trailerPick, fromSheet ? null : trailer);
      return;
    }
    var star = event.target.closest("[data-star]");
    if (star) {
      var starHost = star.closest("[data-id]");
      if (starHost) apply(starHost.dataset.id, "rate", Number(star.dataset.star));
      closeSheet();
      return;
    }
    var action = event.target.closest("[data-action]");
    if (action) {
      var host = action.closest("[data-id]");
      if (host) apply(host.dataset.id, action.dataset.action, null);
      closeSheet();
      return;
    }
    if (event.target.closest("a, #sheet")) return;
    var toggle = event.target.closest(".details-toggle") || (TOUCH_LAYOUT.matches && event.target.closest(".card-body"));
    if (!toggle) return;
    var card = toggle.closest(".card");
    var pick = card && pickById(card.dataset.id);
    if (pick) openSheet(pick, card.querySelector(".details-toggle"));
  }

  function load() {
    fetch("data/picks.json", { cache: "no-store" }).then(function (response) {
      if (!response.ok) throw new Error("picks");
      return response.json();
    }).then(function (picksDoc) {
      state.picks = Array.isArray(picksDoc) ? picksDoc : (Array.isArray(picksDoc.picks) ? picksDoc.picks : []);
      state.entries = knownEntries();
      render();
      flush();
      loadRemote().then(function (remote) {
        if (!remote) return;
        reconcile(remote);
        render();
      }).catch(function () {});
    }).catch(function () {
      app.replaceChildren(el("p", "status-line", "Could not load picks."));
    });
  }

  function passwordHash() {
    var cfg = window.MOVIES_FEEDBACK || {};
    return typeof cfg.passwordHash === "string" ? cfg.passwordHash : "";
  }

  function sha256Hex(text) {
    return crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)).then(function (buffer) {
      return Array.from(new Uint8Array(buffer)).map(function (byte) {
        return (byte < 16 ? "0" : "") + byte.toString(16);
      }).join("");
    });
  }

  function isUnlocked() {
    try {
      return passwordHash().length === 64 && localStorage.getItem(UNLOCK_KEY) === passwordHash();
    } catch (err) {
      return false;
    }
  }

  function showSite() {
    document.getElementById("gate").hidden = true;
    document.getElementById("site").hidden = false;
    load();
  }

  function bindGate() {
    var form = document.getElementById("gate-form");
    var input = document.getElementById("gate-password");
    var error = document.getElementById("gate-error");
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      sha256Hex(input.value).then(function (hex) {
        if (hex === passwordHash()) {
          try { localStorage.setItem(UNLOCK_KEY, passwordHash()); } catch (err) {}
          input.value = "";
          error.hidden = true;
          showSite();
          return;
        }
        error.hidden = false;
        input.select();
      }).catch(function () {
        error.hidden = false;
      });
    });
  }

  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-close-trailer]")) closeTrailer();
    if (event.target.closest("[data-close-sheet]")) closeSheet();
  });
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    if (!document.getElementById("trailer").hidden) closeTrailer();
    else closeSheet();
  });
  window.addEventListener("online", flush);
  app.addEventListener("click", onClick);
  document.getElementById("sheet").addEventListener("click", onClick);
  if (isUnlocked()) showSite();
  else bindGate();
})();
