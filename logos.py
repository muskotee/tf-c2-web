"""Validated, persistent logo images. Original upload metadata is discarded."""
import base64
import binascii
import hashlib
import io
from pathlib import Path
import re
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent / 'data' / 'logos'
MAX_BYTES = 2 * 1024 * 1024


def image_path(identifier):
    if not isinstance(identifier, str) or not re.fullmatch('[0-9a-f]{64}', identifier):
        raise ValueError('Ungültige Logo-ID.')
    path = ROOT / (identifier + '.png')
    if not path.is_file():
        raise ValueError('Das gespeicherte Logo wurde nicht gefunden. Bitte erneut hochladen.')
    return path


def store(encoded, name):
    if not isinstance(encoded, str) or len(encoded) > (MAX_BYTES + 2) // 3 * 4:
        raise ValueError('Das Logo darf höchstens 2 MB groß sein.')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError('Die Bilddatei konnte nicht gelesen werden.') from exc
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('Bitte eine Bilddatei mit höchstens 2 MB auswählen.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in ('PNG', 'JPEG', 'WEBP', 'BMP'):
                    raise ValueError('Unterstützt werden PNG, JPG, WebP und BMP.')
                width, height = source.size
                if width * height > 4_000_000 or max(width, height) > 8192:
                    raise ValueError('Bitte ein Logo mit höchstens 4 Megapixeln verwenden.')
                image = ImageOps.exif_transpose(source).convert('RGBA')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('Die Datei ist kein unterstütztes, lesbares Bild.') from exc
    # Remove transparent margins, but preserve white backgrounds as image content.
    bounds = image.getchannel('A').getbbox()
    if not bounds:
        raise ValueError('Das Bild ist vollständig transparent.')
    image = image.crop(bounds)
    image.thumbnail((512, 512), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format='PNG')
    content = out.getvalue()
    identifier = hashlib.sha256(content).hexdigest()
    ROOT.mkdir(parents=True, exist_ok=True)
    target = ROOT / (identifier + '.png')
    if not target.exists():
        target.write_bytes(content)
    name = str(name or 'Logo').replace('\\', '/').split('/')[-1][:100]
    return {'id': identifier, 'name': name, 'width': image.width, 'height': image.height,
            'url': '/api/logo/' + identifier + '.png'}


def prepare(opt, color, max_height=32, max_width=128):
    if not opt.get('logo_id'):
        return None
    with Image.open(image_path(opt['logo_id'])) as source:
        image = source.convert('RGBA')
    scale = min(min(opt['logo_width'], max_width) / image.width, max_height / image.height)
    image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
    alpha = image.getchannel('A')
    if opt['logo_style'] == 'invert':
        image = ImageOps.invert(image.convert('RGB')).convert('RGBA')
        image.putalpha(alpha)
    elif opt['logo_style'] == 'solid':
        image = Image.new('RGBA', image.size, (*color, 255))
        image.putalpha(alpha)
    return image
