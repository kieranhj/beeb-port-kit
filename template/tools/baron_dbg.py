"""
baron_dbg.py - turn a Baron build into the ld65 debug file that beebgame's
static analyses read, so they run on a Baron port with no change to them.

beeb-port-kit: new 2026-10-06, for tools/dataflow (docs/dataflow.md).

WHY IT EXISTS. beebgame's tools/dataflow (Eben Upton, github.com/ebenupton/
beebgame) is liveness, constant and value-range analysis of a linked 6502
program, and it reads exactly one thing from the build: ld65's `--dbgfile`.
Everything else - the CFG, the summaries, the ranges, the findings - works on
the `model.Program` it builds from that file. So rather than fork the
analyses, this writes the file: a `game.dbg`, one image per SECTION and one
generated source file, and the upstream tools are pointed at them unmodified.

WHAT A BARON BUILD GIVES, AND WHAT IT DOES NOT.
  * The `-v` listing: the address, bytes and text of every emitted statement,
    macros expanded, and the SECTION each sits in. That says which bytes are
    instructions and which are data, which is what the analysis needs most.
  * The raw disc (`-o build/game-raw.ssd`): every saved SECTION's exact bytes,
    including the data the listing elides with "...".
  * The `--symbols` dump: every constant's resolved value.
  * NOT the source file and line of a listed statement. Baron prints the text
    and never the place. So this re-finds it: it walks the sources from the
    main file, follows INCLUDE and MACRO as the listing does, and matches each
    listed statement against the next statements of the file it is in. A
    statement it cannot place is still analysed - it is given only its own
    generated line - and the count is printed, so a bad match is visible.
  * NOT the references a symbol has. ld65 records them; the analysis uses them
    to find code whose address is taken (a dispatch table, an `lda #LO(x)`).
    This takes them from the text: a name on a statement is a reference to
    the label it resolves to through the `{ }` scopes. A name resolved to the
    wrong label errs towards "taken", which costs precision, never soundness.

HOW A STATEMENT IS DESCRIBED. ld65 gives each emitted span two lines: the
assembler-source line (type 0) and, inside a macro, the body line (type 2).
model.py classifies a span by its INNER line's text (a mnemonic, a `.byte`)
and reports it at its OUTER one. Here every emitted statement gets an inner
line in a generated file, `stmts.s`, holding just that statement in the
spelling model.py knows (`EQUB` becomes `.byte`, `EQUW` `.word`, and so on),
and its outer line is the real `file:line` - the macro call's, inside an
expansion. So a line of four `:`-separated instructions is four instructions,
and the reports and annotations point at the project's own sources.

Fork this into your project's tools/ with tools/analyse.py; keep this header.

FORKED into beeb-port-kit/template 2026-10-06, unchanged.
"""

import json
import os
import re
from pathlib import Path

try:                                                # the package
    from . import listing as _listing
    from . import dfs as _dfs
except ImportError:                                 # a fork in tools/
    import listing as _listing
    import dfs as _dfs

# ---- statements in the sources ---------------------------------------------

