#!/usr/bin/env python3
"""Source voting + source-trust bandit for Muskan's weekly movie picks.

Data in, data out (no network unless you ask for `fetch`/`weekly`):
  sources.json                  vetted sources, each with id / flavor / kind / status / aliases
  <site>/data/picks.json        published picks; each gets `slot` and `sources`
  <site>/data/taste-profile.json  weights and hard filters
  feedback dump                 bodies from matrixmuskan/muskan-movies-feedback/feedback/
  <site>/data/source-scores.json  the state file this script writes (not on the site)

Design
  * Vote: every source that recommends a title adds kind_weight * trust. Votes from the same
    flavor shrink (1, 1/2, 1/4 ...) and each extra distinct flavor adds a small bonus, so
    independent agreement beats an echo chamber. Charts vote 0.2, release calendars 0.
  * Score = 0.45 * votes(squashed to 0..1) + 0.35 * taste match + 0.20 * IMDb(6->0, 9->1).
  * Trust: Beta(alpha, beta) per source, prior Beta(2, 2) for everyone (new sources too).
    Keep / 4-5 stars = success, Discard / 1-2 = failure, 3 = half of each, applied to every
    source that endorsed the pick. The state is rebuilt from the prior by replaying the
    newest feedback file per pick, so re-running never double-counts.
  * Weekly 5: 3-4 exploit (best score with mean trust), 1-2 explore (best Thompson-sampled
    score among titles backed by a new / under-sampled source or a less-tested flavor).
    Every pick must pass the hard rules first. 50-50 platform rule: at least 3 of 5 must be OFF
    Netflix/Prime Video (theaters, JioHotstar, SonyLIV, ZEE5, Aha, Apple TV+ ...), and 4 of 5 when
    the running share of Netflix/Prime across active (not removed) picks in picks.json is above 50%.
    A title showing in a local theater counts as off Netflix/Prime.

CLI
  score_sources.py fetch    --out feedback.json            (gh or $MOVIES_FEEDBACK_TOKEN; token never printed)
  score_sources.py backfill --picks P                       (adds slot/sources to picks without them)
  score_sources.py update   --picks P --feedback F --state S
  score_sources.py rank     --candidates C --week YYYY-MM-DD --state S [--record]
  score_sources.py report   --state S
  score_sources.py weekly   [--candidates C --week W]       (fetch + backfill + update + report [+ rank])
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Works from /workspace/muskan-movies (sources.json beside it) and from the site repo's tools/.
_IN_REPO = (HERE.parent / "data" / "picks.json").exists()
DEFAULT_SITE = Path(os.environ.get("MOVIES_SITE_DIR") or (HERE.parent if _IN_REPO else "/workspace/site"))
DEFAULT_SOURCES = HERE / "sources.json" if (HERE / "sources.json").exists() else DEFAULT_SITE / "data" / "sources.json"
FEEDBACK_REPO = "matrixmuskan/muskan-movies-feedback"

PRIOR = (2.0, 2.0)
KIND_WEIGHT = {"critic": 1.0, "curator/listicle": 0.8, "chart": 0.2, "release-calendar": 0.0}
SAME_FLAVOR_DECAY = 0.5
DIVERSITY_BONUS = 0.10
W_VOTES, W_TASTE, W_IMDB = 0.45, 0.35, 0.20
UNDER_SAMPLED = 3          # a source / flavor with fewer observations than this is "under-sampled"
MIN_NON_NETFLIX_PRIME = 3  # 50-50 rule: at least 3 of 5 OFF Netflix / Prime Video (theaters, JioHotstar, SonyLIV, ZEE5, Aha, Apple TV+ ...)
NETFLIX_PRIME_SHARE_CAP = 0.50  # if the running share across active picks is above this, require MIN_NON_NETFLIX_PRIME + 1 (4 of 5)
MAX_HOLLYWOOD = 1          # <= 20% of 5
NETFLIX_PRIME = ("netflix", "prime video", "amazon prime")
THEATER_MARKERS = ("in theaters", "in theatres", "in cinemas")


# ---------------------------------------------------------------- sources
def load_sources(path: Path = DEFAULT_SOURCES) -> dict[str, dict]:
    doc = json.loads(Path(path).read_text())
    out: dict[str, dict] = {}
    for section in ("social_sources", "review_sites"):
        for s in doc.get(section, []):
            sid = s["id"]
            if sid in out:  # same outlet listed twice (fcg): merge aliases
                out[sid]["aliases"] = sorted(set(out[sid]["aliases"]) | set(s.get("aliases", [])) | {s["name"]})
                continue
            out[sid] = {
                "id": sid, "name": s["name"], "flavor": s["flavor"], "kind": s["kind"],
                "status": s.get("status", "established"),
                "aliases": sorted(set(s.get("aliases", [])) | {s["name"]}),
            }
    return out


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


class Resolver:
    """Maps an endorsement name ('Anuj Kumar (The Hindu)') to a source id or None."""

    def __init__(self, sources: dict[str, dict]):
        self.index: dict[str, str] = {}
        for sid, s in sources.items():      # names and aliases first ...
            for name in s["aliases"]:
                self.index.setdefault(_norm(name), sid)
        for sid in sources:                 # ... then bare ids
            self.index.setdefault(_norm(sid), sid)

    def __call__(self, name: str) -> str | None:
        key = _norm(name)
        if key in self.index:
            return self.index[key]
        m = re.match(r"^(.*?)\s*\((.*)\)\s*$", name)
        if m:
            person, outlet = _norm(m.group(1)), _norm(m.group(2))
            if person in self.index:      # 'Rahul Desai (THR India)' -> the person
                return self.index[person]
            if outlet in self.index:      # 'Anuj Kumar (The Hindu)' -> the outlet
                return self.index[outlet]
        return None


# ---------------------------------------------------------------- bandit
def new_arm() -> dict:
    return {"alpha": PRIOR[0], "beta": PRIOR[1], "n_obs": 0, "surfaced": 0, "rated": 0,
            "stars_sum": 0, "stars_count": 0, "keeps": 0, "discards": 0,
            "successes": 0.0, "failures": 0.0}


def mean(arm: dict) -> float:
    return arm["alpha"] / (arm["alpha"] + arm["beta"])


def thompson(arm: dict, rng: random.Random) -> float:
    return rng.betavariate(arm["alpha"], arm["beta"])


def ucb(arm: dict, total_obs: int, c: float = 0.5) -> float:
    n = arm["alpha"] + arm["beta"]
    return mean(arm) + c * math.sqrt(math.log(max(total_obs, 1) + 1) / n)


def reward(action: str, rating: int | None) -> float | None:
    if action == "keep":
        return 1.0
    if action == "discard":
        return 0.0
    if action == "rate" and isinstance(rating, int):
        if rating >= 4:
            return 1.0
        if rating <= 2:
            return 0.0
        return 0.5
    return None


def latest_feedback(bodies: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for item in bodies:
        body = item.get("body", item)
        pid = body.get("id")
        if not pid or "timestamp" not in body:
            continue
        if pid not in latest or body["timestamp"] >= latest[pid]["timestamp"]:
            latest[pid] = body
    return latest


def pick_sources(pick: dict, resolve: Resolver) -> list[str]:
    if isinstance(pick.get("sources"), list):
        return list(dict.fromkeys(pick["sources"]))
    ids = [resolve(e["name"]) for e in pick.get("endorsements", [])]
    return list(dict.fromkeys(i for i in ids if i))


def replay(sources: dict[str, dict], picks: list[dict], feedback: list[dict],
           old_state: dict | None = None, today: str | None = None) -> dict:
    """Rebuild the whole state from the prior. Pure function of its inputs."""
    resolve = Resolver(sources)
    arms = {sid: new_arm() for sid in sources}
    flavors = {s["flavor"]: new_arm() for s in sources.values()}
    latest = latest_feedback(feedback)
    old_picks = {p["id"]: p for p in (old_state or {}).get("picks", [])}
    unmapped: dict[str, int] = {}
    log = []
    for pick in picks:
        sids = [s for s in pick_sources(pick, resolve) if s in arms]
        for e in pick.get("endorsements", []):
            if not resolve(e["name"]):
                unmapped[e["name"]] = unmapped.get(e["name"], 0) + 1
        fb = latest.get(pick["id"])
        r = reward(fb["action"], fb.get("rating")) if fb else None
        for sid in sids:
            arms[sid]["surfaced"] += 1
        for fl in {sources[s]["flavor"] for s in sids}:
            flavors[fl]["surfaced"] += 1
        if r is not None:
            touched = [arms[s] for s in sids] + [flavors[f] for f in {sources[s]["flavor"] for s in sids}]
            for i, arm in enumerate(touched):
                arm["alpha"] += r
                arm["beta"] += 1 - r
                arm["n_obs"] += 1
                arm["rated"] += 1
                arm["successes"] += r
                arm["failures"] += 1 - r
                if fb["action"] == "rate":
                    arm["stars_sum"] += fb["rating"]
                    arm["stars_count"] += 1
                arm["keeps"] += fb["action"] == "keep"
                arm["discards"] += fb["action"] == "discard"
        prev = old_picks.get(pick["id"], {})
        log.append({
            "id": pick["id"], "week": pick.get("week"), "slot": pick.get("slot", prev.get("slot")),
            "sources": sids,
            "votes": prev.get("votes") or {s: round(KIND_WEIGHT[sources[s]["kind"]] * mean(new_arm()), 3) for s in sids},
            "votes_recorded": prev.get("votes_recorded", "backfill (prior trust 0.50)"),
            "score": prev.get("score"),
            "feedback": ({"action": fb["action"], "rating": fb.get("rating"), "timestamp": fb["timestamp"]} if fb else None),
            "reward": r,
        })
    out_sources = {}
    for sid, arm in arms.items():
        s = sources[sid]
        out_sources[sid] = {"name": s["name"], "flavor": s["flavor"], "kind": s["kind"], "status": s["status"],
                            **_finish(arm)}
    return {
        "version": 1,
        "updated": today or date.today().isoformat(),
        "method": "Beta-Bernoulli bandit per source, Thompson sampling for exploration; state rebuilt from the prior on every update",
        "prior": {"alpha": PRIOR[0], "beta": PRIOR[1]},
        "reward_rules": {"keep": 1, "rate 4-5": 1, "rate 3": 0.5, "rate 1-2": 0, "discard": 0,
                         "applies_to": "every source in the pick's `sources`; newest feedback file per pick only"},
        "vote_rules": {"kind_weight": KIND_WEIGHT, "same_flavor_decay": SAME_FLAVOR_DECAY,
                       "diversity_bonus_per_extra_flavor": DIVERSITY_BONUS,
                       "squash": "votes = 1 - exp(-(sum + bonus))",
                       "score": f"{W_VOTES}*votes + {W_TASTE}*taste + {W_IMDB}*imdb((r-6)/3, clipped)"},
        "explore_rules": {"under_sampled_if_n_obs_below": UNDER_SAMPLED,
                          "slots": "2 explore + 3 exploit while most taste sources are under-sampled, else 1 + 4"},
        "sources": out_sources,
        "flavors": {f: _finish(a) for f, a in flavors.items()},
        "picks": log,
        "unmapped_endorsers": dict(sorted(unmapped.items(), key=lambda kv: (-kv[1], kv[0]))),
    }


def _finish(arm: dict) -> dict:
    a = dict(arm)
    a["mean"] = round(mean(arm), 4)
    a["avg_stars"] = round(arm["stars_sum"] / arm["stars_count"], 2) if arm["stars_count"] else None
    for k in ("alpha", "beta", "successes", "failures"):
        a[k] = round(a[k], 3)
    return a


def arms_from_state(state: dict, sources: dict[str, dict]) -> dict[str, dict]:
    """State arms, with any source missing from the state starting at the prior."""
    arms = {}
    for sid in sources:
        arms[sid] = state.get("sources", {}).get(sid) or {**new_arm(), "mean": 0.5}
    return arms


# ---------------------------------------------------------------- voting / scoring
def vote_score(sids: list[str], sources: dict[str, dict], trust: dict[str, float]) -> tuple[float, dict[str, float]]:
    by_flavor: dict[str, list[tuple[str, float]]] = {}
    for sid in dict.fromkeys(sids):
        if sid not in sources:
            continue
        w = KIND_WEIGHT[sources[sid]["kind"]] * trust[sid]
        by_flavor.setdefault(sources[sid]["flavor"], []).append((sid, w))
    votes: dict[str, float] = {}
    total = 0.0
    taste_flavors = 0
    for fl, items in by_flavor.items():
        items.sort(key=lambda kv: -kv[1])
        for i, (sid, w) in enumerate(items):
            v = w * SAME_FLAVOR_DECAY ** i
            votes[sid] = round(v, 4)
            total += v
        if any(w > 0 for _, w in items):
            taste_flavors += 1
    bonus = DIVERSITY_BONUS * max(taste_flavors - 1, 0)
    return 1 - math.exp(-(total + bonus)), votes


def _lang_key(language: str) -> str:
    l = language.lower()
    for south in ("tamil", "telugu", "malayalam", "kannada"):
        if south in l:
            return f"{south.title()} (Hindi dub)"
    if "hindi" in l:
        return "Hindi"
    if "english" in l:
        return "English (Hollywood)"
    return "Other"


def taste_match(cand: dict, profile: dict) -> float:
    lang = profile.get("language_weights", {}).get(_lang_key(cand.get("language", "")), 0.1)
    table = {}
    for key in ("genre_weights", "theme_weights", "producer_weights"):
        table.update({k.lower(): v for k, v in profile.get(key, {}).items()})
    tags = list(cand.get("genres", [])) + list(cand.get("themes", []))
    if cand.get("producer"):
        tags.append(cand["producer"])
    weights = sorted((table[t.lower()] for t in tags if t.lower() in table), reverse=True)
    tag = sum(weights[:3]) / len(weights[:3]) if weights else 0.5
    return round(0.4 * lang + 0.6 * tag, 4)


def imdb_part(rating) -> float:
    if rating is None:
        return 0.0
    return min(max((float(rating) - 6.0) / 3.0, 0.0), 1.0)


def hard_rule_failure(cand: dict, profile: dict) -> str | None:
    hf = profile.get("hard_filters", {})
    r = cand.get("imdb_rating")
    if r is None:
        return "no IMDb rating yet"
    if float(r) < hf.get("min_imdb_rating", 6.0):
        return f"IMDb {r} < {hf.get('min_imdb_rating', 6.0)}"
    tags = {t.lower() for t in cand.get("genres", []) + cand.get("themes", [])}
    if "heavy horror" in tags or cand.get("horror") == "heavy":
        return "heavy horror"
    if cand.get("animated") and not cand.get("inside_out_level"):
        return "animated (not Inside Out-level)"
    seen = {_norm(t) for t in profile.get("seen", []) + profile.get("seen_or_rejected", [])}
    if _norm(cand.get("title", "")) in seen:
        return "already seen"
    return None


def score(cand: dict, sids: list[str], sources: dict, trust: dict, profile: dict) -> tuple[float, dict]:
    v, votes = vote_score(sids, sources, trust)
    t = taste_match(cand, profile)
    s = W_VOTES * v + W_TASTE * t + W_IMDB * imdb_part(cand.get("imdb_rating"))
    return round(s, 4), {"votes": votes, "vote_score": round(v, 4), "taste": t}


def candidate_sources(cand: dict, resolve: Resolver, sources: dict) -> list[str]:
    ids = list(cand.get("sources", []))
    for e in cand.get("endorsements", []):
        sid = e.get("source_id") or resolve(e.get("name", ""))
        if sid:
            ids.append(sid)
    return [i for i in dict.fromkeys(ids) if i in sources]


def is_explore_eligible(sids: list[str], sources: dict, arms: dict, flavor_arms: dict) -> bool:
    for sid in sids:
        if KIND_WEIGHT[sources[sid]["kind"]] == 0:
            continue
        if sources[sid]["status"] == "new" or arms[sid]["n_obs"] < UNDER_SAMPLED:
            return True
        if flavor_arms.get(sources[sid]["flavor"], {}).get("n_obs", 0) < UNDER_SAMPLED:
            return True
    return False


def explore_slots(sources: dict, arms: dict) -> int:
    taste = [s for s in sources if KIND_WEIGHT[sources[s]["kind"]] > 0]
    under = sum(arms[s]["n_obs"] < UNDER_SAMPLED for s in taste)
    return 2 if taste and under / len(taste) >= 0.5 else 1


def on_netflix_prime(c: dict) -> bool:
    """True only if the title is watched on Netflix / Prime Video. A title that is also in a
    local theater this week (where_to_watch says 'In theaters', or in_local_theater is true)
    counts as off-Netflix/Prime, so it is never double-counted."""
    where = c.get("where_to_watch", "").lower()
    if c.get("in_local_theater") or any(m in where for m in THEATER_MARKERS):
        return False
    return any(s in where for s in NETFLIX_PRIME)


def netflix_prime_share(history: list[dict]) -> tuple[int, int]:
    """(on Netflix/Prime, total) across all weeks of active picks; removed picks don't count."""
    live = [p for p in history if p.get("status") != "removed"]
    return sum(on_netflix_prime(p) for p in live), len(live)


