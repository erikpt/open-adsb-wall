"""Multi-aircraft card cycling, up to 5 jets / 12 s each (issue #20).

Deliberately NOT built on lib/hero.py's Hero class: hero.py's hysteresis
exists to stop a single shown card from flapping between two near-equidistant
planes -- it has nothing to do once every candidate gets a fixed-length turn
regardless of rank. Cycle only tracks "how far through the current snapshot,
how long has this card been up", and reuses hero.py's pure rank() for the
same closest-first ordering, nothing else from it.

The snapshot and the OpenSky poll are intentionally decoupled: build() is
only meant to be called once code.py's poll cadence has fresh candidates, but
replacing the snapshot mid-rotation would flap every card back to the first
one every ~15 s poll (a 5-card list takes 60 s to get through once at 12 s
each) -- so build() is gated by ready_for_build() having completed a full
pass of whatever is currently showing, not by "a poll happened". No map view
(issue #20 is explicit about that) -- this only ever hands back one
candidate dict at a time, in lib/hero.py:candidates()'s shape, for
firmware/code.py to assemble into the same card dict single-hero mode uses.
"""
from hero import rank

DWELL_S = 12
MAX_CARDS = 5


class Cycle:
    """One instance lives for the whole run (firmware/code.py), same as
    lib/hero.py:Hero."""

    def __init__(self, dwell_s=DWELL_S, max_cards=MAX_CARDS):
        self.dwell_s = dwell_s
        self.max_cards = max_cards
        self.list = []            # current snapshot, closest-first, <= max_cards
        self.index = 0
        self.since = None         # monotonic time self.index was last (re)shown; None = not yet ticked
        self._completed_round = True  # no snapshot yet: build() is due immediately

    def ready_for_build(self):
        """True once the current snapshot has been shown all the way through
        (or there isn't one yet) -- code.py's signal that it's safe to spend
        a poll's results on a fresh snapshot instead of discarding them."""
        return self._completed_round or not self.list

    def build(self, cands):
        """Replace the snapshot with the closest max_cards candidates
        (hero.py:rank() order) and restart the rotation at card 0. Call only
        when ready_for_build() is true -- see module docstring."""
        self.list = sorted(cands, key=rank)[: self.max_cards]
        self.index = 0
        self.since = None
        self._completed_round = False

    def tick(self, now):
        """The candidate dict to show right now, or None (empty snapshot --
        code.py renders this the same as hero mode's "no traffic"). Advances
        to the next card once dwell_s has elapsed; wrapping from the last
        card back to the first is what sets ready_for_build()."""
        if not self.list:
            return None
        if self.since is None:
            self.since = now
        elif now - self.since >= self.dwell_s:
            self.index += 1
            if self.index >= len(self.list):
                self.index = 0
                self._completed_round = True
            self.since = now
        return self.list[self.index]
