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

The newest `week` in `data/picks.json` is **This Week**, even if today is not that Friday. Its first pick that is still open is the hero. Older weeks are rows under that, newest first. **Kept** is its own row. **History** is collapsed and holds discarded or rated titles, plus any pick whose `status` is `removed`, with its `removed_reason` in small text.

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
| `trailer_url` | string | yes | Public `https` trailer. For a Tamil, Telugu, Malayalam, or Kannada title, use the official Hindi-dubbed YouTube trailer when one exists (check that it plays in the site's player). |
| `trailer_lang` | string | no | Audio language of the trailer, such as `Hindi` or `Tamil`. Set it when a South Indian title has no Hindi trailer and the original stays. Any value other than `Hindi` shows a small `Trailer: Tamil` note on the tile. |
| `poster_url` | string | yes | Public `https` poster image. |
| `kid_safe` | boolean | yes | `true` shows a small Kid-safe badge. |
| `week` | string | yes | Friday of that week, `YYYY-MM-DD`. Every pick from the same drop shares one Friday. The greatest week is This Week. |
| `source` | string | yes | Who recommended it, and why. Stored for the bot. Not shown on the card. |
| `endorsements` | array | yes | Reviewers and influencers who recommended the title: `[{ "name": "Rahul Desai", "url": "https://x.com/..." }]`. Each `url` must go to that person's own video, post, or review of this title, and must be opened and checked before it is added. Never guess a link. Use `[]` when none is verified; the site then hides the line. Shown as "Recommended by" on the tile and in the hero. |
| `status` | string | yes | `new`, `kept`, `discarded`, `seen`, or `removed`. A new drop uses `new`. `removed` takes a pick out of every row for good, even if feedback says otherwise, and shows it in History. |
| `removed_reason` | string | with `removed` | Short reason, shown in small text in History. Required when `status` is `removed`; not allowed otherwise. |
| `example` | boolean | no | Optional. Current picks are real and do not set this. |

`status` in this file is the editorial starting point. A newer feedback file for the same `id` overrides it. The site does not need the bot to edit `status` after the viewer acts.

`tools/validate.py` checks this shape on every push. A week that is not a Friday fails the check.

### Curation rules for weekly builds

- **South Indian titles.** For Tamil, Telugu, Malayalam, or Kannada picks, prefer the official Hindi-dubbed YouTube trailer (usually from the streamer or studio channel). If none exists, keep the original and set `trailer_lang`.
- **No cartoons.** Skip animated films and cartoons unless the title is a huge, acclaimed blockbuster on the level of Inside Out. If one gets in, set `status` to `removed` and give a `removed_reason`; do not delete the object.
- **Endorsements.** Fill `endorsements` from the reviewers in `data/taste-profile.json` (`reviewer_trust_weights`) and the web. Only favourable takes count. Each link is checked by hand or by fetching it.

Append an object in that shape. The current file already holds real weeks. `2026-11-06` is This Week.

## `data/taste-profile.json`

The bot's preference model: weights, hard filters, and what Muskan has already seen. It stays in the repo so a later run can read it. The page does not fetch it, does not render it, and the Pages artifact does not include it.

## `data/ratings-log.json`

The learning file for the weekly build. It sorts each title the viewer acted on into one of three lists, using the newest feedback file for that title in `muskan-movies-feedback/feedback/`. The site does not fetch or render it, and Pages does not publish it.

```json
{
  "version": 1,
  "updated": "2026-11-04",
  "source": "matrixmuskan/muskan-movies-feedback/feedback/",
  "rules": { "loved": "4-5 stars or keep", "neutral": "3 stars", "disliked": "1-2 stars or discard" },
  "loved": [],
  "neutral": [],
  "disliked": []
}
```

One entry per title:

| Field | Type | Meaning |
| --- | --- | --- |
| `title` | string | Display title. |
| `id` | string | Pick id. |
| `type` | string | `movie` or `series`. |
| `language` | string | Same as the pick. |
| `genres` | array of strings | Genres and themes, using `genre_weights` and `theme_weights` names from the taste profile where they fit. |
| `action` | string | `keep`, `discard`, or `rate`. |
| `stars` | number or null | `1`–`5` for `rate`, otherwise null. |
| `date` | string | ISO timestamp of the newest feedback file for the title. |
| `endorsers` | array of strings | Names from the pick's `endorsements`. |
| `lesson` | string | One sentence the next build should act on. |

Which list: keep or 4–5 stars goes in `loved`; 3 stars in `neutral`; discard or 1–2 stars in `disliked`. When the viewer acts again, move the entry and update it. Do not keep two entries for one id. `tools/validate.py` checks the fields and the list each entry is in.

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

## Sources, voting, and source trust

The weekly build learns which reviewers and channels fit Muskan's taste. None of this is on the site: the Pages job copies only `index.html`, `assets/`, and `data/picks.json`.

| File | What it holds |
| --- | --- |
| `data/sources.json` | Every vetted source. Each has a stable `id` (slug), `flavor` (`critic`, `hindi-youtube`, `south`, `hidden-gems`, `listicle`, `ott-charts`, `mainstream-calendar`), `kind` (`critic`, `curator/listicle`, `chart`, `release-calendar`), `status` (`established` = on file before 2026-11-04, `new` = from Muskan's 2026-11-04 list), `aliases` (names used in `endorsements`), and per-platform `accounts` (YouTube channel id + RSS feed, X user id, Instagram marked manual only). |
| `data/source-scores.json` | The learning state, written by `tools/score_sources.py`: one Beta(alpha, beta) per source and per flavor with tallies, the per-pick log, and endorser names that map to no source yet. |
| `tools/score_sources.py` | The helper. `tools/test_score_sources.py` is its test suite. |

### How a title is scored

1. **Hard rules first.** IMDb 6.0+ (no rating yet = not eligible), no heavy horror, no animation unless it is Inside Out-level, nothing already seen. At most 1 of 5 is Hollywood.
2. **Platform mix (50-50 rule).** Muskan already browses Netflix and Prime Video on his TV, so the picks lean toward hidden gems elsewhere. At least 3 of the 5 weekly picks (`MIN_NON_NETFLIX_PRIME = 3`) must be **off** Netflix and Prime Video. Theater releases, JioHotstar, Hulu, SonyLIV, ZEE5, Aha, Sun NXT, MX Player, Apple TV+, Lionsgate Play, Hoichoi, Chaupal, ShemarooMe, TVF Play, YouTube, and the like count as off. A title that is showing in a local theater this week counts as off, even if it is also on Prime (`where_to_watch` says "In theaters", or the candidate has `in_local_theater: true`). When the running Netflix/Prime share across active picks in `data/picks.json` (removed picks excluded) is above 50% (`NETFLIX_PRIME_SHARE_CAP`), the minimum rises to 4 of 5. Exactly 50% is not above, so it stays at 3. If the top picks miss the minimum, the weakest `exploit` pick on Netflix/Prime is swapped for the best unused off-Netflix/Prime title that passes the hard rules and the Hollywood cap. The rule is only a floor: an all-off week is fine. Each ranked pick reports `on_netflix_prime`. On 2026-11-04 the share was 14 of 20 active picks (70%), so five Netflix/Prime picks with no feedback were marked `removed` (`removed_reason: "rebalanced: 50-50 platform rule"`) and three off-platform picks were added to the 2026-11-06 week. The share is now 9 of 18 (50%), so the next week needs 3 off.
3. **Votes.** Each source that recommends the title adds `kind_weight × trust`. The kind weights are critic 1.0, curator/listicle 0.8, chart 0.2, and release-calendar 0, so a release calendar tells us a title exists but gives it no taste vote. Inside one flavor the votes shrink (1, ½, ¼ …). Each extra distinct flavor adds +0.10, so three different flavors agreeing beat three critics from the same bubble. The total is squashed to 0–1 with `1 − e^(−x)`.
4. **Score** = 0.45 × votes + 0.35 × taste match (language weight plus the top genre, theme, and producer weights from `taste-profile.json`) + 0.20 × IMDb (6 → 0, 9+ → 1).

### Trust as a bandit

* Every source starts at Beta(2, 2), a mean trust of 0.50. New sources get the same prior.
* When Muskan acts on a pick, every source in its `sources` is updated. Keep or 4–5 stars counts as a success (alpha + 1), Discard or 1–2 stars as a failure (beta + 1), and 3 stars as half of each. Only the newest feedback file per pick counts, which matches the site.
* The state is rebuilt from the prior on every run by replaying `picks.json` against the feedback files, so running it twice never counts a tap twice.
* **Explore vs exploit.** Of the 5 weekly picks, the `exploit` picks are the top scores using mean trust. The `explore` picks are the top scores using a Thompson sample of each source's Beta, taken from titles backed by a `new` source, a source with fewer than 3 rated picks, or a flavor with fewer than 3 rated picks. That gives 2 explore and 3 exploit while most sources are untested, and 1 and 4 after that. The random seed is the week, so a rerun gives the same list.

### Fields the build adds to `data/picks.json`

| Field | Meaning |
| --- | --- |
| `slot` | `exploit` or `explore`. The 22 picks made before 2026-11-04 are `exploit`, because nothing was explored on purpose then. |
| `sources` | Source ids that surfaced the pick. Back-filled from `endorsements` by name or outlet, so "Anuj Kumar (The Hindu)" maps to `the-hindu-reviews`. Endorsers with no source, such as Filmfare or Times of India critics, are counted in `unmapped_endorsers`. |

`tools/validate.py` accepts both fields. The site ignores them.

### Weekly commands

```bash
# 1. read the feedback repo, back-fill new picks, rebuild trust, print the source report
python3 tools/score_sources.py weekly
# 2. rank this week's candidates into 5 picks and log their votes
python3 tools/score_sources.py rank --candidates candidates.json --week 2026-11-13 --record --out shortlist.json
# 3. after the 5 picks (with slot + sources) are appended to data/picks.json
python3 tools/score_sources.py update
python3 tools/test_score_sources.py
```

`fetch` and `weekly` read `matrixmuskan/muskan-movies-feedback`. They use `$MOVIES_FEEDBACK_TOKEN` when it is set and the logged-in `gh` otherwise. The token is never printed, and the downloaded files go to `tools/feedback_dump/`, which git ignores.

A candidate is a JSON object with `id`, `title`, `language`, `imdb_rating`, `where_to_watch`, `genres`, `themes`, optional `producer`, `hollywood`, `animated`, `inside_out_level`, `in_local_theater`, and either `sources` (ids) or `endorsements` (`{name, url}` or `{source_id, url}`).
