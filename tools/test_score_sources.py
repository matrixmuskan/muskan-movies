import json
import random
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import score_sources as ss  # noqa: E402

SOURCES = {
    "critic-a": {"id": "critic-a", "name": "Critic A", "flavor": "critic", "kind": "critic", "status": "established", "aliases": ["Critic A"]},
    "critic-b": {"id": "critic-b", "name": "Critic B", "flavor": "critic", "kind": "critic", "status": "established", "aliases": ["Critic B"]},
    "critic-c": {"id": "critic-c", "name": "Critic C", "flavor": "critic", "kind": "critic", "status": "established", "aliases": ["Critic C"]},
    "south-x": {"id": "south-x", "name": "South X", "flavor": "south", "kind": "critic", "status": "new", "aliases": ["South X"]},
    "gems-y": {"id": "gems-y", "name": "Gems Y", "flavor": "hidden-gems", "kind": "curator/listicle", "status": "new", "aliases": ["Gems Y"]},
    "chart-z": {"id": "chart-z", "name": "Chart Z", "flavor": "ott-charts", "kind": "chart", "status": "established", "aliases": []},
    "cal-w": {"id": "cal-w", "name": "Calendar W", "flavor": "mainstream-calendar", "kind": "release-calendar", "status": "established", "aliases": []},
    "the-hindu": {"id": "the-hindu", "name": "The Hindu - Reviews", "flavor": "south", "kind": "critic", "status": "established", "aliases": ["The Hindu"]},
}
PROFILE = json.loads((ss.DEFAULT_SITE / "data" / "taste-profile.json").read_text())


def pick(pid, endorsers=(), **kw):
    return {"id": pid, "week": "2026-11-06", "endorsements": [{"name": n, "url": "https://x.example/" + pid + n} for n in endorsers], **kw}


