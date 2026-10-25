"""nmosify.py - a Master (65SC12) source made NMOS-clean with lib/nmos.6502's macros,
each site's form chosen from the dataflow annotation, and re-proved after every change.

    python tools/nmosify.py report          every 65SC12 instruction the annotated build reaches:
                                            the form chosen for each, and the ones left to do by hand
    python tools/nmosify.py report-all      the same, every site listed
    python tools/nmosify.py apply           the sources rewritten to the macros (MANUAL sites left)
    python tools/nmosify.py check           on a build WITHOUT NMOS: each macro site's form still allowed
    python tools/nmosify.py check --nmos    on a build WITH NMOS: what the forms newly read (a flag, a
                                            register known 0) as the NMOS code leaves it. Both are needed.

  --root DIR       the project (default: this file's ..)
  --annotated DIR  the annotation's copy of the sources (default build/annotated/src: what
                   `python tools/analyse.py annotate` writes)
  --src DIR        the sources it mirrors (default src); only `apply` reads or writes them
  --v-dead         take V as dead everywhere but where a BVC/BVS reads it straight after the
                   instruction that set it. The analysis keeps V live almost everywhere (few
                   instructions write it), so without this INC_A_ADC/CLC are rarely allowed. The
                   tool checks the claim first: every BVC, BVS, BRA_VS, BRA_VC and BVx_BIT6 must
                   follow a BIT, ADC, SBC, CLV, PLP or RTI on the line before, with no label
                   between (BVC_BIT6/BVS_BIT6 carry their own BIT), or it refuses.

The annotation is of ONE flag set's build: run it on the flag set the forms are for (a port
with B and Master builds: the build that will carry NMOS, assembled without it). A site that
build does not assemble has no annotation and is not seen; `check` counts macro sites with no
annotation as "not in this build". report and check read only the annotated copy (the source
text is in it, before `;|`), so they run on any project read-only; apply refuses a line whose
source no longer matches its annotation.

The forms (lib/nmos.6502 has the macros, their conditions and costs):

  STZ    a register known 0 there (STZ_A/X/Y: free), else one dead there, with N and Z, loaded
         with 0 (STZ_LDA/LDX/LDY: +2 bytes, +2 cycles; the register then serves the STZs straight
         after it)
  BRA    a branch on a flag known there (BRA_EQ .. BRA_VS: free), else JMP (BRA_JMP: +1 byte)
  INC A / DEC A   C known (0 for INC, 1 for DEC) and C, V dead after: ADC/SBC #1 (+1 byte);
         C and V dead: CLC/SEC first (+2 bytes, +2 cycles); else X or Y dead: TAX INX TXA (+2, +4)
  PHX/PHY/PLX/PLY  A dead after (and N, Z for a push): through A (+1 byte, +2 cycles)

Anything else (TSB, TRB, BIT #, BIT zp,X / abs,X, (zp), JMP (abs,X), and any 65SC12
instruction after a `:` on a line) is reported MANUAL and left alone: an `IF NMOS` block by
hand, or STZ_PHA / BVC_BIT6 / BVS_BIT6 with "(hand" in the line's comment once its callers are
read (check counts those, and does not judge them).

From Stryker's Run (tools/nmosify.py, 2026-10-24; its decision 73, docs/briefs/model-b-lite.md
step 1), into the kit 2026-10-25 with the paths made options, `;` comments and `:` lines
handled, report/check reading the annotation alone, and its V assumption (there: "measured
over the whole build, every BVC/BVS follows a BIT", hard-wired in check only) made --v-dead
and checked. There: 281 sites in the plain build, 232 by rule, 49 by hand; `check --nmos`
found two clashes between forms each safe alone (a CLC/ADC #1 before a BRA_CS; a BIT abs,X
rewritten as LDA/AND before a BRA chosen on V). Fork this into your project's tools/; keep this
header.
"""
import argparse
import collections
import os
import re
import sys