def required_off_netflix_prime(history: list[dict] | None, n: int = 5) -> int:
    """50-50 rule: at least MIN_NON_NETFLIX_PRIME (3) of n=5 off Netflix/Prime. When the running
    share across active picks is above NETFLIX_PRIME_SHARE_CAP (50%), raise it by one (4 of 5).
    For other n the base scales to ceil(n * 3/5); never more than n - 1."""
    need = MIN_NON_NETFLIX_PRIME if n == 5 else math.ceil(n * MIN_NON_NETFLIX_PRIME / 5)
    on, total = netflix_prime_share(history or [])
    if total and on / total > NETFLIX_PRIME_SHARE_CAP:
        need += 1
    return max(0, min(need, n - 1))


def select_weekly(candidates: list[dict], sources: dict, state: dict, profile: dict,
                  week: str, n: int = 5, seed: str | None = None,
                  history: list[dict] | None = None) -> list[dict]:
    rng = random.Random(seed or week)
    resolve = Resolver(sources)
    arms = arms_from_state(state, sources)
    flavor_arms = state.get("flavors", {})
    mean_trust = {sid: mean(a) for sid, a in arms.items()}
    sampled = {sid: thompson(a, rng) for sid, a in arms.items()}
    pool = []
    for c in candidates:
        why_not = hard_rule_failure(c, profile)
        if why_not:
            continue
        sids = candidate_sources(c, resolve, sources)
        s_exploit, detail = score(c, sids, sources, mean_trust, profile)
        s_explore, _ = score(c, sids, sources, sampled, profile)
        pool.append({"cand": c, "sids": sids, "exploit": s_exploit, "explore": s_explore, "detail": detail,
                     "explore_ok": is_explore_eligible(sids, sources, arms, flavor_arms)})
    n_explore = min(explore_slots(sources, arms), n - 1)
    chosen: list[dict] = []

    def hollywood_ok(item):
        hw = sum(1 for x in chosen if x["cand"].get("hollywood"))
        return not item["cand"].get("hollywood") or hw < MAX_HOLLYWOOD

    for item in sorted(pool, key=lambda x: -x["exploit"]):
        if len(chosen) >= n - n_explore:
            break
        if hollywood_ok(item):
            chosen.append({**item, "slot": "exploit"})
    used = lambda item: any(item["cand"] is c_["cand"] for c_ in chosen)
    for item in sorted((x for x in pool if x["explore_ok"] and not used(x)), key=lambda x: -x["explore"]):
        if len(chosen) >= n:
            break
        if hollywood_ok(item):
            chosen.append({**item, "slot": "explore"})
    # not enough explore titles: fill with the next best exploit titles
    for item in sorted(pool, key=lambda x: -x["exploit"]):
        if len(chosen) >= n:
            break
        if not used(item) and hollywood_ok(item):
            chosen.append({**item, "slot": "exploit"})
    # Platform mix: at least `need_off` picks OFF Netflix/Prime. Swap the weakest exploit pick that
    # IS on Netflix/Prime for the best unused off-Netflix/Prime title (pool already passed the hard rules).
    need_off = required_off_netflix_prime(history, n)
    while sum(not on_netflix_prime(x["cand"]) for x in chosen) < need_off:
        weak = sorted((x for x in chosen if x["slot"] == "exploit" and on_netflix_prime(x["cand"])),
                      key=lambda x: x["exploit"])
        if not weak:
            break
        out = weak[0]
        hw_left = sum(1 for x in chosen if x is not out and x["cand"].get("hollywood"))
        spare = [x for x in sorted(pool, key=lambda x: -x["exploit"])
                 if not on_netflix_prime(x["cand"]) and not used(x)
                 and (not x["cand"].get("hollywood") or hw_left < MAX_HOLLYWOOD)]
        if not spare:
            break
        chosen[chosen.index(out)] = {**spare[0], "slot": "exploit"}
    result = []
    for x in chosen:
        c = x["cand"]
        result.append({"id": c["id"], "title": c.get("title"), "slot": x["slot"], "sources": x["sids"],
                       "votes": x["detail"]["votes"], "score": x["exploit"],
                       "explore_score": round(x["explore"], 4), "taste": x["detail"]["taste"],
                       "vote_score": x["detail"]["vote_score"], "week": week,
                       "on_netflix_prime": on_netflix_prime(c)})
    return result