class RewardTests(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(ss.reward("keep", None), 1.0)
        self.assertEqual(ss.reward("discard", None), 0.0)
        self.assertEqual(ss.reward("rate", 5), 1.0)
        self.assertEqual(ss.reward("rate", 4), 1.0)
        self.assertEqual(ss.reward("rate", 3), 0.5)
        self.assertEqual(ss.reward("rate", 2), 0.0)
        self.assertEqual(ss.reward("rate", 1), 0.0)
        self.assertIsNone(ss.reward("rate", None))


class ResolverTests(unittest.TestCase):
    def test_names_and_outlets(self):
        r = ss.Resolver(SOURCES)
        self.assertEqual(r("Critic A"), "critic-a")
        self.assertEqual(r("critic a"), "critic-a")
        self.assertEqual(r("Anuj Kumar (The Hindu)"), "the-hindu")
        self.assertEqual(r("Critic B (Some Paper)"), "critic-b")
        self.assertIsNone(r("Devesh Sharma (Filmfare)"))


class ReplayTests(unittest.TestCase):
    def test_prior_and_updates(self):
        picks = [pick("p1", ["Critic A", "South X"]), pick("p2", ["Critic A"]), pick("p3", ["Gems Y"]), pick("p4", ["Critic B"])]
        fb = [
            {"id": "p1", "action": "rate", "rating": 2, "timestamp": "2026-11-04T10:00:00Z"},
            {"id": "p1", "action": "keep", "rating": None, "timestamp": "2026-11-04T11:00:00Z"},  # newest wins
            {"id": "p2", "action": "rate", "rating": 3, "timestamp": "2026-11-04T10:00:00Z"},
            {"id": "p3", "action": "discard", "rating": None, "timestamp": "2026-11-04T10:00:00Z"},
        ]
        st = ss.replay(SOURCES, picks, fb, today="2026-11-04")
        a = st["sources"]["critic-a"]
        self.assertEqual((a["alpha"], a["beta"]), (3.5, 2.5))   # keep + half
        self.assertEqual((a["surfaced"], a["rated"], a["keeps"], a["discards"]), (2, 2, 1, 0))
        self.assertEqual(a["avg_stars"], 3.0)
        self.assertEqual((st["sources"]["south-x"]["alpha"], st["sources"]["south-x"]["beta"]), (3.0, 2.0))
        self.assertEqual((st["sources"]["gems-y"]["alpha"], st["sources"]["gems-y"]["beta"]), (2.0, 3.0))
        b = st["sources"]["critic-b"]
        self.assertEqual((b["alpha"], b["beta"], b["surfaced"], b["rated"]), (2.0, 2.0, 1, 0))  # surfaced, no feedback
        self.assertEqual(st["sources"]["chart-z"]["mean"], 0.5)  # untouched -> prior
        # critic flavor got p1 (keep), p2 (3 stars): one update per pick, not per source
        self.assertEqual(st["flavors"]["critic"]["n_obs"], 2)

    def test_idempotent(self):
        picks = [pick("p1", ["Critic A"])]
        fb = [{"id": "p1", "action": "keep", "rating": None, "timestamp": "t"}]
        s1 = ss.replay(SOURCES, picks, fb, today="d")
        s2 = ss.replay(SOURCES, picks, fb, old_state=s1, today="d")
        self.assertEqual(s1["sources"], s2["sources"])

    def test_explicit_sources_win_and_unmapped_logged(self):
        picks = [pick("p1", ["Nobody (Filmfare)"], sources=["gems-y"])]
        st = ss.replay(SOURCES, picks, [], today="d")
        self.assertEqual(st["picks"][0]["sources"], ["gems-y"])
        self.assertEqual(st["unmapped_endorsers"], {"Nobody (Filmfare)": 1})

    def test_new_source_starts_at_prior(self):
        st = ss.replay(SOURCES, [], [], today="d")
        more = dict(SOURCES, brand_new={"id": "brand_new", "name": "N", "flavor": "south", "kind": "critic", "status": "new", "aliases": []})
        arms = ss.arms_from_state(st, more)
        self.assertEqual((arms["brand_new"]["alpha"], arms["brand_new"]["beta"]), (2.0, 2.0))


class VoteTests(unittest.TestCase):
    trust = {s: 0.5 for s in SOURCES}

    def test_diversity_beats_echo_chamber(self):
        echo, _ = ss.vote_score(["critic-a", "critic-b", "critic-c"], SOURCES, self.trust)
        diverse, _ = ss.vote_score(["critic-a", "south-x", "the-hindu", "gems-y"][:3], SOURCES, self.trust)
        mixed, _ = ss.vote_score(["critic-a", "south-x", "gems-y"], SOURCES, self.trust)
        self.assertGreater(mixed, echo)

    def test_more_votes_more_score(self):
        one, _ = ss.vote_score(["critic-a"], SOURCES, self.trust)
        two, _ = ss.vote_score(["critic-a", "critic-b"], SOURCES, self.trust)
        self.assertGreater(two, one)

    def test_calendar_has_no_taste_vote_and_chart_small(self):
        none, _ = ss.vote_score([], SOURCES, self.trust)
        cal, votes = ss.vote_score(["cal-w"], SOURCES, self.trust)
        chart, _ = ss.vote_score(["chart-z"], SOURCES, self.trust)
        critic, _ = ss.vote_score(["critic-a"], SOURCES, self.trust)
        self.assertEqual(cal, none)
        self.assertEqual(votes["cal-w"], 0)
        self.assertLess(chart, critic / 3)
        # a calendar does not earn the diversity bonus
        a, _ = ss.vote_score(["critic-a"], SOURCES, self.trust)
        b, _ = ss.vote_score(["critic-a", "cal-w"], SOURCES, self.trust)
        self.assertEqual(a, b)

    def test_trust_matters(self):
        hi = dict(self.trust, **{"critic-a": 0.9})
        lo = dict(self.trust, **{"critic-a": 0.2})
        self.assertGreater(ss.vote_score(["critic-a"], SOURCES, hi)[0], ss.vote_score(["critic-a"], SOURCES, lo)[0])


class HardRuleTests(unittest.TestCase):
    def test_rules(self):
        base = {"title": "X", "imdb_rating": 7.0, "genres": ["comedy"]}
        self.assertIsNone(ss.hard_rule_failure(base, PROFILE))
        self.assertIn("IMDb", ss.hard_rule_failure(dict(base, imdb_rating=5.9), PROFILE))
        self.assertIsNotNone(ss.hard_rule_failure(dict(base, imdb_rating=None), PROFILE))
        self.assertEqual(ss.hard_rule_failure(dict(base, genres=["heavy horror"]), PROFILE), "heavy horror")
        self.assertIsNotNone(ss.hard_rule_failure(dict(base, animated=True), PROFILE))
        self.assertIsNone(ss.hard_rule_failure(dict(base, animated=True, inside_out_level=True), PROFILE))


def cand(cid, sources, imdb=7.0, lang="Hindi", where="Netflix", **kw):
    return {"id": cid, "title": cid, "imdb_rating": imdb, "language": lang, "genres": ["comedy"],
            "where_to_watch": where, "sources": sources, **kw}


class SelectionTests(unittest.TestCase):
    def setUp(self):
        # critic-a and critic-b are well tested and good; the rest untested
        picks = [pick(f"old{i}", ["Critic A", "Critic B", "Critic C"]) for i in range(6)]
        fb = [{"id": f"old{i}", "action": "keep", "rating": None, "timestamp": "t"} for i in range(6)]
        self.state = ss.replay(SOURCES, picks, fb, today="d")

    def test_slots_and_hard_rules(self):
        cands = [cand(f"e{i}", ["critic-a", "critic-b"], imdb=8.0) for i in range(6)]
        cands += [cand("new1", ["south-x"], imdb=7.0), cand("new2", ["gems-y"], imdb=7.0),
                  cand("horror", ["south-x", "gems-y", "critic-a"], imdb=9.0, genres=["heavy horror"]),
                  cand("low", ["south-x"], imdb=5.5)]
        sel = ss.select_weekly(cands, SOURCES, self.state, PROFILE, "2026-11-13")
        self.assertEqual(len(sel), 5)
        slots = [s["slot"] for s in sel]
        self.assertIn(slots.count("explore"), (1, 2))
        self.assertIn(slots.count("exploit"), (3, 4))
        ids = {s["id"] for s in sel}
        self.assertNotIn("horror", ids)
        self.assertNotIn("low", ids)
        for s in sel:
            if s["slot"] == "explore":
                self.assertTrue(set(s["sources"]) & {"south-x", "gems-y"})
            self.assertIsInstance(s["votes"], dict)

    def test_deterministic_for_week(self):
        cands = [cand(f"c{i}", [["south-x"], ["gems-y"], ["critic-a"], ["the-hindu"]][i % 4], imdb=6 + i / 5) for i in range(12)]
        a = ss.select_weekly(cands, SOURCES, self.state, PROFILE, "2026-11-13")
        b = ss.select_weekly(cands, SOURCES, self.state, PROFILE, "2026-11-13")
        self.assertEqual(a, b)

    def test_off_netflix_prime_quota_and_hollywood_cap(self):
        # strongest titles are all on Netflix/Prime; three weaker ones are off it
        cands = [cand(f"nf{i}", ["critic-a", "critic-b"], imdb=9.0, where=["Netflix", "Prime Video"][i % 2]) for i in range(6)]
        cands += [cand("hw1", ["critic-a"], imdb=9.0, lang="English", hollywood=True, where="Apple TV+"),
                  cand("hw2", ["critic-a"], imdb=9.0, lang="English", hollywood=True, where="In theaters"),
                  cand("zee", ["critic-c"], imdb=6.5, where="ZEE5"), cand("jio", ["critic-c"], imdb=6.4, where="JioHotstar"),
                  cand("bad-off", ["critic-c"], imdb=5.0, where="SonyLIV")]
        sel = ss.select_weekly(cands, SOURCES, self.state, PROFILE, "2026-11-13", history=[])
        by_id = {c["id"]: c for c in cands}
        self.assertGreaterEqual(sum(not ss.on_netflix_prime(by_id[s["id"]]) for s in sel), 3)   # 50-50 base: 3 of 5
        self.assertLessEqual(sum(bool(by_id[s["id"]].get("hollywood")) for s in sel), 1)
        self.assertNotIn("bad-off", {s["id"] for s in sel})       # swaps still obey the hard rules
        self.assertTrue(all("on_netflix_prime" in s for s in sel))

    def test_swap_replaces_weakest_netflix_prime_exploit(self):
        cands = [cand(f"nf{i}", ["critic-a", "critic-b"], imdb=6.0 + i / 2, where="Netflix") for i in range(6)]
        cands += [cand("sony", ["critic-c"], imdb=6.2, where="SonyLIV"), cand("aha", ["critic-c"], imdb=6.1, where="Aha"),
                  cand("zee", ["critic-c"], imdb=6.0, where="ZEE5")]
        sel = ss.select_weekly(cands, SOURCES, self.state, PROFILE, "2026-11-13", history=[])
        ids = {s["id"] for s in sel}
        self.assertTrue({"sony", "aha", "zee"} <= ids)
        self.assertNotIn("nf0", ids)          # the weakest Netflix titles went out
        self.assertNotIn("nf1", ids)
        self.assertIn("nf5", ids)             # the strongest stayed

    def test_off_titles_not_forced_onto_netflix(self):
        # an all-off week is left alone: the rule is a floor for off-Netflix/Prime, never a quota for Netflix/Prime
        cands = [cand(f"t{i}", ["critic-a", "critic-b"], imdb=9.0, where="In theaters") for i in range(5)]
        cands += [cand("nf", ["south-x"], imdb=6.5, where="Netflix"), cand("pv", ["gems-y"], imdb=6.5, where="Prime Video")]
        sel = ss.select_weekly(cands, SOURCES, self.state, PROFILE, "2026-11-13", history=[])
        by_id = {c["id"]: c for c in cands}
        self.assertGreaterEqual(sum(not ss.on_netflix_prime(by_id[s["id"]]) for s in sel), 3)

    def test_theater_title_fills_the_off_quota(self):
        # a Prime title that is also in a local theater counts toward the off-Netflix/Prime floor
        cands = [cand(f"nf{i}", ["critic-a", "critic-b"], imdb=9.0, where="Prime Video") for i in range(6)]
        cands += [cand("thr", ["critic-c"], imdb=6.5, where="Prime Video (also still In theaters: Cinemark)"),
                  cand("loc", ["critic-c"], imdb=6.4, where="Prime Video", in_local_theater=True),
                  cand("sony", ["critic-c"], imdb=6.3, where="SonyLIV")]
        sel = ss.select_weekly(cands, SOURCES, self.state, PROFILE, "2026-11-13", history=[])
        ids = {s["id"] for s in sel}
        self.assertTrue({"thr", "loc", "sony"} <= ids)
        self.assertEqual(sum(not s["on_netflix_prime"] for s in sel), 3)

    def test_theater_plus_prime_counts_as_off(self):
        self.assertFalse(ss.on_netflix_prime({"where_to_watch": "Prime Video (also still In theaters: Cinemark Pacific Commons, Fremont)"}))
        self.assertFalse(ss.on_netflix_prime({"where_to_watch": "Prime Video", "in_local_theater": True}))
        self.assertTrue(ss.on_netflix_prime({"where_to_watch": "Prime Video"}))
        self.assertTrue(ss.on_netflix_prime({"where_to_watch": "Netflix (US access not verified)"}))
        for off in ("ZEE5", "SonyLIV", "JioHotstar (India; US access not verified)", "Aha", "Apple TV+", "In theaters: Cinemark"):
            self.assertFalse(ss.on_netflix_prime({"where_to_watch": off}), off)

    def test_constants_are_the_50_50_rule(self):
        self.assertEqual(ss.MIN_NON_NETFLIX_PRIME, 3)
        self.assertEqual(ss.NETFLIX_PRIME_SHARE_CAP, 0.50)

    def test_running_share_pushes_further_off(self):
        hist = lambda on, off: [{"where_to_watch": "Netflix"}] * on + [{"where_to_watch": "ZEE5"}] * off
        self.assertEqual(ss.required_off_netflix_prime([], 5), 3)              # base: 3 of 5
        self.assertEqual(ss.required_off_netflix_prime(hist(5, 15), 5), 3)     # 25%: base
        self.assertEqual(ss.required_off_netflix_prime(hist(10, 10), 5), 3)    # 50% exactly: not above
        self.assertEqual(ss.required_off_netflix_prime(hist(11, 10), 5), 4)    # 52% -> 4
        self.assertEqual(ss.required_off_netflix_prime(hist(14, 6), 5), 4)     # 70% -> 4
        self.assertEqual(ss.required_off_netflix_prime(hist(20, 0), 5), 4)     # never more than 4 of 5
        removed = hist(10, 10) + [{"where_to_watch": "Netflix", "status": "removed"}] * 5
        self.assertEqual(ss.netflix_prime_share(removed), (10, 20))             # removed picks ignored
        self.assertEqual(ss.required_off_netflix_prime(removed, 5), 3)
        mixed = hist(10, 9) + [{"where_to_watch": "Prime Video (also still In theaters: X)"}] + [{"where_to_watch": "Prime Video", "in_local_theater": True}]
        self.assertEqual(ss.netflix_prime_share(mixed), (10, 21))               # theater titles count as off
        self.assertEqual(ss.required_off_netflix_prime(mixed, 5), 3)

    def test_high_share_history_selects_four_off(self):
        cands = [cand(f"nf{i}", ["critic-a", "critic-b"], imdb=9.0, where="Netflix") for i in range(6)]
        cands += [cand(f"off{i}", ["critic-c"], imdb=6.5, where="SonyLIV") for i in range(4)]
        hist = [{"where_to_watch": "Netflix"}] * 14 + [{"where_to_watch": "ZEE5"}] * 6
        sel = ss.select_weekly(cands, SOURCES, self.state, PROFILE, "2026-11-13", history=hist)
        self.assertGreaterEqual(sum(not s["on_netflix_prime"] for s in sel), 4)

    def test_balanced_history_selects_three_off(self):
        cands = [cand(f"nf{i}", ["critic-a", "critic-b"], imdb=9.0, where="Netflix") for i in range(6)]
        cands += [cand(f"off{i}", ["critic-c"], imdb=6.5, where="SonyLIV") for i in range(4)]
        hist = [{"where_to_watch": "Netflix"}] * 10 + [{"where_to_watch": "ZEE5"}] * 10
        sel = ss.select_weekly(cands, SOURCES, self.state, PROFILE, "2026-11-13", history=hist)
        self.assertEqual(sum(not s["on_netflix_prime"] for s in sel), 3)

    def test_record_selection(self):
        sel = ss.select_weekly([cand(f"c{i}", ["critic-a"]) for i in range(5)], SOURCES, self.state, PROFILE, "2026-11-13")
        st = ss.record_selection(json.loads(json.dumps(self.state)), sel)
        logged = {p["id"]: p for p in st["picks"]}
        self.assertEqual(logged["c0"]["votes_recorded"], "rank 2026-11-13")


class BackfillAndReportTests(unittest.TestCase):
    def test_backfill(self):
        picks = [pick("p1", ["Critic A", "Anuj Kumar (The Hindu)", "Nobody"]), pick("p2", [], slot="explore", sources=["gems-y"])]
        n = ss.backfill_picks(picks, ss.Resolver(SOURCES))
        self.assertEqual(picks[0]["sources"], ["critic-a", "the-hindu"])
        self.assertEqual(picks[0]["slot"], "exploit")
        self.assertEqual(picks[1]["slot"], "explore")
        self.assertEqual(n, 2)

    def test_report(self):
        picks = [pick("p1", ["Critic A"]), pick("p2", ["Gems Y"])]
        fb = [{"id": "p1", "action": "rate", "rating": 5, "timestamp": "t"}, {"id": "p2", "action": "discard", "rating": None, "timestamp": "t"}]
        text = ss.source_report(ss.replay(SOURCES, picks, fb, today="d"), top=1)
        top = text.split("Bottom")[0]
        self.assertIn("critic-a", top)
        self.assertIn("gems-y", text.split("Bottom")[1].split("\n")[1])
        self.assertIn("Untested:", text)


class RealFilesTests(unittest.TestCase):
    def test_sources_json(self):
        src = ss.load_sources(ss.DEFAULT_SOURCES)
        self.assertGreaterEqual(len(src), 29)
        for sid, s in src.items():
            self.assertRegex(sid, r"^[a-z0-9][a-z0-9-]*$")
            self.assertIn(s["kind"], ss.KIND_WEIGHT)
            self.assertIn(s["status"], ("established", "new"))
        self.assertEqual(sum(s["status"] == "new" for s in src.values()), 10)
        r = ss.Resolver(src)
        self.assertEqual(r("Rahul Desai"), "rahul-desai")
        self.assertEqual(r("Anuj Kumar (The Hindu)"), "the-hindu-reviews")
        self.assertEqual(r("Yashaswini Sri (The Indian Express)"), "indian-express-reviews")
        self.assertEqual(r("Suchin Mehrotra (THR India)"), "thr-india-reviews")


if __name__ == "__main__":
    unittest.main()