INS = re.compile(r'^(\s*)(STZ|BRA|INC\s+A\b|DEC\s+A\b|PHX|PHY|PLX|PLY|TSB|TRB|BIT|LDA|STA|ADC|SBC|AND|ORA|EOR|CMP|JMP)\b(.*)$', re.I)
CMOS_ANY = re.compile(r'^\s*(STZ|BRA|INC\s+A\b|DEC\s+A\b|PHX|PHY|PLX|PLY|TSB|TRB)\b', re.I)
BLOCK = ('IF', 'ELSE', 'ELIF', 'ENDIF', 'MACRO', 'ENDMACRO', 'FOR', 'NEXT', '{', '}')
COST = {'STZ_LDA': (2, 2), 'STZ_LDX': (2, 2), 'STZ_LDY': (2, 2), 'BRA_JMP': (1, 0),
        'INC_A_ADC': (1, 0), 'DEC_A_SBC': (1, 0), 'INC_A_CLC': (2, 2), 'DEC_A_SEC': (2, 2),
        'INC_A_X': (2, 4), 'DEC_A_X': (2, 4), 'INC_A_Y': (2, 4), 'DEC_A_Y': (2, 4),
        'PHX_A': (1, 2), 'PHY_A': (1, 2), 'PLX_A': (1, 2), 'PLY_A': (1, 2)}
BRA_FLAG = {'EQ': ('Z', '1'), 'NE': ('Z', '0'), 'CS': ('C', '1'), 'CC': ('C', '0'),
            'MI': ('N', '1'), 'PL': ('N', '0'), 'VS': ('V', '1'), 'VC': ('V', '0')}
MACROS = set(COST) | {'STZ_A', 'STZ_X', 'STZ_Y', 'STZ_PHA', 'BVC_BIT6', 'BVS_BIT6', 'BRA_JMP'} | \
    {'BRA_' + k for k in BRA_FLAG}
V_READERS = re.compile(r'^\s*(BVC|BVS|BRA_VS|BRA_VC)\b', re.I)
V_SETTERS = re.compile(r'^\s*(BIT|ADC|SBC|CLV|PLP|RTI)\b', re.I)

V_DEAD = False


def code_of(text):
    """The statement text of a source line: before any comment (\\ or ;), outside quotes."""
    out, q = [], None
    for ch in text:
        if q:
            if ch == q:
                q = None
        elif ch in '"\'':
            q = ch
        elif ch in '\\;':
            break
        out.append(ch)
    return ''.join(out).rstrip()


def state(ann):
    """(registers and flags known before the line, what is live after it), or None."""
    i = ann.find(';|')
    if i < 0:
        return None
    s = ann[i + 2:]
    regs = dict(re.findall(r'\b([AXYCZNV])=(\S+)', s.split('|')[0]))
    m = re.search(r'in:(\S+) out:(\S+)', s)
    out = set() if not m or m.group(2) == '-' else set(m.group(2))
    if V_DEAD:
        out.discard('V')
    return regs, out


def zero(v):
    return v is not None and re.match(r'\$00(?![0-9A-Fa-f.])', v) is not None


def operand(rest):
    code = code_of(rest).strip()
    if re.search(r',\s*X$', code, re.I):
        return code, 'X'
    if code.startswith('('):
        return code, 'ind'
    return code, ''


def is_cmos(mn, rest):
    code, mode = operand(rest)
    if mn in ('STZ', 'BRA', 'INC A', 'DEC A', 'PHX', 'PHY', 'PLX', 'PLY', 'TSB', 'TRB'):
        return True
    if mn == 'BIT':
        return code.startswith('#') or mode == 'X'
    if mn == 'JMP':
        return re.match(r'\(.*,\s*X\s*\)$', code, re.I) is not None
    return mode == 'ind' and not re.search(r'\)\s*,\s*Y$|,\s*X\s*\)$', code, re.I)


def choose(mn, rest, regs, out, run_zero):
    code, mode = operand(rest)
    if mn == 'STZ':
        if zero(regs.get('A')) or 'A' in run_zero:
            return 'STZ_A'
        if mode == '':
            if zero(regs.get('X')) or 'X' in run_zero:
                return 'STZ_X'
            if zero(regs.get('Y')) or 'Y' in run_zero:
                return 'STZ_Y'
        if {'N', 'Z'} & out:
            return None
        if 'A' not in out:
            return 'STZ_LDA'
        if mode == '' and 'X' not in out:
            return 'STZ_LDX'
        if mode == '' and 'Y' not in out:
            return 'STZ_LDY'
        return None
    if mn == 'BRA':
        for f, one, nought in (('Z', 'EQ', 'NE'), ('C', 'CS', 'CC'), ('N', 'MI', 'PL'), ('V', 'VS', 'VC')):
            if regs.get(f) == '1':
                return 'BRA_' + one
            if regs.get(f) == '0':
                return 'BRA_' + nought
        return 'BRA_JMP'
    if mn in ('INC A', 'DEC A'):
        inc = mn == 'INC A'
        cv_dead = not ({'C', 'V'} & out)
        if cv_dead and regs.get('C') == ('0' if inc else '1'):
            return 'INC_A_ADC' if inc else 'DEC_A_SBC'
        if cv_dead:
            return 'INC_A_CLC' if inc else 'DEC_A_SEC'
        if 'X' not in out:
            return 'INC_A_X' if inc else 'DEC_A_X'
        if 'Y' not in out:
            return 'INC_A_Y' if inc else 'DEC_A_Y'
        return None
    if mn in ('PHX', 'PHY'):
        return mn + '_A' if 'A' not in out and not ({'N', 'Z'} & out) else None
    if mn in ('PLX', 'PLY'):
        return mn + '_A' if 'A' not in out else None
    return None


