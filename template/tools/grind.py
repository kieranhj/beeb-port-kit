"""
grind.py - the bookkeeping and the gate of the micro-optimisation grind (the kit's
beeb-micro-grind skill). Nothing here decides what is better code: the evaluation workflow's
agents do that. This cuts the work up, keeps the record, and proves.

The method is Eben Upton's, from beebgame (github.com/ebenupton/beebgame, tools/dataflow/README.md,
"Using the annotations to shrink code: a suggested farm"; vendored in tools/dataflow/): annotated
windows, a reviewer then a skeptic, survivors applied a batch at a time behind an equivalence gate.

beeb-port-kit template, MIT, Kieran Connell 2026. From Stryker's Run's tools/grind.py
(2026-10-17 to 10-25), which ran three rounds over that game's hand-written 6502: 580 candidates
proposed, 256 kept by the gate, a pass's work 43,036 -> 31,869 cycles. Everything about the
project - its builds, its proofs, its protected code - is in tools/grind_config.py; this file
names no game.

    python tools/grind.py windows [--size 32] [--offset 0] [--profile PC.json ...] [--all]
        the annotated sources (tools/analyse.py annotate -> build/annotated/) cut into windows of
        SIZE consecutive instructions, each weighted by its measured cycles a pass (tools/pcprof.mjs
        --out files of the build the annotation read; phases in CFG.EXCLUDE_PHASES left out),
        hottest first. Windows already evaluated (LEDGER_DIR/seen.txt) are left out unless --all.
        Writes build/grind/windows.json and build/grind/w/<id>.txt
    python tools/grind.py add ROUND_DIR | RESULT.json
        a round into the ledger, LEDGER_DIR/ledger.jsonl: each candidate with its skeptics' votes,
        approved (two or more heard, fewer than half refuting), refuted or unreviewed; its
        windows into seen.txt
    python tools/grind.py todo ROUND_DIR [--windows W.json]
        what an interrupted evaluation still owes, as JSON for refute.workflow.js
    python tools/grind.py queue                  the approved candidates not yet tried, best first
    python tools/grind.py apply ID ... | revert ID ...
    python tools/grind.py gate [--quick] [--control REV]
        build the control (REV, default HEAD, in a git worktree; cached by commit) and the test
        (the working tree), run CFG.CHECKS, measure both (CFG.MEASURE): a JSON verdict on stdout
        It builds in the tree's own build/, so afterwards build/ holds the test's build (and after
        `run`, possibly a reverted candidate's): rebuild before anything else reads it
    python tools/grind.py run [--batch 4] [--max N] [--retry STATUS ...]
        the queue, serially: apply a batch, gate it, commit it if it passes, is no slower and gains
        something; else bisect it down to the candidates that fail; every outcome in the ledger.
        Refuses to run on main or master, or with uncommitted changes in the sources
    python tools/grind.py report                 LEDGER_DIR/README.md, from the ledger

Exit codes: 0 done (gate: the verdict's ok); 1 the gate failed; 2 usage or a broken setup.
GRIND_DIR moves build/grind, GRIND_LEDGER_DIR the ledger (a dry run that must not touch the
project's record); GRIND_TRAILER is appended to every commit `run` makes ("\\n" for newlines).
"""
import argparse, collections, hashlib, json, os, re, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import grind_config as CFG  # noqa: E402

GRIND = Path(os.environ.get('GRIND_DIR') or ROOT / 'build' / 'grind')
LEDGER_DIR = Path(os.environ.get('GRIND_LEDGER_DIR') or ROOT / getattr(CFG, 'LEDGER_DIR', 'docs/grind'))
LEDGER = LEDGER_DIR / 'ledger.jsonl'
SEEN = LEDGER_DIR / 'seen.txt'
ANNOTATED = ROOT / getattr(CFG, 'ANNOTATED', 'build/annotated')
DBG = ROOT / getattr(CFG, 'DBG', 'build/dataflow-in/game.dbg')
SOURCES = getattr(CFG, 'SOURCES', ('src/',))
EXCLUDE_PHASES = set(getattr(CFG, 'EXCLUDE_PHASES', ('wait',)))
BS = chr(92)


