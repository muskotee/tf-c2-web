"""Native multi-program directory, verified against PowerLED captures.

The controller switches complete window layouts; no scene-by-scene uploads.
"""
import struct


def merge(entries):
    if not 1 <= len(entries) <= 30:
        raise ValueError('Eine Folge benötigt 1 bis 30 Programme.')
    first = entries[0][0]
    header = bytearray(first[:128])
    if len(header) != 128:
        raise ValueError('Die Programmdatei ist zu kurz.')
    count = len(entries)
    struct.pack_into('<H', header, 120, count)
    # Captured native directory checks (counts 1, 2, 3).
    header[125] = (header[125] - count + 1) & 255
    header[127] = (header[127] + count - 1) & 255
    result = header + bytearray(4 * count)
    for index, entry in enumerate(entries):
        source, seconds = entry[:2]
        play_mode = entry[2] if len(entry) == 3 else 1
        if play_mode not in (0,1):
            raise ValueError('Unbekannter Programm-Abspielmodus.')
        if struct.unpack_from('<H', source, 120)[0] != 1 or struct.unpack_from('<I', source, 72)[0]:
            raise ValueError('Die Szene benötigt ein einzelnes Programm ohne externe Schrift.')
        if not isinstance(seconds, int) or not 2 <= seconds <= 3600:
            raise ValueError('Ungültige Szenenlaufzeit.')
        old_base = struct.unpack_from('<I', source, 128)[0]
        if old_base != 132 or len(source) < old_base + 444:
            raise ValueError('Unbekanntes natives Programmformat.')
        base = len(result); delta = base - old_base
        struct.pack_into('<I', result, 128 + index * 4, base)
        result.extend(source[old_base:])
        struct.pack_into('<HB', result, base, seconds, play_mode)
        visited = set()
        for row in range(15):
            pointer_at = old_base + 216 + row * 12
            pointer = struct.unpack_from('<I', source, pointer_at)[0]
            if not pointer:
                break
            struct.pack_into('<I', result, pointer_at + delta, pointer + delta)
            chain = set()
            while pointer:
                if pointer in chain or pointer < old_base + 444 or pointer + 24 > len(source):
                    raise ValueError('Ungültige Seitenverkettung in der Szene.')
                chain.add(pointer)
                next_page = struct.unpack_from('<I', source, pointer)[0]
                if pointer not in visited:
                    struct.pack_into('<I', result, pointer + delta, next_page + delta if next_page else 0)
                    visited.add(pointer)
                pointer = next_page
    return bytes(result)