def holds(form, regs, out, run_zero):
    """Whether a macro's NMOS form is right at a site, from the state before it (None: by hand)."""
    if form in ('STZ_A', 'STZ_X', 'STZ_Y'):
        r = form[-1]
        return zero(regs.get(r)) or r in run_zero
    if form in ('STZ_LDA', 'STZ_LDX', 'STZ_LDY'):
        return not ({'N', 'Z', form[-1]} & out)
    if form.startswith('BRA_'):
        if form == 'BRA_JMP':
            return True
        f, v = BRA_FLAG[form[4:]]
        return regs.get(f) == v
    if form in ('INC_A_ADC', 'DEC_A_SBC'):
        return not ({'C', 'V'} & out) and regs.get('C') == ('0' if form == 'INC_A_ADC' else '1')
    if form in ('INC_A_CLC', 'DEC_A_SEC'):
        return not ({'C', 'V'} & out)
    if form in ('INC_A_X', 'DEC_A_X', 'INC_A_Y', 'DEC_A_Y'):
        return form[-1] not in out
    if form in ('PHX_A', 'PHY_A'):
        return not ({'A', 'N', 'Z'} & out)
    if form in ('PLX_A', 'PLY_A'):
        return 'A' not in out
    return None         # STZ_PHA, BVC_BIT6, BVS_BIT6: checked by hand only


class Project:
    def __init__(self, root, annotated, src):
        self.root, self.ann, self.src = root, annotated, src

    def files(self):
        """(relative path, annotated lines): the annotated files end their lines \\r\\r\\n, so
        they are read raw and split on \\n."""
        for dirpath, _, names in sorted(os.walk(self.ann)):
            for f in sorted(names):
                if f.endswith('.6502') or f.endswith('.asm') or f.endswith('.s'):
                    p = os.path.join(dirpath, f)
                    rel = os.path.relpath(p, self.ann).replace('\\', '/')
                    text = open(p, encoding='utf-8', newline='').read()
                    yield rel, [l.rstrip('\r') for l in text.split('\n')]

    def show(self, rel):
        return os.path.relpath(os.path.join(self.src, rel), self.root).replace('\\', '/')


def source_text(al):
    return al.split(';|')[0].rstrip()


class NmosBlocks:
    """Which lines are the 65SC12 half of a hand-written IF NMOS block: the ELSE of `IF NMOS`,
    the body of `IF NMOS = 0` / `IF NOT(NMOS)` (and ELIF/ELSE nesting followed)."""
    def __init__(self):
        self.stack = []         # per open IF: is its current branch the 65SC12 half?

    def feed(self, code):
        u = code.upper()
        w = u.split()[0] if u else ''
        if w in ('IF', 'ELIF'):
            c = u[len(w):].strip()
            if re.fullmatch(r'\(?\s*NMOS\s*\)?', c):
                b = ['nmos', False]
            elif re.fullmatch(r'\(?\s*(NMOS\s*=\s*0|NOT\s*\(?\s*NMOS\s*\)?)\s*\)?', c):
                b = ['cmos', True]
            else:
                b = [None, False]
            if w == 'IF':
                self.stack.append(b)
            elif self.stack:
                self.stack[-1] = b
        elif w == 'ELSE' and self.stack:
            self.stack[-1][1] = self.stack[-1][0] == 'nmos'
        elif w == 'ENDIF' and self.stack:
            self.stack.pop()

    def cmos_half(self):
        return any(b for _, b in self.stack)