def rel(p):
    """A path for messages and the ledger: relative to ROOT if under it, forward slashes."""
    p = Path(p)
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


# ---------------------------------------------------------------- the ledger
def load():
    if not LEDGER.exists():
        return []
    return [json.loads(l) for l in LEDGER.read_text(encoding='utf-8').splitlines() if l.strip()]


def save(cands):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(''.join(json.dumps(c, ensure_ascii=False) + '\n' for c in cands), encoding='utf-8')


def find(cands, cid):
    for c in cands:
        if c['id'] == cid:
            return c
    sys.exit(f'no candidate {cid}')


# ---------------------------------------------------------------- windows
def lines_of(path):
    """A file's lines, whatever its line endings (the annotator writes CRLF in text mode on
    Windows, so its lines can end CR CR LF)."""
    t = Path(path).read_bytes().decode('utf-8').replace(chr(13), '')
    L = t.split(chr(10))
    while L and not L[-1].strip():          # trailing blank lines: the annotator adds one
        L.pop()
    return L


def code_of(line):
    """A line's code: everything before its first comment (';' or a backslash; the annotator's
    ';|' is a comment too)."""
    return re.split(r'[;\\]', line, maxsplit=1)[0].strip()


def breaks_run(line):
    """A source line that is not an instruction: does it end a run of instructions? Labels,
    comments, blank lines, braces, equates, ASSERTs and PRINTs do not; data, conditional assembly,
    sections, includes and macros do (a macro's body is not annotated as its call's lines)."""
    c = code_of(line)
    if not c or c.startswith('.') or c in ('{', '}') or re.match(r'^[A-Za-z_][\w.]*\s*=', c):
        return False
    if c.upper().startswith(('ASSERT', 'PRINT')):
        return False
    return True


def read_dbg():
    """(source, line) -> [(segment name, run address, size)] from the debug file tools/analyse.py
    wrote (tools/baron_dbg.py's, in ld65's format)."""
    if not DBG.exists():
        sys.exit(f'no {rel(DBG)}: run tools/analyse.py annotate on the build first')
    files, segs, spans, out = {}, {}, {}, {}
    recre = re.compile(r'(\w+)=("[^"]*"|[^,]*)')
    lines = []
    for l in DBG.read_text(encoding='utf-8').splitlines():
        kind, _, rest = l.partition('\t')
        f = {k: v.strip('"') for k, v in recre.findall(rest)}
        if kind == 'file':
            files[f['id']] = f['name'].replace(BS, '/')
        elif kind == 'seg':
            segs[f['id']] = (f['name'], int(f['start'], 16))
        elif kind == 'span':
            spans[f['id']] = (f['seg'], int(f['start']), int(f['size']))
        elif kind == 'line' and 'span' in f:
            lines.append(f)
    for f in lines:
        name = files.get(f['file'], '')
        p = Path(name)
        name = rel(p) if p.is_absolute() else name
        if not name.startswith(SOURCES):
            continue
        for sp in f['span'].split('+'):
            if sp in spans:
                seg, start, size = spans[sp]
                sname, sbase = segs[seg]
                out.setdefault((name, int(f['line'])), []).append((sname, sbase + start, size))
    return out


def heat_of(profiles):
    """address key (bank << 16 | addr in &8000-&BFFF, else addr) -> cycles a pass, phases in
    EXCLUDE_PHASES left out, averaged over the profiles (tools/pcprof.mjs --out)."""
    total = collections.Counter()
    for p in profiles:
        d = json.loads(Path(p).read_text())
        for k, v in d['pc'].items():
            phase, _, a = k.rpartition(':')
            if phase not in EXCLUDE_PHASES:
                total[int(a)] += v / d['passes'] / len(profiles)
    return total


