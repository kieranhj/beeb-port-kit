"""probe.py - the score a ROM model gets against a capture, and the verdict it implies.

Fork this into your project's tools/; keep this header.

The shape of every probe in 1942-beeb (`tools/probe_efire.py`, `probe_pdeath.py`,
`probe_large.py`, `probe_bomber.py`, `probe_turner.py`, `probe_sound.py`): a Python
transliteration of a ROM routine is stepped frame by frame over a MAME RAM capture,
and every prediction is compared with what the arcade did.

THE PASS MARK IS 0 WRONG, WITH EVERY EXCLUDED SAMPLE NAMED AND COUNTED. "A residual you
cannot explain is a defect you have not found yet": 3 jumps in 32,971 samples were a
real coordinate defect (1942-beeb BUGS.md #8), and 3,333 frames once rationalised away
were another (#10). What 1942 learned about the residue, all of which this class makes
cheap to do and expensive to skip:

  * EXCLUDE BY A NAMED CAUSE, NEVER BY A TOLERANCE. probe_efire's exclusions read "a
    freeze flag was set", "a sprite record was freed inside the frame", "a formation
    member ($41A3, no gun)" - each a fact about the frame, each checked, each counted.
    exclude() takes a reason and the report prints every reason with its count.
  * THE INSTRUMENT HAS ITS OWN PHASE. A capture of sprite RAM is one mover step late
    (it is LDIR'd from a shadow copy: 0 of 83 became 83 of 83 once allowed for,
    arcade-facts s16); a RAM-to-RAM read is not (six residuals in 2,146, s18). Four
    "mover" residuals were all the capture's frame boundary (s19). Check the lag
    before the rule.
  * A TORN SAMPLE IS NOT A PASS. MAME samples at frame end and a sub-CPU's IRQ can be
    mid-handler then; probe_sound counted 146 such frames - but a model error
    PROPAGATES and a torn snapshot does not, so a torn sample must be FOLLOWED BY A
    MATCH on the same rule, or it is wrong. observe(..., torn_ok=True).
  * A CHECK THAT RAN OVER NOTHING IS NOT A PASS. A rule with zero samples fails, and
    so does a declared coverage path that was never taken (cover/require).
  * PER TYPE, NEVER IN AGGREGATE. 113 of stage 1's 119 objects were one plane type, so
    an aggregate score measured almost nothing (arcade-facts s12). Give each kind its
    own rule.
  * "UNREAD" IS A VALUE. A model that returns None on a path it does not follow
    behaves like a model that answered (s28). Raise Unread instead, and the probe
    records it as wrong, named.

    s = Score("enemy gun")
    for f in frames:
        if frozen(f): s.exclude("a freeze flag was set"); continue
        s.observe("$50F9 gates", predict(f) == observed(f), key=f, detail=(...))
        s.cover("fired at heading %d" % h)
    s.require("fired at heading 0")
    sys.exit(s.finish())
"""

import collections
import sys


class Unread(Exception):
    """Raise from a model on a path it does not follow. Never return a default."""


class Score:
    def __init__(self, title, first=8):
        self.title, self.first = title, first
        self.rules = collections.OrderedDict()      # rule -> [match, wrong, torn]
        self.wrongs = collections.defaultdict(list)  # rule -> first N (key, detail)
        self.torns = collections.defaultdict(list)
        self.excluded = collections.Counter()
        self.covered = collections.Counter()
        self.required = collections.OrderedDict()
        self._pending = {}                           # rule -> (key, detail) awaiting a match

    def _rule(self, rule):
        return self.rules.setdefault(rule, [0, 0, 0])

    def _wrong(self, rule, key, detail):
        r = self._rule(rule)
        r[1] += 1
        if len(self.wrongs[rule]) < self.first:
            self.wrongs[rule].append((key, detail))

    def observe(self, rule, ok, key=None, detail=None, torn_ok=False):
        """One prediction against one observation.

        torn_ok: a mismatch is held as possibly torn, and resolved by the NEXT
        observation of the same rule - torn if that one matches, wrong if not (or if
        the run ends first)."""
        r = self._rule(rule)
        pend = self._pending.pop(rule, None)
        if pend is not None:
            if ok:
                r[2] += 1
                if len(self.torns[rule]) < self.first:
                    self.torns[rule].append(pend)
            else:
                self._wrong(rule, *pend)
        if ok:
            r[0] += 1
        elif torn_ok:
            self._pending[rule] = (key, detail)
        else:
            self._wrong(rule, key, detail)
        return ok

    def compare(self, rule, predicted, observed, key=None, torn_ok=False):
        """observe() with the detail filled in as (predicted, observed)."""
        return self.observe(rule, predicted == observed, key, (predicted, observed),
                            torn_ok)

    def model(self, rule, fn, observed, key=None):
        """Call a model; an Unread it raises is a WRONG with its message, never a
        skip."""
        try:
            predicted = fn()
        except Unread as e:
            self._wrong(rule, key, "UNREAD: %s" % e)
            return False
        return self.compare(rule, predicted, observed, key)

    def exclude(self, reason, n=1):
        if not reason or not str(reason).strip():
            raise ValueError("an exclusion needs a named cause")
        self.excluded[reason] += n

    def cover(self, path, n=1):
        self.covered[path] += n

    def require(self, path, n=1):
        """Fail unless cover(path) was counted at least n times."""
        self.required[path] = n

    # --- the verdict ----------------------------------------------------------------
    def _settle(self):
        for rule, pend in list(self._pending.items()):
            self._wrong(rule, *pend)        # torn but never followed by a match
        self._pending.clear()

    def problems(self):
        self._settle()
        out = []
        for rule, (m, w, t) in self.rules.items():
            if w:
                out.append("%s: %d wrong" % (rule, w))
            if m + w + t == 0:
                out.append("%s: no samples - a check that ran over nothing" % rule)
        if not self.rules:
            out.append("no rule was scored at all")
        for path, n in self.required.items():
            if self.covered[path] < n:
                out.append("never covered: %s (%d of %d)" % (path, self.covered[path], n))
        return out

    @property
    def passed(self):
        return not self.problems()

    def report(self, out=sys.stdout):
        probs = self.problems()
        p = lambda s="": print(s, file=out)
        p(self.title)
        width = max([len(k) for k in self.rules] + [10])
        for rule, (m, w, t) in self.rules.items():
            n = m + w + t
            extra = ("  (%d torn, each followed by a match)" % t) if t else ""
            p("  %-*s %7d of %7d match%s" % (width, rule, m, n, extra))
        if self.excluded:
            p("EXCLUDED, named and counted:")
            for k, v in sorted(self.excluded.items()):
                p("  %-*s %7d" % (width, k, v))
        if self.required or self.covered:
            p("COVERAGE:")
            for path in sorted(set(self.covered) | set(self.required)):
                need = self.required.get(path)
                p("  %-*s %7d%s" % (width, path, self.covered[path],
                                    "  (need %d)" % need if need else ""))
        for rule, rows in self.wrongs.items():
            for key, detail in rows:
                p("  WRONG %s  %s  %s" % (rule, key, detail))
        for rule, rows in self.torns.items():
            for key, detail in rows[:4]:
                p("  torn  %s  %s  %s" % (rule, key, detail))
        p("PASS" if not probs else
          "FAIL -- a residual you cannot explain is a defect you have not found yet")
        for s in probs:
            p("  " + s)
        return not probs

    def finish(self, out=sys.stdout):
        """Print the report; return the process exit code (0 pass, 1 fail)."""
        return 0 if self.report(out) else 1