def sites(pr):
    for rel, a_lines in pr.files():
        run_zero = set()        # registers an STZ_LD? just zeroed, for the STZs straight after
        blocks = NmosBlocks()
        for n, al in enumerate(a_lines, 1):
            sl = source_text(al)
            code = code_of(sl).strip()
            blocks.feed(code)
            st = state(al)
            if st is None:
                if code.startswith('.') or code.upper().startswith(BLOCK):
                    run_zero = set()
                continue
            stmts = [s for s in code.split(':')] if ':' in code else [code]
            m = INS.match(stmts[0])
            mn = re.sub(r'\s+', ' ', m.group(2).upper()) if m else None
            later = [s for s in stmts[1:] if CMOS_ANY.match(s) or (INS.match(s) and is_cmos(
                re.sub(r'\s+', ' ', INS.match(s).group(2).upper()), INS.match(s).group(3)))]
            first = bool(m) and is_cmos(mn, m.group(3))
            if not first and not later:
                run_zero = set()
                continue
            regs, out = st
            if blocks.cmos_half():
                form = 'IF NMOS'        # done by hand already: the NMOS half is its ELSE
            else:
                form = None if later or len(stmts) > 1 else choose(mn, m.group(3), regs, out, run_zero)
            yield rel, n, sl, (mn if first else 'after :'), form, regs, out
            if mn != 'STZ' or form in (None, 'IF NMOS'):
                run_zero = set()
            elif form.startswith('STZ_LD'):
                run_zero.add(form[-1])


def check_v(pr):
    """--v-dead's claim, checked: every reader of V straight after an instruction that sets it."""
    bad = []
    for rel, a_lines in pr.files():
        prev = ''
        for n, al in enumerate(a_lines, 1):
            code = code_of(source_text(al)).strip()
            if code.startswith('.'):
                prev = ''               # a label: other paths may enter here
                continue
            if not code or code.upper().startswith(BLOCK) or state(al) is None:
                continue
            if V_READERS.match(code) and not V_SETTERS.match(prev):
                bad.append(f"{pr.show(rel)}:{n}: {code[:60]}   (after: {prev[:40] or '-'})")
            prev = code.split(':')[-1].strip()
    return bad


MULTI = re.compile(r'^(STZ_LD[AXY]|STZ_PHA|INC_A_\w+|DEC_A_\w+|PH[XY]_A|PL[XY]_A|BV[CS]_BIT6)$')


def built_with_nmos(pr):
    """Was the annotated build assembled with NMOS? A macro whose NMOS form is several
    instructions is annotated with one state per instruction ([lda #$00] ... [sta ...]) only
    then. None if the build has no such macro."""
    for rel, a_lines in pr.files():
        for al in a_lines:
            code = code_of(source_text(al)).strip()
            if code and MULTI.match(code.split()[0]) and ';|' in al:
                return al.split(';|', 1)[1].count('] A=') > 1
    return None


def check(pr):
    """Every macro site in the annotated build (one without NMOS: each macro there is its
    65SC12 instruction, so the state before it is the analysis's): does its form still hold?
    A site whose line says (hand was checked by reading its callers, where the analysis cannot."""
    bad, hand, ok, unseen = [], 0, 0, 0
    for rel, a_lines in pr.files():
        run_zero = set()
        for n, al in enumerate(a_lines, 1):
            sl = source_text(al)
            code = code_of(sl).strip()
            word = code.split()[0] if code else ''
            st = state(al)
            if word not in MACROS:
                if code and (st is not None or code.startswith('.') or code.upper().startswith(BLOCK)):
                    run_zero = set()
                continue
            if st is None:
                unseen += 1         # not assembled in this build
                continue
            regs, out = st
            verdict = None if '(hand' in sl else holds(word, regs, out, run_zero)
            if verdict is None:
                hand += 1
            elif verdict:
                ok += 1
            else:
                bad.append(f"{pr.show(rel)}:{n}: {code[:60]}   [{' '.join(k + '=' + v for k, v in regs.items())} out:{''.join(sorted(out)) or '-'}]")
            if word.startswith('STZ_LD'):
                run_zero.add(word[-1])
            elif not word.startswith('STZ_'):
                run_zero = set()
    print(f"{ok} hold, {hand} checked by hand, {unseen} not in this build, {len(bad)} NO LONGER HOLD")
    for b in bad:
        print('  ' + b)
    return 1 if bad else 0