def record_selection(state: dict, selection: list[dict]) -> dict:
    by_id = {p["id"]: p for p in state.setdefault("picks", [])}
    for s in selection:
        entry = by_id.get(s["id"])
        if entry is None:
            entry = {"id": s["id"], "feedback": None, "reward": None}
            state["picks"].append(entry)
            by_id[s["id"]] = entry
        entry.update(week=s["week"], slot=s["slot"], sources=s["sources"], votes=s["votes"], score=s["score"],
                     votes_recorded=f"rank {s['week']}")
    return state


# ---------------------------------------------------------------- picks back-fill
def backfill_picks(picks: list[dict], resolve: Resolver) -> int:
    changed = 0
    for p in picks:
        if p.get("preview"):
            continue   # labeled previews are not fresh picks: no slot, no bandit credit
        if "sources" not in p:
            p["sources"] = pick_sources(p, resolve)
            changed += 1
        if "slot" not in p:
            p["slot"] = "exploit"   # chosen before the bandit existed: no deliberate exploration
            changed += 1
    return changed


# ---------------------------------------------------------------- report
def source_report(state: dict, top: int = 5) -> str:
    rows = state["sources"]
    tested = sorted(((sid, a) for sid, a in rows.items() if a["n_obs"] > 0),
                    key=lambda kv: (-kv[1]["mean"], -kv[1]["n_obs"], kv[0]))
    untested = sorted(sid for sid, a in rows.items() if a["n_obs"] == 0)

    def line(sid, a):
        stars = f"{a['avg_stars']:.1f}" if a["avg_stars"] is not None else "-"
        return (f"  {sid:<24} trust {a['mean']:.2f}  Beta({a['alpha']:g},{a['beta']:g})  "
                f"surfaced {a['surfaced']:>2}  rated {a['rated']:>2}  avg* {stars:>3}  "
                f"keeps {a['keeps']}  discards {a['discards']}  [{a['flavor']}, {a['status']}]")

    out = [f"Source report ({state['updated']}): {len(tested)} sources with feedback, {len(untested)} untested at prior 0.50"]
    out.append("Top by mean trust:")
    out += [line(*kv) for kv in tested[:top]] or ["  (no rated picks yet)"]
    out.append("Bottom by mean trust:")
    shown = {sid for sid, _ in tested[:top]}
    bottom = [kv for kv in tested[::-1][:top] if kv[0] not in shown]
    if bottom:
        out += [line(*kv) for kv in bottom]
    elif tested:
        out.append(f"  (only {len(tested)} rated sources so far, all listed above)")
    else:
        out.append("  (no rated picks yet)")
    surfaced_untested = [s for s in untested if rows[s]["surfaced"]]
    if surfaced_untested:
        out.append("Surfaced but not rated yet: " + ", ".join(f"{s} ({rows[s]['surfaced']})" for s in surfaced_untested))
    out.append("Untested: " + ", ".join(s for s in untested if s not in surfaced_untested))
    fl = sorted(state.get("flavors", {}).items(), key=lambda kv: (-kv[1]["mean"], kv[0]))
    out.append("Flavors: " + "; ".join(f"{f} {a['mean']:.2f} (n={a['n_obs']})" for f, a in fl))
    return "\n".join(out)