_IDENT = re.compile(r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*")
_SECTION = re.compile(r"^SECTION\s+([A-Za-z_][A-Za-z_0-9]*)(.*)$", re.I)
_FILENAME = re.compile(r"filename\s*=\s*\"([^\"]*)\"", re.I)
_INCLUDE = re.compile(r"^INCLUDE\s+\"([^\"]+)\"", re.I)
_MACRO = re.compile(r"^MACRO\s+([A-Za-z_][A-Za-z_0-9]*)\s*(.*)$", re.I)
_ENDMACRO = re.compile(r"^ENDMACRO\b", re.I)
_LEADING_LABEL = re.compile(r"^(\.[A-Za-z_][A-Za-z_0-9]*)\s+(\S.*)$")
_FOR = re.compile(r"^FOR\b", re.I)

# Baron's data directives, as model.py spells them. Anything else that emits
# bytes and is not an instruction is data too, and becomes `.byte`.
_DATA = {"equb": ".byte", "equs": ".byte", "equw": ".word", "equd": ".dword",
         "incbin": ".incbin"}


def _key(text):
    """What two spellings of one statement have in common."""
    return re.sub(r"\s+", "", text).lower()


def split_statements(line):
    """A source line's statements: the comment cut off (`\\` or `;` outside a
    string), split at `:` outside a string, and a leading `.label` split from
    the statement that follows it on the line."""
    out, cur, quote = [], [], None
    for ch in line:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            cur.append(ch)
        elif ch in "\\;":
            break
        elif ch == ":":
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    stmts = []
    for s in out:
        s = s.strip()
        if not s:
            continue
        m = _LEADING_LABEL.match(s)
        if m:
            stmts += [m.group(1), m.group(2).strip()]
        else:
            stmts.append(s)
    return stmts


def _args(text):
    """How many arguments a macro call passes (top-level commas)."""
    parts = text.split(None, 1)
    if len(parts) < 2:
        return 0
    depth, n, quote = 0, 1, None
    for ch in parts[1]:
        if quote:
            quote = None if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            n += 1
    return n


class SourceFile:
    """One source file as statements: `top` are the file's own, in order;
    each MACRO's body is kept apart under `macros`, since its statements are
    only ever listed inside an expansion."""

    def __init__(self, path, rel):
        self.path, self.rel = path, rel
        self.size = path.stat().st_size
        text = path.read_bytes().decode("latin-1")
        self.top, self.macros = [], []
        self.has_for = False
        body = None
        for n, raw in enumerate(text.split("\n"), 1):
            for s in split_statements(raw):
                if _FOR.match(s):
                    self.has_for = True
                m = _MACRO.match(s)
                if m and body is None:
                    params = [p for p in m.group(2).split(",") if p.strip()]
                    body = dict(name=m.group(1), nparams=len(params), stmts=[],
                                has_for=False, file=self)
                    self.macros.append(body)
                    continue
                if body is not None:
                    if _ENDMACRO.match(s):
                        body = None
                    else:
                        if _FOR.match(s):
                            body["has_for"] = True
                        body["stmts"].append((n, s, _key(s)))
                    continue
                self.top.append((n, s, _key(s)))


# ---- the conversion ------------------------------------------------------------

class Frame:
    """Where the walk is: a file's own statements, or a macro's body."""

    def __init__(self, stmts, has_for, file, macro=None, call=None, depth=0):
        self.stmts, self.has_for, self.file = stmts, has_for, file
        self.cursor = 0
        self.macro = macro          # the body, inside an expansion
        self.call = call            # the outermost call: (file, line, addr, seg)
        self.depth = depth          # macro nesting, 0 in a file
        self.end = None             # inside an expansion: the furthest byte emitted

    def find(self, key, back=False):
        n = len(self.stmts)
        for i in range(self.cursor, n):
            if self.stmts[i][2] == key:
                return i
        if back and self.has_for:
            for i in range(min(self.cursor, n) - 1, -1, -1):
                if self.stmts[i][2] == key:
                    return i
        return None


class Converter:
    def __init__(self, root, listing_path, symbols_path, disc_path=None, main=None):
        self.root = Path(root).resolve()
        self.lines = _listing.parse(listing_path)
        self.dump = json.loads(Path(symbols_path).read_text(encoding="utf-8"))
        self.disc = _dfs.read_image(disc_path).files if disc_path and \
            Path(disc_path).exists() else {}
        self.main = main or next(iter(self.dump))
        self.files = {}             # resolved path -> SourceFile
        self.macros = {}            # lower name -> [bodies]
        self.notes = []

    # ---- sources
    def source(self, path):
        path = path.resolve()
        if path not in self.files:
            rel = os.path.relpath(path, self.root).replace(os.sep, "/")
            f = SourceFile(path, rel)
            f.id = len(self.files)
            self.files[path] = f
            for m in f.macros:
                self.macros.setdefault(m["name"].lower(), []).append(m)
        return self.files[path]

    def macro_body(self, text):
        name = text.split(None, 1)[0].lower() if text.split() else ""
        bodies = self.macros.get(name)
        if not bodies:
            return None
        n = _args(text)
        for b in bodies:
            if b["nparams"] == n:
                return b
        return bodies[0]

    # ---- the walk
    def walk(self):
        main = self.source(self.root / self.main)
        stack = [Frame(main.top, main.has_for, main)]
        self.segs = []              # dict(name, filename, lo, hi, image)
        seg = None
        scope_ids, scope_next = [], [0]
        self.emits = []             # dict(seg, addr, size, text, kind, outer, depth, scope)
        self.calls = []             # dict(file, line, seg, lo, hi)
        self.labels = []            # dict(name, addr, seg, scope, parent)
        self.autos = []             # (name, addr)
        self.refs = []              # (name, scope chain, emit index or call index)
        unplaced = 0

        def close(frame):
            """An expansion ends: its outermost call covers what it emitted."""
            if frame.macro is None or frame.end is None:
                return
            if frame.depth == 1:
                f, n, a, s = frame.call
                self.calls.append(dict(file=f, line=n, seg=s, lo=a, hi=frame.end))
            else:
                outer = stack[-1]
                outer.end = frame.end if outer.end is None else max(outer.end, frame.end)

        for L in self.lines:
            t = L.text.strip()
            if L.addr is None:
                m = _SECTION.match(t)
                if m:
                    fn = _FILENAME.search(m.group(2))
                    seg = dict(name=m.group(1), filename=fn.group(1) if fn else None,
                               lo=None, hi=None, image={})
                    self.segs.append(seg)
                elif t.upper() == "ENDSECTION":
                    seg = None
                elif t == "{":
                    scope_next[0] += 1
                    scope_ids.append(scope_next[0])
                elif t == "}":
                    if scope_ids:
                        scope_ids.pop()
                else:
                    a = _listing._AUTO.match(t)
                    if a:
                        self.autos.append((a.group(1), int(a.group(2), 16)))
                continue
            if not t:
                continue
            # place the statement: the innermost frame that has it next
            key = _key(t)
            place = None
            for d in range(len(stack) - 1, -1, -1):
                i = stack[d].find(key)
                if i is not None:
                    place = (d, i)
                    break
            if place is None:
                i = stack[-1].find(key, back=True)
                if i is not None:
                    place = (len(stack) - 1, i)
            if place is not None:
                d, i = place
                while len(stack) - 1 > d:
                    close(stack.pop())
                fr = stack[-1]
                fr.cursor = i + 1
                where = (fr.file, fr.stmts[i][0]) if fr.macro is None else None
            else:
                fr = stack[-1]
                where = None
                if L.data:
                    unplaced += 1
            outer = where if fr.macro is None else None
            call = fr.call
            if seg is not None:
                seg["lo"] = L.addr if seg["lo"] is None else min(seg["lo"], L.addr)
                seg["hi"] = L.addr if seg["hi"] is None else max(seg["hi"], L.addr)
            # what it is
            lab = _listing._LABEL.match(t)
            if lab:
                self.labels.append(dict(name=lab.group(1), addr=L.addr,
                                        seg=len(self.segs) - 1 if seg is not None else None,
                                        scope=list(scope_ids),
                                        nested=bool(scope_ids) or fr.macro is not None))
                continue
            if L.data:
                if seg is None:
                    self.notes.append("listing line %d emits outside any SECTION" % L.n)
                    continue
                for k, b in enumerate(L.data):
                    seg["image"][L.addr + k] = b
                kind = "insn" if L.is_instruction and len(L.data) <= 3 else "data"
                e = dict(seg=len(self.segs) - 1, addr=L.addr, size=len(L.data),
                         elided=L.elided, text=t, kind=kind, outer=outer,
                         depth=fr.depth, n=L.n)
                self.emits.append(e)
                self.refs.append((t, list(scope_ids), ("emit", len(self.emits) - 1)))
                end = L.addr + len(L.data)
                if fr.macro is not None:
                    fr.end = end if fr.end is None else max(fr.end, end)
                continue
            m = _INCLUDE.match(t)
            if m and place is not None:
                base = fr.file.path.parent
                p = (base / m.group(1))
                if p.exists():
                    f = self.source(p)
                    stack.append(Frame(f.top, f.has_for, f))
                else:
                    self.notes.append("INCLUDE %s: not found from %s" % (m.group(1), fr.file.rel))
                continue
            body = self.macro_body(t)
            if body is not None and place is not None:
                if fr.macro is None:
                    call = (fr.file, where[1], L.addr, len(self.segs) - 1 if seg else None)
                    self.refs.append((t, list(scope_ids), ("call", call)))
                stack.append(Frame(body["stmts"], body["has_for"], body["file"],
                                   macro=body, call=call, depth=fr.depth + 1))
        while len(stack) > 1:
            close(stack.pop())
        self.unplaced = unplaced

    # ---- the segments' bytes
    def images(self):
        for s in self.segs:
            if s["lo"] is None:
                continue
            f = self.disc.get(s["filename"]) if s["filename"] else None
            lo = s["lo"]
            if f is not None and (f.load & 0xFFFF) != lo:
                self.notes.append("SECTION %s: disc file %s loads at &%04X, listing starts &%04X"
                                  % (s["name"], s["filename"], f.load & 0xFFFF, lo))
            if f is not None:
                data = bytearray(f.data)
            else:
                hi = max(s["image"]) + 1 if s["image"] else lo
                data = bytearray(hi - lo)
                if any(e["elided"] for e in self.emits if self.segs[e["seg"]] is s):
                    self.notes.append("SECTION %s: not on the disc, and the listing elides "
                                      "some of its data (zeros there)" % s["name"])
            for a, b in s["image"].items():
                o = a - lo
                if f is None:
                    data[o] = b
                elif 0 <= o < len(data) and data[o] != b:
                    self.notes.append("SECTION %s: listing and disc differ at &%04X"
                                      % (s["name"], a))
                    break
            s["data"] = bytes(data)
        # an elided line's size: up to the next address in its section
        by_seg = {}
        for e in self.emits:
            by_seg.setdefault(e["seg"], []).append(e)
        for si, es in by_seg.items():
            s = self.segs[si]
            addrs = sorted({L.addr for L in self.lines if L.addr is not None})
            end = s["lo"] + len(s["data"])
            for e in es:
                if not e["elided"]:
                    continue
                nxt = [a for a in addrs if a > e["addr"]]
                stop = min([a for a in nxt if a <= end] or [end])
                e["size"] = max(e["size"], stop - e["addr"])

    # ---- symbols and their references
    def symbols(self):
        syms, labels_by_name = [], {}
        for k, l in enumerate(self.labels):
            labels_by_name.setdefault(l["name"], []).append(k)
        # the dump's top-level constants (a scoped name is a label, listed above)
        consts = {}
        for fsyms in self.dump.values():
            for name, v in fsyms.items():
                if name.startswith("@") or isinstance(v, bool) or not isinstance(v, int):
                    continue
                if 0 <= v <= 0xFFFF:
                    consts.setdefault(name, v)
        qualified = {}
        for fsyms in self.dump.values():
            for name, v in fsyms.items():
                leaf = _listing._SCOPE.sub("", name)
                if "." in leaf and isinstance(v, int) and not isinstance(v, bool):
                    qualified[leaf] = v

        def resolve(name, chain):
            if "." in name and name in qualified:
                leaf = name.rsplit(".", 1)[1]
                return [k for k in labels_by_name.get(leaf, [])
                        if self.labels[k]["addr"] == qualified[name]]
            ks = labels_by_name.get(name)
            if not ks:
                return []
            for sc in reversed(chain):
                hit = [k for k in ks if self.labels[k]["scope"] and self.labels[k]["scope"][-1] == sc]
                if hit:
                    return hit[:1]
            return [k for k in ks if not self.labels[k]["scope"]][:1]

        label_refs, const_refs = {}, {}
        for text, chain, at in self.refs:
            body = text.split(None, 1)
            # a macro call's own name is not a reference
            words = _IDENT.findall(body[1] if at[0] == "call" and len(body) > 1 else text)
            for w in set(words):
                for k in resolve(w, chain):
                    label_refs.setdefault(k, []).append(at)
                if w in consts and w not in labels_by_name:
                    const_refs.setdefault(w, []).append(at)
        self.label_refs, self.const_refs, self.consts = label_refs, const_refs, consts

    # ---- the files
    def write(self, out):
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        self.walk()
        self.images()
        self.symbols()
        recs = []
        seg_ids = {}
        for k, s in enumerate(self.segs):
            if s.get("data") is None:
                continue
            fn = "seg_%s.bin" % s["name"]
            (out / fn).write_bytes(s["data"])
            seg_ids[k] = len(seg_ids)
            recs.append("seg\tid=%d,name=\"%s\",start=0x%06X,size=0x%04X,addrsize=absolute,"
                        "type=rw,oname=\"%s\",ooffs=0"
                        % (seg_ids[k], s["name"], s["lo"], len(s["data"]), fn))
        # the generated file of statements, one a line
        stmts = []
        for e in self.emits:
            tok = e["text"].split(None, 1)
            if e["kind"] == "insn":
                stmts.append(e["text"])
            else:
                rest = tok[1] if len(tok) > 1 else ""
                stmts.append("%s %s" % (_DATA.get(tok[0].lower(), ".byte"), rest))
        stmt_path = out / "stmts.s"
        stmt_path.write_bytes(("\n".join(s.replace(";", ",") for s in stmts) + "\n").encode("latin-1", "replace"))
        files = sorted(self.files.values(), key=lambda f: f.id)
        sid = len(files)
        for f in files:
            recs.append("file\tid=%d,name=\"%s\",size=%d,mtime=0x00000000,mod=0" % (f.id, f.rel, f.size))
        rel = os.path.relpath(stmt_path.resolve(), self.root).replace(os.sep, "/")
        recs.append("file\tid=%d,name=\"%s\",size=%d,mtime=0x00000000,mod=0"
                    % (sid, rel, stmt_path.stat().st_size))
        spans, lines = [], {}

        def span(seg, lo, size):
            spans.append("span\tid=%d,seg=%d,start=%d,size=%d"
                          % (len(spans), seg_ids[seg], lo - self.segs[seg]["lo"], size))
            return len(spans) - 1

        def line(fid, n, typ, count, sp):
            k = (fid, n, typ, count)
            if k not in lines:
                lines[k] = dict(id=len(lines), spans=[])
            if sp is not None:
                lines[k]["spans"].append(sp)
            return lines[k]["id"]

        emit_line, call_line = {}, {}
        for k, e in enumerate(self.emits):
            if e["seg"] not in seg_ids:
                continue
            sp = span(e["seg"], e["addr"], e["size"])
            emit_line[k] = line(sid, k + 1, 2, e["depth"], sp)
            if e["outer"] is not None:
                f, n = e["outer"]
                line(f.id, n, 0, 0, sp)
        for c in self.calls:
            if c["seg"] in seg_ids and c["hi"] > c["lo"]:
                sp = span(c["seg"], c["lo"], c["hi"] - c["lo"])
                call_line[(c["file"].id, c["line"], c["lo"])] = line(c["file"].id, c["line"], 0, 0, sp)

        def ref_line(at):
            if at[0] == "emit":
                return emit_line.get(at[1])
            f, n, a, s = at[1]
            return call_line.get((f.id, n, a))

        for (fid, n, typ, count), d in sorted(lines.items(), key=lambda kv: kv[1]["id"]):
            recs.append("line\tid=%d,file=%d,line=%d,type=%d,count=%d%s"
                        % (d["id"], fid, n, typ, count,
                           ",span=" + "+".join(map(str, d["spans"])) if d["spans"] else ""))
        recs += spans
        nsym = 0
        names = set()
        for k, l in enumerate(self.labels):
            if l["seg"] not in seg_ids:
                continue
            refs = sorted({r for r in (ref_line(a) for a in self.label_refs.get(k, [])) if r is not None})
            recs.append("sym\tid=%d,name=\"%s\",addrsize=absolute,%sval=0x%04X,seg=%d,type=lab%s"
                        % (nsym, l["name"], "parent=0," if l["nested"] else "", l["addr"],
                           seg_ids[l["seg"]], ",ref=" + "+".join(map(str, refs)) if refs else ""))
            nsym += 1
            names.add(l["name"])
        # Baron's allocator gives one zero-page byte to every variable whose
        # life it does not overlap, so a byte can be three variables: name it
        # by all of them ("fill_ptr/scroll/zxsrc") rather than let the
        # shortest win and mislabel the other two's code.
        at = {}
        for name, a in self.autos:
            at.setdefault(a, []).append(name)
            names.add(name)
        for a, ns in sorted(at.items()):
            recs.append("sym\tid=%d,name=\"%s\",addrsize=zeropage,val=0x%02X,type=lab"
                        % (nsym, "/".join(sorted(set(ns))), a))
            nsym += 1
        for name, v in sorted(self.consts.items()):
            # A constant under &100 is a count, a key number, a register
            # index far more often than a zero-page address, and the analysis
            # names memory by any symbol with the value: leave those out.
            if name in names or v < 0x100:
                continue
            refs = sorted({r for r in (ref_line(a) for a in self.const_refs.get(name, [])) if r is not None})
            recs.append("sym\tid=%d,name=\"%s\",addrsize=absolute,val=0x%04X,type=equ%s"
                        % (nsym, name, v, ",ref=" + "+".join(map(str, refs)) if refs else ""))
            nsym += 1
        (out / "game.dbg").write_text("version\tmajor=2,minor=0\n" + "\n".join(recs) + "\n",
                                      encoding="ascii", errors="replace")
        placed = sum(1 for e in self.emits if e["outer"] is not None or e["depth"])
        return dict(emits=len(self.emits), placed=placed, unplaced=self.unplaced,
                    files=len(files), segs=len(seg_ids), notes=self.notes)


def convert(root, listing, symbols, disc, out, main=None):
    """Write `out`/game.dbg, the section images and stmts.s; return a summary."""
    return Converter(root, listing, symbols, disc, main).write(out)


def _main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="a Baron build as an ld65 debug file")
    ap.add_argument("--root", default=".", help="the project root (Baron's working directory)")
    ap.add_argument("--listing", default="build/game.lst")
    ap.add_argument("--symbols", default="build/game.symbols.json")
    ap.add_argument("--disc", default="build/game-raw.ssd", help="Baron's own -o image")
    ap.add_argument("--main", default=None, help="the main source (default: the dump's first file)")
    ap.add_argument("--out", default="build/dataflow-in")
    a = ap.parse_args(argv)
    r = Path(a.root)
    s = convert(r, r / a.listing, r / a.symbols, r / a.disc, r / a.out, a.main)
    print("%d statements emitted, %d placed in the sources, %d not placed; %d files, %d sections"
          % (s["emits"], s["placed"], s["unplaced"], s["files"], s["segs"]))
    for n in s["notes"]:
        print("  note: " + n)


if __name__ == "__main__":
    import sys
    _main(sys.argv[1:])
