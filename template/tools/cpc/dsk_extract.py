"""Extract AMSDOS files from a CPC DSK, standard ("MV - CPCEMU") or EXTENDED (DATA format:
sectors &C1-&C9, 1K blocks).

python tools/dsk_extract.py DSK OUTDIR    - every file, AMSDOS header stripped (kept as .hdr)
As a library: read_dsk_bytes(raw) -> tracks; read_file(tracks, 'NAME.EXT') -> bytes (header
stripped); read_raw(tracks, name) -> the entry with its header; header(raw) -> (load, exec, len).

Square Roots' disc is a standard DSK: one track size for every track (header &32-&33), each
sector 128 << N bytes (N from the track's sector info). Isometrikum's was EXTENDED.
"""
import os
import struct
import sys


def read_dsk_bytes(d):
    ext = d[:8] == b'EXTENDED'
    assert ext or d[:8] == b'MV - CPC', 'not a CPC DSK'
    ntracks, nsides = d[0x30], d[0x31]
    if ext:
        sizes = [s * 256 for s in d[0x34:0x34 + ntracks * nsides]]
    else:
        sizes = [struct.unpack('<H', d[0x32:0x34])[0]] * (ntracks * nsides)
    off = 0x100
    tracks = {}
    for t in range(ntracks * nsides):
        if sizes[t] == 0:
            continue
        tb = d[off:off + sizes[t]]
        assert tb[:10] == b'Track-Info', f'track {t}'
        secs = {}
        p = 0x100
        for s in range(tb[0x15]):
            info = tb[0x18 + s * 8:0x20 + s * 8]
            ln = struct.unpack('<H', info[6:8])[0] if ext else 128 << info[3]
            secs[info[2]] = tb[p:p + ln]
            p += ln
        tracks[t] = secs
        off += sizes[t]
    return tracks


def directory(tracks):
    def sector(lin):
        return tracks[lin // 9][0xC1 + lin % 9]

    def block(b):
        return sector(b * 2) + sector(b * 2 + 1)
    dirb = block(0) + block(1)
    files = {}
    for i in range(64):
        e = dirb[i * 32:(i + 1) * 32]
        if e[0] == 0xE5:
            continue
        name = bytes(c & 0x7F for c in e[1:9]).decode().strip()
        ext = bytes(c & 0x7F for c in e[9:12]).decode().strip()
        if ext:
            name += '.' + ext
        files.setdefault(name, []).append((e[12], e[15], [b for b in e[16:32] if b]))
    out = {}
    for name, exts in files.items():
        data = b''
        for ext, rc, blocks in sorted(exts):
            data += b''.join(block(b) for b in blocks)[:rc * 128]
        out[name] = data
    return out


def strip_header(data):
    """(payload, header or None): an AMSDOS header is recognised by its checksum"""
    if len(data) >= 128 and sum(data[:67]) & 0xFFFF == struct.unpack('<H', data[67:69])[0]:
        flen = struct.unpack('<H', data[64:66])[0] | (data[66] << 16)
        return data[128:128 + flen], data[:128]
    return data, None


def header(raw):
    """(load, exec, length) of an AMSDOS file with its header"""
    payload, h = strip_header(raw)
    assert h, 'no AMSDOS header'
    return struct.unpack('<H', h[21:23])[0], struct.unpack('<H', h[26:28])[0], len(payload)


def read_raw(tracks, name):
    return directory(tracks)[name]


def read_file(tracks, name):
    return strip_header(directory(tracks)[name])[0]


def main(path, out):
    tracks = read_dsk_bytes(open(path, 'rb').read())
    os.makedirs(out, exist_ok=True)
    for name, data in directory(tracks).items():
        payload, h = strip_header(data)
        if h:
            load, exe = struct.unpack('<H', h[21:23])[0], struct.unpack('<H', h[26:28])[0]
            print(f'{name}: AMSDOS type={h[18]} load=&{load:04X} exec=&{exe:04X} len={len(payload)}')
            open(os.path.join(out, name + '.hdr'), 'wb').write(h)
        else:
            print(f'{name}: no header, {len(data)} bytes')
        open(os.path.join(out, name), 'wb').write(payload)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