# ---------------------------------------------------------------- feedback fetch
def fetch_feedback(repo: str = FEEDBACK_REPO) -> list[dict]:
    token = os.environ.get("MOVIES_FEEDBACK_TOKEN")

    def get(path: str) -> dict | list:
        if token:
            req = urllib.request.Request(f"https://api.github.com/repos/{repo}/{path}",
                                         headers={"Authorization": f"Bearer {token}",
                                                  "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        out = subprocess.run(["gh", "api", f"repos/{repo}/{path}"], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    tree = get("git/trees/main?recursive=1")
    bodies = []
    for item in tree.get("tree", []):
        if item["type"] == "blob" and item["path"].startswith("feedback/") and item["path"].endswith(".json"):
            blob = get(f"contents/{item['path']}")
            bodies.append({"path": item["path"], "body": json.loads(base64.b64decode(blob["content"]))})
    return bodies


# ---------------------------------------------------------------- CLI
def _read(path):
    return json.loads(Path(path).read_text())


def _write(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["fetch", "backfill", "update", "rank", "report", "weekly"])
    ap.add_argument("--sources", default=str(DEFAULT_SOURCES))
    ap.add_argument("--site", default=str(DEFAULT_SITE))
    ap.add_argument("--picks")
    ap.add_argument("--profile")
    ap.add_argument("--feedback", default=str(HERE / "feedback_dump" / "feedback.json"))
    ap.add_argument("--state")
    ap.add_argument("--out")
    ap.add_argument("--candidates")
    ap.add_argument("--week")
    ap.add_argument("--record", action="store_true", help="rank: write the selection's votes into the state")
    ap.add_argument("--top", type=int, default=5)
    a = ap.parse_args(argv)
    site = Path(a.site)
    picks_path = Path(a.picks or site / "data" / "picks.json")
    profile_path = Path(a.profile or site / "data" / "taste-profile.json")
    state_path = Path(a.state or site / "data" / "source-scores.json")
    sources = load_sources(a.sources)

    if a.cmd in ("fetch", "weekly"):
        bodies = fetch_feedback()
        Path(a.feedback).parent.mkdir(parents=True, exist_ok=True)
        _write(a.out if a.cmd == "fetch" and a.out else a.feedback, bodies)
        print(f"fetched {len(bodies)} feedback files")
        if a.cmd == "fetch":
            return
    if a.cmd in ("backfill", "weekly"):
        picks = _read(picks_path)
        n = backfill_picks(picks, Resolver(sources))
        if n:
            _write(picks_path, picks)
        print(f"backfill: {n} fields added to {picks_path}")
    if a.cmd in ("update", "weekly"):
        old = _read(state_path) if state_path.exists() else None
        fb = _read(a.feedback) if Path(a.feedback).exists() else []
        state = replay(sources, _read(picks_path), fb, old)
        _write(state_path, state)
        if not _IN_REPO and state_path.resolve() != (HERE / "source-scores.json").resolve():
            shutil.copy(state_path, HERE / "source-scores.json")  # working copy next to sources.json
        print(f"state: {state_path}")
    if a.cmd in ("rank",) or (a.cmd == "weekly" and a.candidates):
        state = _read(state_path)
        cands = _read(a.candidates)
        week = a.week or date.today().isoformat()
        sel = select_weekly(cands, sources, state, _read(profile_path), week, history=_read(picks_path))
        print(json.dumps(sel, indent=2, ensure_ascii=False))
        if a.out:
            _write(a.out, sel)
        if a.record:
            _write(state_path, record_selection(state, sel))
    if a.cmd in ("report", "update", "weekly"):
        print(source_report(_read(state_path), a.top))


if __name__ == "__main__":
    main()