def protected_lines():
    out = collections.defaultdict(dict)       # file -> {line: why}
    for p in getattr(CFG, 'PROTECT', ()):
        L = lines_of(ROOT / p['file'])
        try:
            s = next(i for i, l in enumerate(L) if code_of(l).split()[:1] == ['.' + p['frm']])
            e = next(i for i in range(s, len(L)) if p['to'] in code_of(L[i]))
        except StopIteration:
            sys.exit(f"grind_config PROTECT: .{p['frm']} ... {p['to']!r} not found in {p['file']}: the config is stale")
        for i in range(s, e + 1):
            out[p['file']][i + 1] = p['why']
    return out


def cmd_windows(a):
    dbg = read_dbg()
    heat = heat_of(a.profile) if a.profile else collections.Counter()
    if not a.profile:
        print('no --profile: every window weighs 0 (tools/pcprof.mjs --out makes one)', file=sys.stderr)
    prot = protected_lines()
    for (f, n), places in dbg.items():
        for seg, addr, size in places:
            for seg_p, lo, hi, why in getattr(CFG, 'PROTECT_BYTES', ()):
                if seg == seg_p and addr <= hi and addr + size - 1 >= lo:
                    prot[f][n] = why
    seen = set(SEEN.read_text().split()) if SEEN.exists() and not a.all else set()
    if not ANNOTATED.exists():
        sys.exit(f'no {rel(ANNOTATED)}: run tools/analyse.py annotate first')
    (GRIND / 'w').mkdir(parents=True, exist_ok=True)
    for old in (GRIND / 'w').glob('*.txt'):
        old.unlink()
    wins, skipped = [], collections.Counter()
    for ann in sorted(ANNOTATED.rglob('*.6502')):
        r = ann.relative_to(ANNOTATED).as_posix()
        if r in CFG.GENERATED:
            skipped['generated'] += 1
            continue
        A = lines_of(ann)
        S = lines_of(ROOT / r)
        if len(A) != len(S):
            sys.exit(f'{r}: the annotation has {len(A)} lines and the source {len(S)}: annotate again')
        runs, run = [], []
        for i, l in enumerate(A):
            if ';|' in l:
                run.append(i + 1)
            elif breaks_run(l) and run:
                runs.append(run)
                run = []
        if run:
            runs.append(run)

        def cyc(n):
            t = 0.0
            for seg, addr, size in dbg.get((r, n), ()):
                bank = CFG.SEGMENT_BANK.get(seg)
                t += heat.get((bank << 16 | addr) if bank is not None and 0x8000 <= addr < 0xC000 else addr, 0)
            return t
        for run in runs:
            starts = list(range(0, len(run), a.size))
            if a.offset and len(run) > a.size:
                starts = [0] + list(range(a.offset, len(run), a.size))
            for k, s in enumerate(starts):
                e = (starts[k + 1] if k + 1 < len(starts) else len(run)) - 1
                first, last = run[s], run[e]
                if all(n in prot[r] for n in run[s:e + 1]):
                    skipped['protected'] += 1
                    continue
                raw = '\n'.join(S[first - 1:last])
                wid = hashlib.sha1((r + '\n' + raw).encode()).hexdigest()[:12]
                if wid in seen:
                    skipped['seen'] += 1
                    continue
                h = sum(cyc(n) for n in run[s:e + 1])
                body = []
                for n in range(first, last + 1):
                    c = cyc(n)
                    mark = 'PROTECTED ' if n in prot[r] else ''
                    body.append(f"{n:5d} {'%8.1f' % c if c else ' ' * 8} {mark}{A[n - 1]}")
                why = sorted({prot[r][n] for n in range(first, last + 1) if n in prot[r]})
                head = [f"window {wid}: {r} lines {first}-{last}, {e - s + 1} instructions, "
                        f"{h:,.1f} cycles a pass measured ({'/'.join(sorted(EXCLUDE_PHASES)) or 'nothing'} excluded)"]
                head += [f"PROTECTED lines: {w}" for w in why]
                (GRIND / 'w' / f'{wid}.txt').write_text('\n'.join(head + [''] + body) + '\n', encoding='utf-8')
                wins.append(dict(id=wid, file=r, first=first, last=last, n=e - s + 1, heat=round(h, 1),
                                 path=rel(GRIND / 'w' / f'{wid}.txt')))
    wins.sort(key=lambda w: -w['heat'])
    (GRIND / 'windows.json').write_text(json.dumps(wins, indent=1))
    hot = [w for w in wins if w['heat'] > 0]
    tot = sum(w['heat'] for w in wins)
    print(f"{len(wins)} windows ({len(hot)} that ran in the profiles, {tot:,.0f} cycles a pass between them); "
          f"left out: {dict(skipped)} -> {rel(GRIND / 'windows.json')}")
    for frac in (0.5, 0.9, 0.99):
        if not tot:
            break
        acc, k = 0, 0
        for w in hot:
            acc += w['heat']
            k += 1
            if acc >= frac * tot:
                break
        print(f"  {int(frac * 100)}% of those cycles in the hottest {k} windows")


