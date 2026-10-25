"""
check_decisions.py -- a port's docs/decisions.md table holds together.

    python -m beeb_port_kit.check_decisions docs/decisions.md          report; exit 1 on a problem
    python -m beeb_port_kit.check_decisions docs/decisions.md --fix    repair what it safely can

From 1942-beeb's `tools/check_decisions.py` (https://github.com/kieranhj/1942-beeb), made generic:
the file is an argument, the column count is read off the header row instead of being written in,
and a `Status` column, when the table has one, is checked against the lifecycle in the template's
`docs/decisions.md` (OPEN / PROPOSED / TAKEN / AGREED / SUPERSEDED by N / REJECTED).
Fork this into your project's tools/; keep this header.

`docs/decisions.md` is THE ONLY COPY of every deviation and every choice the hardware forced, and
it is a hand-kept Markdown table, so it rots the way hand-kept things do - silently, and only in
the RENDERING. The three faults 1942's table had on 2026-09-14, all invisible in the source:

  A BLANK LINE BETWEEN TWO ROWS ENDS THE TABLE. Markdown cannot resume it, so every row after the
    blank renders as a header-less table or as plain text. Six had crept in between decisions 32
    and 57: two thirds of the file was not rendering as a table at all.
  A ROW WITHOUT A TRAILING PIPE loses its last column. Three rows.
  A ROW WITH MORE PIPES THAN THE HEADER spills into columns that do not exist. One row had seven
    cells against the header's five - an unescaped `|` in the text.

None of that shows when you read the source, which is why it went unnoticed for a week and why
this is a tool rather than a note. The status check is new in the kit: 1942 had no Status column,
so its statuses lived in the Date cell ("ANSWERED 2026-09-17", "REVISED ...") and in essays inside
the Decision cell, and about 30 of its 161 rows were superseded or reversed without the table
saying so where a reader looks first.

The main table is the first one whose header starts `| # |`, and runs to the next `## ` heading
(a `## Rejected, do not re-litigate` table below it is a different shape and is not checked).
"""
import argparse
import re
import sys

HEADER = "| # |"

# The lifecycle. A status cell must START with one of these words (bold or not); anything after
# it - a date, who answered, a pointer - is free text. SUPERSEDED must name the row that replaced it.
STATUSES = ("OPEN", "PROPOSED", "TAKEN", "AGREED", "SUPERSEDED", "REJECTED")


