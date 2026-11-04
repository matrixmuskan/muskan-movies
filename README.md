# Muskan

Weekly movie and show picks for one person. The page is a static site: dark, quiet, and poster-led. It is published with GitHub Pages from the `pages` workflow, the same Actions-based setup as [study-hub](https://github.com/matrixmuskan/study-hub).

Expected site: <https://matrixmuskan.github.io/muskan-movies/>

Preview locally from the repo root:

```bash
python3 -m http.server 8765
```

Then open <http://127.0.0.1:8765/>. Paths are relative, so the page works on a project site (`/muskan-movies/`) and on localhost.

There is no analytics, no font service, and no token in the page. Type is the system UI font.

## Turn on GitHub Pages

The workflow is in the repo. Pages still has to be switched on once, by the owner:

1. Merge this change to `main`.
2. On GitHub, open **Settings → Pages**.
3. Under **Build and deployment**, set **Source** to **GitHub Actions**.
4. If GitHub asks you to approve the `github-pages` environment, approve it.

The `pages` workflow then runs on every push to `main`. It publishes `index.html`, `assets/`, `data/picks.json`, `data/feedback.json`, and `.nojekyll`. The README, `tools/`, `.github/`, and `data/taste-profile.json` are not on the site.

The first push to `main` also runs the `feedback` workflow, which creates a GitHub label named `feedback` (neutral gray). That label is what the Keep / Discard / star links request. You can re-run the workflow with **Actions → feedback → Run workflow** if the label is missing.

If a feedback run cannot push, open **Settings → Actions → General → Workflow permissions** and allow Actions to read and write. This repo's personal default is usually enough, because the workflow itself asks for `contents: write`.

## Layout

The newest `week` in `data/picks.json` is **This Week**, even if today is not that Friday. Its first pick that is still open is the hero. Older weeks are rows under that, newest first. **Kept** is its own row. **History** is collapsed and holds discarded or rated titles.

Each card shows the poster, title, year, language, movie or series, IMDb rating, a one-line hook, where to watch, and a Kid-safe badge when `kid_safe` is true. The poster and **Play trailer** open `trailer_url`. On a wide screen, hover or keyboard focus reveals Keep, Discard, and the stars. On a narrow screen, **Details** reveals those actions so a scroll does not file an issue by accident.

## `data/picks.json`

The file is a JSON array. A bot appends the next Friday's objects to that array. Leave `data/feedback.json` and `data/taste-profile.json` alone when adding a week. One object per title:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | string | yes | Stable slug, unique. Pattern: `^[a-z0-9][a-z0-9-]{0,80}$`. Example: `udta-teer`. |
| `title` | string | yes | Display title. |
| `year` | number | yes | Release year. |
| `type` | string | yes | `movie` or `series`. |
| `language` | string | yes | The version being recommended, such as `Hindi` or `Tamil (Hindi dub available)`. |
| `imdb_rating` | number or null | yes | IMDb score. Use null when you do not have one. The site links it when `imdb_url` is set. |
| `imdb_id` | string | no | IMDb title id, such as `tt31806773`. |
| `imdb_url` | string | no | Public `https` IMDb title URL. |
| `hook` | string | yes | Short recommendation line. |
| `where_to_watch` | string | yes | Service or theater line, such as `SonyLIV`, `Prime Video`, or `In theaters: Cinemark Pacific Commons, Fremont`. |
| `trailer_url` | string | yes | Public `https` trailer. |
| `poster_url` | string | yes | Public `https` poster image. |
| `kid_safe` | boolean | yes | `true` shows a small Kid-safe badge. |
| `week` | string | yes | Friday of that week, `YYYY-MM-DD`. Every pick from the same drop shares one Friday. The greatest week is This Week. |
| `source` | string | yes | Who recommended it, and why. Stored for the bot. Not shown on the card. |
| `status` | string | yes | `new`, `kept`, `discarded`, or `seen`. A new drop uses `new`. |
| `example` | boolean | no | Optional. Current picks are real and do not set this. |

`status` in this file is the editorial starting point. A newer row in `data/feedback.json` for the same `id` overrides it. The site does not need the bot to edit `status` after the viewer acts.

`tools/validate.py` checks this shape on pull requests. A week that is not a Friday fails the check.

Append an object in that shape. The current file already holds real weeks. `2026-11-06` is This Week.

## `data/taste-profile.json`

The bot's preference model: weights, hard filters, and what Muskan has already seen. It stays in the repo so a later run can read it. The page does not fetch it, does not render it, and the Pages artifact does not include it.

## Feedback

The page has no backend. An action does three things:

1. It writes `{ id, action, rating, timestamp }` into `localStorage` under `muskan-movies-feedback`, and the card moves immediately.
2. It opens a prefilled new-issue URL on this repo. The title is `feedback: <id>`, the label is `feedback`, and the body contains a small JSON block.
3. On load, the page reads `data/feedback.json` and merges it with anything still only in `localStorage`. The newer timestamp wins.

Actions:

| Action | `rating` | Where the card goes |
| --- | --- | --- |
| `keep` | `null` | Kept |
| `discard` | `null` | History, marked Discarded |
| `rate` | integer 1–5 | History, marked Seen. A rating means you have seen it. |

A later action wins. Keep after a rating puts the title back in Kept and still shows the stars. Rating something you had kept moves it to History.

Issue body:

```json
{
  "id": "andhadhun-2018",
  "action": "keep",
  "rating": null,
  "timestamp": "2026-11-04T21:40:00.000Z"
}
```

The `feedback` workflow runs when an issue titled `feedback: ...` is opened. `tools/record_feedback.py` appends one object to `data/feedback.json` (adding the issue number), pushes that commit to `main`, closes the issue, and starts the Pages workflow so the new file is published. Filing the same issue twice does not duplicate the row.

Anyone who can open an issue on this repo can write feedback. For a single viewer, that is the GitHub account already signed in on the phone. Restrict who can open issues if this repo is public and that is too open.

`data/feedback.json` shape:

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Same slug as the pick. |
| `action` | string | `keep`, `discard`, or `rate`. |
| `rating` | number or null | `1`–`5` for `rate`, otherwise null. |
| `timestamp` | string | ISO-8601 time from the browser. |
| `issue` | number | GitHub issue that carried the action. |

The committed file starts as `{ "entries": [] }`.