# ---------------------------------------------------------------- candidates
def from_dir(d):
    """A round as the evaluation workflow left it on disk: each optimiser's opt-<window>.json and
    each skeptic's skeptic-<window>-<i>-<lens>.json (i counts the optimiser's candidates)."""
    d = Path(d)
    rnd = int(re.sub(r'\D', '', d.name) or 0)
    cands, wins = [], set()
    for f in sorted(d.glob('opt-*.json')):
        got = json.loads(f.read_text(encoding='utf-8')).get('candidates', [])
        wins.add(f.stem[4:])
        for i, c in enumerate(got):
            wins.add(c.get('window', ''))
            c['skeptics'] = []
            for v in sorted(d.glob(f"skeptic-{c.get('window')}-{i}-*.json")):
                try:
                    vote = json.loads(v.read_text(encoding='utf-8'))
                except ValueError as e:     # an agent's hand-written JSON (a 6502 comment's backslash)
                    print(f"{v.name}: {e}; vote skipped (the workflow's own result has it)")
                    continue
                vote['lens'] = v.stem.rsplit('-', 1)[1]
                c['skeptics'].append(vote)
            cands.append(c)
    return dict(round=rnd, windows=sorted(w for w in wins if w), candidates=cands)


LENSES = ['semantics', 'machine', 'project']


def cmd_todo(a):
    """An interrupted evaluation's remainder: candidates short of skeptic files, windows with no
    optimiser file. The lens rule is the workflow's: three from THREE_SKEPTICS_FROM cycles a pass,
    else semantics and machine."""
    d = Path(a.dir)
    three = getattr(CFG, 'THREE_SKEPTICS_FROM', 5)
    items = []
    for f in sorted(d.glob('opt-*.json')):
        try:
            got = json.loads(f.read_text(encoding='utf-8')).get('candidates', [])
        except ValueError as e:
            print(f"{f.name}: {e}; skipped", file=sys.stderr)
            continue
        for i, c in enumerate(got):
            w = c.get('window')
            lenses = LENSES if (c.get('claim') or {}).get('cycles_a_pass', 0) >= three else LENSES[:2]
            missing = [x for x in lenses if not (d / f'skeptic-{w}-{i}-{x}.json').exists()]
            if missing:
                items.append(dict(window=w, i=i, file=c['file'], line=c['line'], lenses=missing,
                                  cycles_a_pass=(c.get('claim') or {}).get('cycles_a_pass', 0)))
    out = dict(round=int(re.sub(r'\D', '', d.name) or 0), items=items)
    if a.windows:
        have = {f.stem[4:] for f in d.glob('opt-*.json')}
        out['windows'] = [w for w in json.loads(Path(a.windows).read_text(encoding='utf-8')) if w['id'] not in have]
    print(json.dumps(out, separators=(',', ':')))