def table(lines):
    """(header line, one past the last line) of the main table, or None if there is none."""
    try:
        hdr = next(i for i, l in enumerate(lines) if l.startswith(HEADER))
    except StopIteration:
        return None
    end = next((i for i in range(hdr + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return hdr, end


def cells(line):
    """The cells of a row, stripped. `\\|` is an escaped pipe and does not split."""
    parts = re.split(r"(?<!\\)\|", line)
    return [c.strip() for c in parts[1:-1]]


def columns(lines):
    """The header's column names, from the table's first line."""
    t = table(lines)
    return cells(lines[t[0]]) if t else []


def _status_problem(text, numbers):
    s = text.replace("*", "").strip()
    word = s.split(" ", 1)[0].rstrip(".,:;-").upper() if s else ""
    if word not in STATUSES:
        return "status %r is not one of %s" % (text, " / ".join(STATUSES))
    if word == "SUPERSEDED":
        m = re.match(r"SUPERSEDED\s+by\s+(\d+)", s, re.I)
        if not m:
            return "SUPERSEDED without 'by N' - say which row replaced it"
        if int(m.group(1)) not in numbers:
            return "SUPERSEDED by %s, which is not a row in the table" % m.group(1)
    return None


def check(lines):
    """A list of problems (strings, empty if the table holds) and the decision numbers found."""
    t = table(lines)
    if t is None:
        return ["no table whose header starts %r" % HEADER], []
    hdr, end = t
    names = cells(lines[hdr])
    cols = len(names)
    status_col = next((k for k, n in enumerate(names) if n.lower() == "status"), None)
    bad, nums, statuses = [], [], []
    for i in range(hdr, end):
        l = lines[i]
        if not l.strip():
            # blank lines after the last row, before the next heading, are correct
            if any(lines[j].strip() for j in range(i + 1, end)):
                bad.append("line %d: a BLANK LINE between rows ends the table; "
                           "every row below it stops being one" % (i + 1))
            continue
        if not l.startswith("|"):
            bad.append("line %d: does not start with a pipe" % (i + 1))
            continue
        if not l.rstrip().endswith("|"):
            bad.append("line %d: NO TRAILING PIPE, so its last column is lost" % (i + 1))
        c = cells(l if l.rstrip().endswith("|") else l.rstrip() + " |")
        if len(c) != cols:
            bad.append("line %d: %d cells against the header's %d%s"
                       % (i + 1, len(c), cols,
                          " - an unescaped pipe in the text?" if len(c) > cols else ""))
        m = re.match(r"\|\s*(\d+)\s*\|", l)
        if m:
            nums.append(int(m.group(1)))
            if status_col is not None and len(c) == cols:
                statuses.append((i + 1, int(m.group(1)), c[status_col]))
    if nums:
        for k in sorted(set(range(1, max(nums) + 1)) - set(nums)):
            bad.append("decision %d is missing" % k)
        for k in sorted({x for x in nums if nums.count(x) > 1}):
            bad.append("decision %d appears more than once" % k)
    for line, n, s in statuses:
        p = _status_problem(s, set(nums))
        if p:
            bad.append("line %d (decision %d): %s" % (line, n, p))
    return bad, nums


def fix(lines):
    """Remove blank lines inside the table, add missing trailing pipes, and fold a row's surplus
    cells into its last column. Text is never changed, and the status is never guessed."""
    t = table(lines)
    if t is None:
        return lines
    hdr, end = t
    cols = len(cells(lines[hdr]))
    out = []
    for i, l in enumerate(lines[hdr:end]):
        if not l.strip():
            continue
        if i >= 2 and l.startswith("|"):
            if not l.rstrip().endswith("|"):
                l = l.rstrip() + " |"
            parts = re.split(r"(?<!\\)\|", l)[1:-1]
            if len(parts) > cols:
                parts = parts[:cols - 1] + [
                    " " + " ".join(p.strip() for p in parts[cols - 1:]) + " "]
                l = "|" + "|".join(parts) + "|"
        out.append(l)
    tail = lines[end:]
    return lines[:hdr] + out + ([""] if tail else []) + tail


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check a port's decisions table renders and its "
                                             "statuses follow the lifecycle.")
    ap.add_argument("path", nargs="?", default="docs/decisions.md")
    ap.add_argument("--fix", action="store_true",
                    help="repair blank lines, trailing pipes and surplus cells (never statuses)")
    a = ap.parse_args(argv)
    with open(a.path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    if a.fix:
        lines = fix(lines)
        with open(a.path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines))
    bad, nums = check(lines)
    print("%s: %d decisions, numbered %d..%d" % (a.path, len(nums), min(nums), max(nums))
          if nums else "%s: no decisions found" % a.path)
    if bad:
        print("\n%d PROBLEM%s:" % (len(bad), "" if len(bad) == 1 else "S"))
        for b in bad:
            print("   " + b)
        print("\n`--fix` repairs the blank lines, the trailing pipes and the surplus cells; an "
              "unescaped pipe inside a cell it folds into the last column, so check the diff. "
              "A status it never touches: that is the owner's.")
        return 1
    print("the table holds: every row starts and ends with a pipe, has %d cells, no blank line "
          "splits it%s." % (len(columns(lines)),
                            ", and every status is in the lifecycle"
                            if any(n.lower() == "status" for n in columns(lines)) else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
