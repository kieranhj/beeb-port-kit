import os
import tempfile
import unittest

from tests import paths  # noqa: F401
from beeb_port_kit.mame import records
from beeb_port_kit.mame.records import Schema, SpecError

# 1942-beeb's whole-game record (tools/mame/fullgame.lua), G list shortened
FULLGAME = ("f:frame;g:bytes@e103,e102,e101,e099,e0a5,e0d2,e0d3;"
            "spr:bytes@cc00-cc7f;obj:slots@e400,10,30,30")


def memory(seed):
    def read(a):
        return (a * 7 + seed) & 0xFF
    return read


class Spec(unittest.TestCase):
    def test_parse_fullgame(self):
        s = Schema.parse(FULLGAME)
        f, g, spr, obj = s.fields
        self.assertEqual((f.kind, g.kind, spr.kind, obj.kind),
                         ("frame", "bytes", "bytes", "slots"))
        self.assertEqual(len(spr.addrs), 128)
        self.assertEqual((obj.base, obj.n, obj.stride, obj.length), (0xE400, 16, 0x30, 0x30))
        self.assertIsNone(s.fixed_size)
        self.assertEqual(Schema.parse("f:frame;g:bytes@$e0d2,0xe0d3,&e0d5").fixed_size, 7)

    def test_bad_specs(self):
        for bad in ("", "x", "x:word@1", "g:bytes@", "g:bytes@zz", "g:bytes@10-5",
                    "o:slots@e400,10", "o:slots@e400,10,30,0", "o:slots@e400,10,30,30,30",
                    "a:frame;a:frame"):
            with self.assertRaises(SpecError, msg=bad):
                Schema.parse(bad)


class RoundTrip(unittest.TestCase):
    def test_pack_read(self):
        s = Schema.parse("f:frame;g:bytes@10,11;obj:slots@100,4,8,3,2,80")

        def mem(frame):
            # slot i is live when byte base+i*8+2 has bit 7 set: slots 1 and 3
            def read(a):
                if a >= 0x100 and (a - 0x100) % 8 == 2:
                    return 0x80 if (a - 0x100) // 8 in (1, 3) else 0x7F
                return (a + frame) & 0xFF
            return read

        data = b"".join(s.pack(n, mem(n)) for n in (1, 2, 3))
        recs = list(s.records(data))
        self.assertEqual([r["f"] for r in recs], [1, 2, 3])
        self.assertEqual(recs[1]["g"].at(0x11), 0x13)
        self.assertEqual(recs[1]["g"].word(0x10), 0x12 | (0x13 << 8))
        self.assertEqual(sorted(recs[0]["obj"]), [1, 3])
        self.assertEqual(recs[0]["obj"][1], bytes([0x09, 0x0A, 0x80]))  # (a + frame) & FF, live byte last

    def test_truncation_is_an_error(self):
        s = Schema.parse(FULLGAME)
        data = s.pack(1, memory(1)) + s.pack(2, memory(2))
        self.assertEqual(len(list(s.records(data))), 2)
        with self.assertRaises(SpecError):
            list(s.records(data[:-5]))
        fixed = Schema.parse("f:frame;g:bytes@0-3")
        with self.assertRaises(SpecError):
            list(fixed.records(b"\x00" * 13))

    def test_wrong_spec_is_caught(self):
        # a file written with 16 slots read as if it had 4
        w = Schema.parse("obj:slots@0,10,4,1")
        data = w.pack(0, lambda a: 1)
        with self.assertRaises(SpecError):
            list(Schema.parse("obj:slots@0,4,4,1").records(data))

    def test_load_capture(self):
        with tempfile.TemporaryDirectory() as td:
            s = Schema.parse(FULLGAME)
            with open(os.path.join(td, "ram.bin"), "wb") as f:
                for n in range(1, 6):
                    f.write(s.pack(n, memory(n)))
            with open(os.path.join(td, "schema.txt"), "w") as f:
                f.write("# written by capture_ram.lua\n" + FULLGAME + "\n")
            sch, path = records.load_capture(td, "ram.bin")
            recs = list(sch.read(path))
            self.assertEqual(len(recs), 5)
            self.assertEqual(recs[4]["g"].at(0xE103), memory(5)(0xE103))

    def test_runs(self):
        self.assertEqual(records.runs([0, 0, 1, 1, 1, 0]),
                         [(0, 1, 0), (2, 4, 1), (5, 5, 0)])


if __name__ == "__main__":
    unittest.main()