def cmd_add(a):
    p = Path(a.result)
    res = from_dir(p) if p.is_dir() else json.loads(p.read_text(encoding='utf-8'))
    cands = load()
    n = max([int(c['id'][1:]) for c in cands] or [0])
    have = {(c['file'], c['old'], c['new']) for c in cands}
    added = collections.Counter()
    for c in res.get('candidates', []):
        key = (c['file'], c['old'], c['new'])
        if key in have:
            added['duplicate'] += 1
            continue
        have.add(key)
        n += 1
        votes = c.get('skeptics', [])
        refuted = sum(1 for v in votes if v.get('refuted'))
        # approved only with at least two skeptics heard and fewer than half of them refuting
        status = 'unreviewed' if len(votes) < 2 else 'refuted' if refuted * 2 >= len(votes) else 'approved'
        c = dict(id=f'G{n:04d}', round=res.get('round'), status=status, **c)
        cands.append(c)
        added[c['status']] += 1
    save(cands)
    seen = set(SEEN.read_text().split()) if SEEN.exists() else set()
    seen |= set(res.get('windows', []))
    SEEN.write_text('\n'.join(sorted(seen)) + '\n')
    print(f"ledger: {dict(added)}; {len(cands)} candidates in all; {len(seen)} windows seen")


def score(c):
    cl = c.get('claim', {})
    return (cl.get('cycles_a_pass', 0), cl.get('bytes', 0))


def queue(cands):
    return sorted([c for c in cands if c['status'] == 'approved'], key=score, reverse=True)


def cmd_queue(a):
    q = queue(load())
    for c in q:
        cl = c.get('claim', {})
        print(f"{c['id']} {c['file']}:{c['line']} ~{cl.get('cycles_a_pass', 0):.1f} cycles a pass, "
              f"{cl.get('bytes', 0)} bytes  {c.get('summary', '')[:80]}")
    print(f"{len(q)} approved and untried", file=sys.stderr)


def _swap(c, old, new):
    p = ROOT / c['file']
    raw = p.read_bytes().decode('utf-8')
    nl = '\r\n' if '\r\n' in raw else '\n'
    o, n = old.replace('\r\n', '\n').replace('\n', nl), new.replace('\r\n', '\n').replace('\n', nl)
    hits = [m.start() for m in re.finditer(re.escape(o), raw)]
    if not hits:
        return False
    at = min(hits, key=lambda h: abs(raw.count(nl, 0, h) + 1 - c.get('line', 0)))   # the one nearest its line
    p.write_bytes((raw[:at] + n + raw[at + len(o):]).encode('utf-8'))
    return True


def apply(c):
    return _swap(c, c['old'], c['new'])


def revert(c):
    return _swap(c, c['new'], c['old'])


def cmd_apply(a, undo=False):
    cands = load()
    bad = 0
    for cid in a.ids:
        c = find(cands, cid)
        ok = revert(c) if undo else apply(c)
        bad += not ok
        print(f"{cid}: {'reverted' if undo else 'applied'}" if ok else f"{cid}: its text is not in {c['file']}")
    return 1 if bad else 0


# ---------------------------------------------------------------- building, proving, measuring
def sh(argv, cwd=ROOT, env=None, timeout=None, input=None):
    return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, input=input)


def build(where, kind):
    """One build of CFG.BUILDS in the project copy at `where`: (image path, '') or (None, why)."""
    b = CFG.BUILDS[kind]
    env = dict(os.environ)
    env.update({k: str(v) for k, v in CFG.build_env(ROOT).items()})
    t0 = time.time()
    if os.name == 'nt':
        r = sh(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command',
                '& .\\build.ps1 ' + ' '.join(b['ps'])], cwd=where, env=env)
    else:
        r = sh(['make'] + list(b['make']), cwd=where, env=env)
    out = Path(where) / b['image']
    if r.returncode or not out.exists() or out.stat().st_mtime < t0 - 2:
        return None, (r.stdout + r.stderr)[-2000:]
    return out, ''