def check_nmos(pr):
    """The other half, on an NMOS build's annotation: what each NMOS form reads that its 65SC12
    instruction did not - a flag (BRA_xx's branch, INC_A_ADC/DEC_A_SBC's C) or a register known
    0 (STZ_A/X/Y) - as the NMOS code really leaves it, other NMOS forms included. The 65SC12
    analysis cannot see these: there the flag or register is not read, so may be anything."""
    bad, ok = [], 0
    for rel, a_lines in pr.files():
        for n, al in enumerate(a_lines, 1):
            code = code_of(source_text(al)).strip()
            word = code.split()[0] if code else ''
            st = state(al)
            if st is None or '(hand' in al:
                continue
            regs = st[0]
            if word.startswith('BRA_') and word != 'BRA_JMP':
                good = '| always |' in al
            elif word in ('STZ_A', 'STZ_X', 'STZ_Y'):
                good = zero(regs.get(word[-1]))
            elif word in ('INC_A_ADC', 'DEC_A_SBC'):
                good = regs.get('C') == ('0' if word == 'INC_A_ADC' else '1')
            else:
                continue
            if good:
                ok += 1
            else:
                bad.append(f"{pr.show(rel)}:{n}: {code[:60]}   [{' '.join(k + '=' + v for k, v in regs.items())}]")
    print(f"NMOS build: {ok} hold, {len(bad)} DO NOT")
    for b in bad:
        print('  ' + b)
    return 1 if bad else 0


def apply(pr, found):
    edits = collections.defaultdict(dict)
    for rel, n, sl, mn, form, regs, out in found:
        if form and form != 'IF NMOS':
            edits[rel][n] = (mn, form, sl)
    for rel, e in edits.items():
        path = os.path.join(pr.src, rel)
        text = open(path, encoding='utf-8', newline='').read()
        nl = '\r\n' if '\r\n' in text else '\n'
        lines = text.split(nl)
        for n, (mn, form, sl) in e.items():
            l = lines[n - 1]
            if l.rstrip() != sl:
                raise SystemExit(f"{pr.show(rel)}:{n}: the source no longer matches its annotation - annotate again")
            pat = re.compile(r'^(\s*)' + mn.replace(' ', r'\s+') + (r'(?=\s|$)' if mn.endswith(' A') else r'\b'), re.I)
            new = pat.sub(lambda m: m.group(1) + form, l, count=1)
            assert new != l, (rel, n, l)
            grow = len(new) - len(l)
            mm = re.search(r'\S( {%d,})[\\;]' % (grow + 1), new) if grow > 0 else None
            if mm:          # the comment keeps its column where the gap allows
                new = new[:mm.start(1)] + ' ' * (len(mm.group(1)) - grow) + new[mm.end(1):]
            lines[n - 1] = new
        open(path, 'w', encoding='utf-8', newline='').write(nl.join(lines))
    print(f"applied to {sum(len(e) for e in edits.values())} lines in {len(edits)} files")


def main(argv=None):
    global V_DEAD
    sys.stdout.reconfigure(encoding='utf-8')
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('what', nargs='?', default='report', choices=['report', 'report-all', 'apply', 'check'])
    ap.add_argument('--nmos', action='store_true', help='check: the NMOS build\'s half')
    ap.add_argument('--root', default=here)
    ap.add_argument('--annotated', default=os.path.join('build', 'annotated', 'src'))
    ap.add_argument('--src', default='src')
    ap.add_argument('--v-dead', action='store_true')
    a = ap.parse_args(argv)
    pr = Project(a.root, os.path.join(a.root, a.annotated), os.path.join(a.root, a.src))
    if not os.path.isdir(pr.ann):
        raise SystemExit(f"{pr.ann}: no annotation - run python tools/analyse.py annotate first")
    if a.v_dead:
        bad = check_v(pr)
        if bad:
            print(f"--v-dead refused: {len(bad)} V readers not straight after a V setter")
            for b in bad:
                print('  ' + b)
            return 2
        V_DEAD = True
    if a.what == 'check':
        nmos = built_with_nmos(pr)
        if nmos is not None and nmos != a.nmos:
            print("the annotation is of a build %s NMOS: check%s is the half for it"
                  % (("with", " --nmos") if nmos else ("without", "")))
            return 2
        return check_nmos(pr) if a.nmos else check(pr)
    found = list(sites(pr))
    forms = collections.Counter(s[4] or 'MANUAL' for s in found)
    nbytes = sum(COST.get(s[4], (0, 0))[0] for s in found)
    print(f"{len(found)} sites; NMOS forms add at most {nbytes} bytes")
    for k, v in sorted(forms.items()):
        print(f"  {k:10s} {v}")
    for rel, n, sl, mn, form, regs, out in found:
        if form is None or a.what == 'report-all':
            st = ' '.join(k + '=' + v for k, v in regs.items())
            print(f"  {form or 'MANUAL':10s} {pr.show(rel)}:{n}: {sl.strip()[:64]}   [{st} out:{''.join(sorted(out)) or '-'}]")
    if a.what == 'apply':
        apply(pr, found)
    return 0


if __name__ == '__main__':
    sys.exit(main())
