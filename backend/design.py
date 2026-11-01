"""Read reference dimensions without resizing or changing its bytes."""
import base64
import re
import struct
from xml.etree import ElementTree


def design_viewport(target: str | None) -> dict[str, int]:
    if not target:
        return {"width": 1440, "height": 900}
    try:
        header, encoded = target.split(';base64,', 1)
        if not header.startswith('data:image/') or len(encoded) > 8 * 1024 * 1024:
            raise ValueError('invalid image')
        data = base64.b64decode(encoded, validate=True)
        if data.startswith(b'\x89PNG\r\n\x1a\n') and data[12:16] == b'IHDR':
            width, height = struct.unpack('>II', data[16:24])
        elif data[:2] == b'\xff\xd8':
            pos = 2
            while pos < len(data):
                if data[pos] != 255:
                    raise ValueError('JPEG marker')
                while data[pos] == 255:
                    pos += 1
                marker = data[pos]; pos += 1
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    continue
                length = int.from_bytes(data[pos:pos+2], 'big')
                if marker in (0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB,0xCD,0xCE,0xCF):
                    height, width = struct.unpack('>HH', data[pos+3:pos+7]); break
                if length < 2: raise ValueError('JPEG length')
                pos += length
            else: raise ValueError('JPEG dimensions')
        elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            kind = data[12:16]
            if kind == b'VP8X':
                width = 1 + int.from_bytes(data[24:27], 'little')
                height = 1 + int.from_bytes(data[27:30], 'little')
            elif kind == b'VP8L' and data[20] == 0x2F:
                bits = int.from_bytes(data[21:25], 'little')
                width, height = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            elif kind == b'VP8 ' and data[23:26] == b'\x9d\x01\x2a':
                width, height = struct.unpack('<HH', data[26:30])
                width &= 0x3FFF; height &= 0x3FFF
            else: raise ValueError('WebP format')
        elif header == 'data:image/svg+xml':
            if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
                raise ValueError('SVG declaration')
            root = ElementTree.fromstring(data)
            def pixels(value):
                if not re.fullmatch(r'\d+(?:px)?', value or ''):
                    raise ValueError('SVG requires explicit pixel dimensions')
                return int(value.removesuffix('px'))
            width, height = pixels(root.get('width')), pixels(root.get('height'))
        else:
            raise ValueError('unsupported image')
        if not (64 <= width <= 2560 and 64 <= height <= 2560):
            raise ValueError('viewport out of range')
        return {"width": width, "height": height}
    except (ValueError, IndexError, struct.error, ElementTree.ParseError) as exc:
        raise ValueError('无法读取设计图尺寸，或尺寸超出64–2560像素范围；原图未修改。') from exc