def stash(src, dst):
    """The image and what the tools read beside it (symbols, listing) under a new name."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dst)
    for ext in ('.symbols.json', '.lst'):
        s = Path(str(src)[:-len(src.suffix)] + ext)
        if s.exists():
            shutil.copy(s, Path(str(dst)[:-len(dst.suffix)] + ext))
    return dst


def build_set(where, into):
    """Every build of CFG.BUILDS in `where`, the images kept in `into`; None if one fails."""
    imgs = {}
    for kind in CFG.BUILDS:
        out, err = build(where, kind)
        if not out:
            return None, f'{kind} does not assemble: {err}'
        imgs[kind] = stash(out, into / f'{kind}{out.suffix}')
    return imgs, ''


def last_json(text):
    for l in reversed(text.strip().splitlines()):
        l = l.strip()
        if l.startswith('{'):
            try:
                return json.loads(l)
            except ValueError:
                return None
    return None


def dig(d, path):
    for k in path.split('.'):
        d = d[k]
    return d


def measure(img):
    """CFG.MEASURE on one image: {name: number}. A tool that fails or prints no number stops the gate."""
    out = {}
    for name, argv, field in CFG.MEASURE:
        r = sh([x.replace('{img}', str(img)) for x in argv])
        d = last_json(r.stdout)
        try:
            out[name] = round(float(dig(d, field)), 1)
        except (TypeError, KeyError, ValueError):
            sys.exit(f'measure {name}: no {field} in its output (exit {r.returncode}): {r.stdout[-300:]}{r.stderr[-300:]}')
    return out


def git_top():
    return Path(sh(['git', 'rev-parse', '--show-toplevel']).stdout.strip())


def control(rev='HEAD'):
    """The control's images and measurement, built once per commit from a clean worktree."""
    head = sh(['git', 'rev-parse', '--short', rev]).stdout.strip()
    if not head:
        sys.exit(f'git: no commit {rev}')
    into = GRIND / f'ctl-{head}'
    done = into / 'done.json'
    if done.exists():
        return json.loads(done.read_text())
    top = git_top()
    sub = ROOT.relative_to(top) if ROOT != top else Path('.')
    wt = GRIND / 'wt'
    sh(['git', 'worktree', 'remove', '--force', str(wt)])
    r = sh(['git', 'worktree', 'add', '--force', '--detach', str(wt), head])
    if r.returncode:
        sys.exit('worktree: ' + r.stderr)
    try:
        imgs, err = build_set(wt / sub, into)
        if not imgs:
            sys.exit('the control does not build: ' + err)
    finally:
        sh(['git', 'worktree', 'remove', '--force', str(wt)])
        sh(['git', 'worktree', 'prune'])
    res = dict(commit=head, images={k: str(v) for k, v in imgs.items()}, work=measure(imgs[CFG.BENCH]))
    done.write_text(json.dumps(res, indent=1))
    return res


def judge(c, r):
    """A check's verdict: CFG's own judge if it gives one, else the kit's exit-code contract
    (0 pass, 1 wrong, 2 could not judge), with the last JSON line's gist as the reason."""
    if len(c) > 2 and callable(c[2]):
        return c[2](r.returncode, r.stdout)
    d = last_json(r.stdout)
    what = json.dumps(d)[:200] if d else (r.stdout + r.stderr).strip().splitlines()[-1:] or ['']
    return r.returncode == 0, (what if isinstance(what, str) else what[0][:200]) + f' (exit {r.returncode})'


def gate(quick=False, rev='HEAD'):
    ctl = control(rev)
    imgs, err = build_set(ROOT, GRIND / 'test')
    if not imgs:
        return dict(ok=False, why=err, control=ctl['commit'])
    I = {k: str(v) for k, v in imgs.items()}
    I.update({f'ctl_{k}': v for k, v in ctl['images'].items()})
    checks = [c for c in CFG.CHECKS if not quick or c[0] in CFG.QUICK]

    def run(c):
        name, argv = c[0], c[1]
        r = sh([x.format(**I) for x in argv])
        ok, what = judge(c, r)
        return name, ok, what
    with ThreadPoolExecutor(CFG.PARALLEL) as ex:
        res = list(ex.map(run, checks))
    ok = all(r[1] for r in res)
    out = dict(ok=ok, control=ctl['commit'], checks=[dict(name=n, ok=o, what=w) for n, o, w in res])
    if ok:
        work = measure(imgs[CFG.BENCH])
        out['work'] = work
        out['saved'] = {k: round(ctl['work'][k] - work[k], 1) for k in work}
    return out


