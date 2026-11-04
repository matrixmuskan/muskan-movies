# Muskan

Weekly movie and show picks for one person. The page is a static site: dark, quiet, and poster-led. It is published with GitHub Pages from the `pages` workflow, the same Actions-based setup as [study-hub](https://github.com/matrixmuskan/study-hub).

Expected site: <https://matrixmuskan.github.io/muskan-movies/>

Preview locally from the repo root:

```bash
python3 -m http.server 8765
```

Then open <http://127.0.0.1:8765/>. Paths are relative, so the page works on a project site (`/muskan-movies/`) and on localhost.

There is no analytics and no font service. Type is the system UI font. The copy of the site in git has a token placeholder; the published page receives the feedback token during the Pages build.

## Turn on GitHub Pages

The workflow is in the repo. Pages still has to be switched on once, by the owner:

1. Merge this change to `main`.
2. On GitHub, open **Settings → Pages**.
3. Under **Build and deployment**, set **Source** to **GitHub Actions**.
4. If GitHub asks you to approve the `github-pages` environment, approve it.

The `pages` workflow then runs on every push to `main`. It publishes `index.html`, `assets/`, `data/picks.json`, and `.nojekyll`. During that job it replaces the placeholder in `assets/js/config.js` with the Actions secret `MOVIES_FEEDBACK_TOKEN`. The README, `tools/`, `.github/`, and `data/taste-profile.json` are not on the site. The token is not stored in git.

## Layout

The newest `week` in `data/picks.json` is **This Week**, even if today is not that Friday. Its first pick that is still open is the hero. Older weeks are rows under that, newest first. **Kept** is its own row. **History** is collapsed and holds discarded or rated titles.

Each card shows the poster, title, year, language, a small Movie or Series label from `type`, IMDb rating, a one-line hook, where to watch, and a Kid-safe badge when `kid_safe` is true. The poster and **Play trailer** open a YouTube trailer in the page when `trailer_url` is a YouTube link. Any other trailer link opens in a new tab. On a wide screen, hover or keyboard focus reveals Keep, Discard, and the stars. On a narrow screen, **Details** reveals those actions.

## Lock

A password field is the first thing on the page. The script published with the site contains a SHA-256 hash of the password, not the password. After a correct entry, that browser stores the hash in `localStorage` under `muskan-movies-unlock` and does not ask again on that device. `data/picks.json` stays a normal file so a weekly build can read and update it. This is a screen in front of the layout, not a lock on the file: the picks file is still reachable at its public URL.

## `data/picks.json`

The file is a JSON array. A bot appends the next Friday's objects to that array. Leave `data/taste-profile.json` alone when adding a week. Viewer feedback is not in this repo. One object per title:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | string | yes | Stable slug, unique. Pattern: `^[a-z0-9][a-z0-9-]{0,80}$`. Example: `udta-teer`. |
| `title` | string | yes | Display title. |
| `year` | number | yes | Release year. |
| `type` | string | yes | `movie` or `series`. The tile label is Movie or Series. A weekly build must set this; the site does not guess. |
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

`status` in this file is the editorial starting point. A newer feedback file for the same `id` overrides it. The site does not need the bot to edit `status` after the viewer acts.

`tools/validate.py` checks this shape on pull requests. A week that is not a Friday fails the check.

Append an object in that shape. The current file already holds real weeks. `2026-11-06` is This Week.

## `data/taste-profile.json`

The bot's preference model: weights, hard filters, and what Muskan has already seen. It stays in the repo so a later run can read it. The page does not fetch it, does not render it, and the Pages artifact does not include it.

## Feedback

Keep, Discard, and a star are one tap. The card moves immediately and the page stays put. Nothing opens a GitHub issue.

Each tap writes one file to the private repo `matrixmuskan/muskan-movies-feedback`:

`feedback/<year>/<timestamp>-<id>.json`

The timestamp in the file name is the ISO time with `:` replaced by `-`, so a keep on Udta Teer looks like `feedback/2026/2026-11-04T22-15-01.123Z-udta-teer.json`. One file per tap, so two taps never edit the same path.

```json
{
  "id": "udta-teer",
  "action": "keep",
  "rating": null,
  "timestamp": "2026-11-04T22:15:01.123Z"
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Same slug as the pick. |
| `action` | string | `keep`, `discard`, or `rate`. |
| `rating` | number or null | `1`–`5` for `rate`, otherwise null. |
| `timestamp` | string | ISO-8601 time from the browser. |

On load the site lists `feedback/` and reads those files, using the same token. The newest timestamp for an id wins, on the phone and on a laptop. `localStorage` keys `muskan-movies-feedback` (last remote snapshot) and `muskan-movies-feedback-queue` (taps not yet confirmed) update the page before the network returns. A failed write stays in the queue and is retried.

| Action | `rating` | Where the card goes |
| --- | --- | --- |
| `keep` | `null` | Kept |
| `discard` | `null` | History, marked Discarded |
| `rate` | integer 1–5 | History, marked Seen. A rating means you have seen it. |

A later file wins. Keep after a rating puts the title back in Kept and still shows the stars. Rating something that was kept moves it to History.

The write uses the GitHub Contents API and the Actions secret `MOVIES_FEEDBACK_TOKEN`. That secret is a fine-grained token with Contents read and write on `matrixmuskan/muskan-movies-feedback` only. The Pages workflow injects it into the built `config.js`. Do not commit a token, and do not print it in a workflow log. A bot that wants the viewer's taps should read `muskan-movies-feedback/feedback/`, not this repo.