def cmd_gate(a):
    v = gate(a.quick, a.control)
    print(json.dumps(v, indent=1))
    return 0 if v['ok'] else 1


# ---------------------------------------------------------------- the serial run
TRAILER = os.environ.get('GRIND_TRAILER', '').replace('\\n', '\n')


def log(msg):
    print(msg, flush=True)
    GRIND.mkdir(parents=True, exist_ok=True)
    with open(GRIND / 'run.log', 'a', encoding='utf-8') as f:
        f.write(msg + '\n')


def verdict(v):
    """A candidate that failed its gate alone, by cause (Stryker's Run's round 1: 7 of 13 'failed'
    were out of room, 3 clashed with a change kept before them, 1 of 11 'slower' gained nothing)."""
    why = v.get('why', '')
    if not v['ok']:
        if re.search(getattr(CFG, 'STALE', r'Duplicate symbol|Undefined symbol'), why):
            return 'stale'                  # a change kept before it took its label or its callee
        if re.search(getattr(CFG, 'NO_ROOM', r'overruns'), why):
            return 'no room'                # its region's ASSERT: worth trying again with more room
        return 'failed'
    if all(abs(s) <= CFG.NOISE for s in v['saved'].values()):
        return 'no gain'
    return 'slower'


def try_batch(cands, batch):
    """Apply `batch`, gate it; keep (commit) or bisect. Returns the candidates kept."""
    live = []
    for c in batch:
        if apply(c):
            live.append(c)
        else:
            c['status'] = 'stale'
            c['note'] = 'its text was no longer in the source when its turn came'
    save(cands)
    if not live:
        return []
    ids = ' '.join(c['id'] for c in live)
    log(f'gate: {ids}')
    v = gate()
    # kept if every check passes, no measurement is slower, and something is gained: cycles, or
    # bytes claimed (the build's ASSERTs and the checks have held, so they are real). Identical code
    # measures within NOISE of its control.
    gain = v['ok'] and (any(s > CFG.NOISE for s in v['saved'].values())
                        or any(c.get('claim', {}).get('bytes', 0) > 0 for c in live))
    if v['ok'] and gain and all(s >= -CFG.NOISE for s in v['saved'].values()):
        for c in live:
            c['status'] = 'accepted'
            c['measured'] = dict(batch=ids, saved=v['saved'])
        save(cands)
        msg = (f"Grind: {ids}: " + ', '.join(f'{k} {s:+.1f}' for k, s in v['saved'].items()) + " cycles a pass saved\n\n"
               + '\n'.join(f"{c['id']} {c['file']}:{c['line']}: {c.get('summary', '')}" for c in live)
               + f"\n\nGated by tools/grind.py against {v['control']}: " + '; '.join(f"{x['name']} ok" for x in v['checks'])
               + f"\nMeasured: {v['work']}\n" + (f"\n{TRAILER}\n" if TRAILER else ''))
        sh(['git', 'add', '-A', *SOURCES, str(LEDGER)])
        r = sh(['git', 'commit', '-q', '-F', '-'], input=msg)
        log(f"  kept {ids}: saved {v['saved']} ({r.stdout.strip() or 'committed'})")
        return live
    for c in live:
        revert(c)
    if len(live) == 1:
        c = live[0]
        c['status'] = verdict(v)
        c['gate'] = v
        save(cands)
        log(f"  {c['id']}: {c['status']}: " + ('; '.join(f"{x['name']}: {x['what']}" for x in v.get('checks', []) if not x['ok'])
                                              or v.get('why', '') or str(v.get('saved'))))
        return []
    log(f"  batch {ids} {'failed' if not v['ok'] else 'not faster'}: bisecting")
    h = len(live) // 2
    return try_batch(cands, live[:h]) + try_batch(cands, live[h:])


def cmd_run(a):
    if sh(['git', 'branch', '--show-current']).stdout.strip() in ('main', 'master'):
        sys.exit('grind.py run commits as it goes: run it on a branch (git checkout -b grind-<date>)')
    if sh(['git', 'status', '--porcelain', *SOURCES]).stdout.strip():
        sys.exit('the sources have uncommitted changes: commit or stash them first')
    GRIND.mkdir(parents=True, exist_ok=True)
    if a.retry:                             # e.g. --retry 'no room' once a region has grown
        cands = load()
        for c in cands:
            if c['status'] in a.retry:
                c['note'] = f"was {c['status']}; retried"
                c['status'] = 'approved'
        save(cands)
    done = 0
    while a.max is None or done < a.max:
        cands = load()
        q = queue(cands)
        if not q:
            log('the queue is empty')
            break
        batch, used = [], set()
        for c in q:                         # one candidate per file region at a time
            span = (c['file'], c.get('line', 0) // 40)
            if span in used:
                continue
            used.add(span)
            batch.append(c)
            if len(batch) >= a.batch:
                break
        try_batch(cands, batch)
        done += len(batch)
    cmd_report(a)


# ---------------------------------------------------------------- the record
def cmd_report(a):
    cands = load()
    by = collections.Counter(c['status'] for c in cands)
    acc = [c for c in cands if c['status'] == 'accepted']
    lines = ['# The micro-optimisation grind', '',
             'GENERATED by `tools/grind.py report` from `ledger.jsonl`; the method is the kit\'s',
             'beeb-micro-grind skill. Every candidate an optimiser proposed, what its skeptics said, and',
             'what the gate found. Savings are the gate\'s measurements (`tools/grind_config.py` MEASURE),',
             'per batch against its control, in cycles a pass. Never add up the claimed column.', '',
             f"Candidates: {len(cands)} - " + ', '.join(f'{k} {v}' for k, v in sorted(by.items())), '',
             '| Id | Where | Status | Claimed | Measured (batch) | What |', '|---|---|---|---|---|---|']
    for c in cands:
        cl = c.get('claim', {})
        m = c.get('measured', {}).get('saved', '')
        lines.append(f"| {c['id']} | `{c['file']}:{c.get('line', '')}` | {c['status']} | "
                     f"{cl.get('cycles_a_pass', 0):.1f} cyc/pass, {cl.get('bytes', 0)} B | {m} | {c.get('summary', '').replace('|', '/')} |")
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    (LEDGER_DIR / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f"{rel(LEDGER_DIR / 'README.md')}: {len(cands)} candidates, {len(acc)} accepted")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest='cmd', required=True)
    w = s.add_parser('windows')
    w.add_argument('--size', type=int, default=32)
    w.add_argument('--offset', type=int, default=0)
    w.add_argument('--profile', nargs='*', default=[])
    w.add_argument('--all', action='store_true')
    s.add_parser('add').add_argument('result')
    t = s.add_parser('todo')
    t.add_argument('dir')
    t.add_argument('--windows')
    s.add_parser('queue')
    s.add_parser('apply').add_argument('ids', nargs='+')
    s.add_parser('revert').add_argument('ids', nargs='+')
    g = s.add_parser('gate')
    g.add_argument('--quick', action='store_true')
    g.add_argument('--control', default='HEAD', help='the commit to prove against (e.g. HEAD^1 for a merge)')
    r = s.add_parser('run')
    r.add_argument('--batch', type=int, default=4)
    r.add_argument('--max', type=int)
    r.add_argument('--retry', nargs='*', default=[], help="statuses to queue again, e.g. 'no room'")
    s.add_parser('report')
    a = p.parse_args()
    rc = {'windows': cmd_windows, 'add': cmd_add, 'todo': cmd_todo, 'queue': cmd_queue, 'apply': cmd_apply,
          'revert': lambda a: cmd_apply(a, True), 'gate': cmd_gate, 'run': cmd_run, 'report': cmd_report}[a.cmd](a)
    sys.exit(rc or 0)


if __name__ == '__main__':
    main()
