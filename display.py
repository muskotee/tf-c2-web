"""TF-C2 V6 / firmware 0.5.9: local raster compilation and serial upload.

The linked-page layout and commands were verified against PowerLED captures.
Only program memory is changed; panel wiring/scan parameters are never written.
"""
import contextlib
import fcntl
import io
import math
import os
from pathlib import Path
import select
import struct
import termios
import time
import re

from PIL import Image, ImageDraw, ImageFont
import logos

ROOT = Path(__file__).resolve().parent
DEVICE = os.environ.get('TF_SERIAL_DEVICE', '/dev/serial/by-id/usb-1a86_USB2.0-Ser_-if00-port0')
WIDTH, HEIGHT = 128, 32
COLORS = {'red': (255, 0, 0), 'green': (0, 255, 0), 'blue': (0, 0, 255),
          'amber': (255, 255, 0), 'cyan': (0, 255, 255),
          'magenta': (255, 0, 255), 'white': (255, 255, 255)}
FONT = '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'
MAX_PAGES = 120
ENCODER_VERSION = 3
SIZES = (10, 11, 12, 14, 16, 20, 24, 28)
EFFECTS = {
    'direct': (1, 'Direkt anzeigen'), 'left': (4, 'Von rechts einschieben'),
    'right': (5, 'Von links einschieben'), 'up': (6, 'Nach oben einschieben'),
    'down': (7, 'Nach unten einschieben'), 'rain': (9, 'Regen'),
    'fountain': (10, 'Fontäne'), 'flash': (11, 'Blinken'),
    'laser_left': (15, 'Laser von links'), 'laser_right': (16, 'Laser von rechts'),
    'open_h': (31, 'Horizontal öffnen'), 'open_v': (33, 'Vertikal öffnen'),
    'shutter_h': (35, 'Horizontale Jalousie'), 'shutter_v': (36, 'Vertikale Jalousie'),
    'mosaic': (41, 'Mosaik'), 'diamond': (42, 'Raute öffnen'),
    'fall': (44, 'Hereinfallen'),
    'ticker_left': (3, 'Fortlaufend nach links'),
    'ticker_right': (5, 'Fortlaufend nach rechts'),
}


def packet(command, payload=b'', sub=0, sequence=6, panel=1):
    key = 8
    result = bytearray(struct.pack('<HBBBBH', len(payload) + 12, key, command, sub, 0, panel))
    result.extend(payload)
    result.extend(((key - sequence) & 255, sequence & 255))
    result.extend(struct.pack('<H', sum(result) & 65535))
    for i in range(len(result)):
        if i != 2:
            result[i] ^= ((i + 1 + key) if i % 2 else (i + 5) * key) & 255
    return bytes(result)


def read_frame(fd, timeout=4):
    data = bytearray()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not select.select([fd], [], [], max(0, end - time.monotonic()))[0]:
            break
        data.extend(os.read(fd, 8192))
        if len(data) >= 3:
            length = int.from_bytes(data[:2], 'little')
            if not 12 <= length <= 4096:
                raise RuntimeError('Ungültige Antwortlänge vom Display.')
            if len(data) >= length:
                frame = bytes(data[:length])
                if frame[2] not in (0x0a, 0xfa):
                    raise RuntimeError('Unerwartete Controllerantwort.')
                if (sum(frame[:-2]) & 65535) != int.from_bytes(frame[-2:], 'little'):
                    raise RuntimeError('Prüfsummenfehler in der Controllerantwort.')
                if frame[2] == 0xfa:
                    raise RuntimeError('Der Controller hat den Befehl abgelehnt.')
                return frame
    raise RuntimeError('Das Display antwortet nicht. Stromversorgung und COM-Kabel prüfen.')


@contextlib.contextmanager
def serial_port():
    ROOT.joinpath('data').mkdir(exist_ok=True)
    with open(ROOT / 'data' / 'serial.lock', 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Die serielle Schnittstelle ist gerade belegt.')
        fd = os.open(DEVICE, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        old = termios.tcgetattr(fd)
        try:
            fcntl.ioctl(fd, termios.TIOCEXCL)
            a = termios.tcgetattr(fd)
            a[0] = a[1] = a[3] = 0
            a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
            a[4] = a[5] = termios.B57600
            a[6][termios.VMIN] = a[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, a)
            termios.tcflush(fd, termios.TCIFLUSH)
            yield fd
        finally:
            termios.tcsetattr(fd, termios.TCSANOW, old)
            fcntl.ioctl(fd, termios.TIOCNXCL)
            os.close(fd)


def exchange(fd, data):
    view = memoryview(data)
    end = time.monotonic() + 5
    while view:
        if time.monotonic() > end:
            raise RuntimeError('Zeitüberschreitung beim Senden.')
        try:
            written = os.write(fd, view)
            view = view[written:]
        except BlockingIOError:
            select.select([], [fd], [], .1)
    termios.tcdrain(fd)
    return read_frame(fd)


def probe_fd(fd):
    firmware = exchange(fd, packet(0x12))[8:-4]
    raw = exchange(fd, packet(0x21, sequence=7))[8:-4]
    if len(raw) != 112:
        raise RuntimeError('Unbekanntes Parameterformat des Controllers.')
    baud, panel, width, height = struct.unpack_from('<IHHH', raw)
    if (width, height, panel) != (128, 32, 1):
        raise RuntimeError(f'Display meldet {width}×{height}, ID {panel}; erwartet 128×32, ID 1.')
    if firmware != bytes.fromhex('9121000509'):
        raise RuntimeError('Diese Firmware wurde noch nicht für die Übertragung geprüft.')
    return {'connected': True, 'width': width, 'height': height, 'baud': baud,
            'panel': panel, 'firmware': 'TF-C2 0.5.9', 'raw_parameters': raw.hex(),
            'brightness': raw[80], 'brightness_manual': raw[81] == 1}


def probe():
    with serial_port() as fd:
        return probe_fd(fd)


def set_brightness(level):
    if type(level) is not int or not 0 <= level <= 15:
        raise ValueError('Helligkeit: bitte eine der 16 Stufen wählen.')
    with serial_port() as fd:
        before = probe_fd(fd)
        raw = bytearray.fromhex(before['raw_parameters'])
        # Native PowerLED capture: command 20/sub 2, manual level at 80,
        # brightness mode at 81. Keep every other controller byte verbatim.
        raw[80:82] = bytes((level, 1))
        response = exchange(fd, packet(0x20, bytes(raw), sub=2, sequence=8))
        if len(response) != 12 or response[3:6] != b'\0\0\0':
            raise RuntimeError('Die Helligkeit wurde nicht bestätigt.')
        # The native settings command briefly restarts controller communication.
        time.sleep(1)
        for attempt in range(3):
            try:
                termios.tcflush(fd, termios.TCIFLUSH)
                current = probe_fd(fd)
                break
            except RuntimeError:
                if attempt == 2:
                    raise
                time.sleep(1)
        if current['raw_parameters'] != raw.hex():
            raise RuntimeError('Die zurückgelesenen Helligkeitswerte stimmen nicht überein.')
        return current


def options(value):
    text = str(value.get('text', '')).replace('\r\n', '\n').strip()
    text = ''.join(c for c in text if c in '\n\t' or ord(c) >= 32)
    logo_id = value.get('logo_id') or None
    if (not text and not logo_id) or len(text) > 2000:
        raise ValueError('Bitte einen Text eingeben oder ein Logo auswählen (maximal 2000 Zeichen).')
    logo_position = value.get('logo_position', 'left')
    logo_width = int(value.get('logo_width', 32))
    logo_style = value.get('logo_style', 'original')
    if not logo_id:
        logo_width = 32
    if logo_position not in ('left', 'right', 'alone') or logo_style not in ('original', 'invert', 'solid'):
        raise ValueError('Ungültige Logo-Darstellung.')
    if not 16 <= logo_width <= (128 if not text or logo_position == 'alone' else 64):
        raise ValueError('Logo-Breite: 16 bis 64 Pixel neben Text, bis 128 Pixel für ein Logo allein.')
    if logo_id:
        logos.image_path(logo_id)
        if logo_position == 'alone' and text:
            raise ValueError('Für „Nur Logo“ bitte den Text ausblenden oder die Position neben Text wählen.')
    size = int(value.get('size', 14))
    size2 = int(value.get('size2', 12))
    split_sizes = bool(value.get('split_sizes', False))
    if size not in SIZES or size2 not in SIZES:
        raise ValueError('Ungültige Schriftgröße.')
    mode = value.get('mode', 'pages')
    color = value.get('color', 'red')
    align = value.get('align', 'center')
    speed = int(value.get('speed', 10))
    duration = int(value.get('duration', 5))
    effect = value.get('effect') or ('ticker_left' if mode == 'ticker' else 'direct')
    if effect == 'random':
        effect = 'direct'
    if effect not in EFFECTS:
        raise ValueError('Unbekannter Anzeigeeffekt.')
    if mode not in ('auto', 'static', 'pages', 'ticker') or color not in COLORS or align not in ('left', 'center'):
        raise ValueError('Ungültige Anzeigeoption.')
    if not 1 <= speed <= 30 or not 2 <= duration <= 30:
        raise ValueError('Anzeigedauer oder Geschwindigkeit außerhalb des gültigen Bereichs.')
    background = value.get('background', 'black')
    frame = value.get('frame', 'none')
    frame_color = value.get('frame_color', 'amber')
    frame_width = int(value.get('frame_width', 1))
    if background not in ('black', *COLORS) or frame_color not in COLORS or frame not in ('none', 'solid', 'dashed', 'dots') or frame_width not in (1, 2):
        raise ValueError('Ungültige Hintergrund- oder Rahmeneinstellung.')
    return dict(text=text, size=size, mode=mode, color=color, align=align,
                background=background, frame=frame, frame_color=frame_color, frame_width=frame_width,
                speed=speed, duration=duration, effect=effect, logo_id=logo_id,
                logo_position=logo_position, logo_width=logo_width, logo_style=logo_style,
                split_sizes=split_sizes, size2=size2)


def wrap(text, font, width=WIDTH):
    lines = []
    for paragraph in text.split('\n'):
        if not paragraph.strip():
            lines.append('')
            continue
        current = ''
        for word in paragraph.split():
            candidate = (current + ' ' + word).strip()
            if font.getlength(candidate) <= width - 4:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ''
            for ch in word:
                if font.getlength(current + ch) > width - 4 and current:
                    lines.append(current)
                    current = ''
                current += ch
        lines.append(current)
    return lines


def styled_lines(text, size, size2, split_sizes, width):
    result = []
    for index, paragraph in enumerate(text.split('\n')):
        font_size = size2 if split_sizes and index > 0 else size
        font = ImageFont.truetype(FONT, font_size)
        for line in wrap(paragraph, font, width):
            box = font.getbbox(line or 'Ag')
            result.append({'text': line, 'size': font_size,
                           'height': max(font_size + 1, box[3] - box[1])})
    return result


def paginate(lines, limit=HEIGHT):
    groups, group, height = [], [], 0
    for line in lines:
        if group and height + line['height'] > limit:
            groups.append(group)
            group, height = [], 0
        group.append(line)
        height += line['height']
    if group or not groups:
        groups.append(group)
    return groups


def layout(value):
    opt = options(value)
    inset = opt['frame_width'] + 1 if opt['frame'] != 'none' else 0
    content_width, content_height = WIDTH - 2 * inset, HEIGHT - 2 * inset
    logo = logos.prepare(opt, COLORS[opt['color']], content_height, content_width)
    logo_only = logo is not None and not opt['text']
    text_width = content_width - logo.width - 4 if logo is not None and not logo_only else content_width
    def profile(size, size2):
        font = ImageFont.truetype(FONT, size)
        lines = styled_lines(opt['text'], size, size2, opt['split_sizes'], text_width) if opt['text'] else []
        line_height = max([size + 1] + [line['height'] for line in lines])
        rows = max(1, content_height // line_height)
        groups = paginate(lines, content_height)
        page_count = len(groups)
        raw_width = math.ceil(max((ImageFont.truetype(FONT, size2 if opt['split_sizes'] and i > 0 else size).getlength(line)
                                  for i, line in enumerate(opt['text'].splitlines())), default=0))
        ticker_text = '   '.join(opt['text'].splitlines()) + '     '
        ticker_box = font.getbbox(ticker_text)
        ticker_count = math.ceil(max(WIDTH, math.ceil(font.getlength(ticker_text)) + 4) / WIDTH)
        return {'size': size, 'size2': size2, 'fits': page_count == 1 and line_height <= content_height,
                         'lines': len(lines), 'rows': max(rows, len(lines)) if opt['split_sizes'] else rows, 'line_height': line_height,
                         'pages': page_count, 'width': raw_width,
                         'height': sum(line['height'] for line in lines),
                         'pages_allowed': line_height <= content_height and page_count <= MAX_PAGES,
                         'ticker_allowed': not inset and logo is None and not opt['split_sizes'] and ticker_box[3] - ticker_box[1] <= HEIGHT and ticker_count <= MAX_PAGES,
                         'ticker_pages': ticker_count}
    profiles = [profile(size, opt['size2']) for size in SIZES]
    profiles2 = [profile(opt['size'], size) for size in SIZES] if opt['split_sizes'] else []
    current = next(p for p in profiles if p['size'] == opt['size'])
    effective = opt['mode']
    if effective == 'auto':
        effective = 'static' if current['fits'] else ('pages' if '\n' in opt['text'] else 'ticker')
        if effective == 'ticker' and not current['ticker_allowed']:
            effective = 'pages'
        if effective == 'pages' and not current['pages_allowed'] and current['ticker_allowed']:
            effective = 'ticker'
    allowed_modes = ['auto'] if current['pages_allowed'] or current['ticker_allowed'] else []
    if current['fits']:
        allowed_modes.append('static')
    if current['pages_allowed']:
        allowed_modes.append('pages')
    if current['ticker_allowed']:
        allowed_modes.append('ticker')
    if logo_only:
        allowed_modes = ['auto', 'static']
        if effective in ('pages', 'ticker'):
            effective = 'static'
    effects = [key for key in EFFECTS if key.startswith('ticker_') == (effective == 'ticker')]
    return {'width': WIDTH, 'height': HEIGHT, 'current': current, 'sizes': profiles,
            'sizes2': profiles2, 'split_sizes': opt['split_sizes'],
            'text_width': text_width, 'content_height': content_height, 'inset': inset, 'logo_only': logo_only,
            'logo': {'width': logo.width, 'height': logo.height, 'position': opt['logo_position']} if logo is not None else None,
            'allowed_modes': allowed_modes, 'effective_mode': effective,
            'effects': [{'value': key, 'label': EFFECTS[key][1]} for key in effects]}


def render(value):
    opt = options(value)
    measured = layout(opt)
    if opt['mode'] not in measured['allowed_modes']:
        raise ValueError('Dieser Text passt mit der gewählten Schriftgröße nicht auf eine einzelne 128×32-Seite. Bitte Automatik, Textseiten oder Laufschrift wählen.')
    effective = measured['effective_mode']
    if effective not in measured['allowed_modes']:
        raise ValueError('Der Text ist für diese Schriftgröße zu lang. Bitte eine kleinere Schrift oder weniger Text verwenden.')
    effect_keys = [e['value'] for e in measured['effects']]
    if opt['effect'] not in effect_keys:
        opt['effect'] = 'ticker_left' if effective == 'ticker' else 'direct'
    font = ImageFont.truetype(FONT, opt['size'])
    rgb = COLORS[opt['color']]
    inset, content_height = measured['inset'], measured['content_height']
    background = COLORS.get(opt['background'], (0, 0, 0))
    logo = logos.prepare(opt, rgb, content_height, WIDTH - 2 * inset)
    text_width = measured['text_width']
    text_x = inset + (logo.width + 4 if logo is not None and opt['logo_position'] == 'left' and opt['text'] else 0)
    pages = []
    if effective == 'ticker':
        text = '   '.join(opt['text'].splitlines()) + '     '
        width = max(WIDTH, math.ceil(font.getlength(text)) + 4)
        if math.ceil(width / WIDTH) > MAX_PAGES:
            raise ValueError('Der Text ist für dieses Display zu lang.')
        strip = Image.new('RGB', (math.ceil(width / WIDTH) * WIDTH, HEIGHT), background)
        box = font.getbbox(text)
        y = (HEIGHT - (box[3] - box[1])) // 2 - box[1]
        ImageDraw.Draw(strip).text((2, y), text, font=font, fill=rgb, stroke_width=0)
        pages = [strip.crop((x, 0, x + WIDTH, HEIGHT)) for x in range(0, strip.width, WIDTH)]
        if opt['effect'] == 'ticker_right':
            pages.reverse()
    else:
        lines = styled_lines(opt['text'], opt['size'], opt['size2'], opt['split_sizes'], text_width) if opt['text'] else []
        for group in paginate(lines, content_height):
            image = Image.new('RGB', (WIDTH, HEIGHT), background)
            draw = ImageDraw.Draw(image)
            # Center the visible glyphs, excluding unused font line spacing.
            text_mask = Image.new('L', (text_width, max(1, sum(line['height'] for line in group))))
            text_draw = ImageDraw.Draw(text_mask)
            top = 0
            for line in group:
                row_font = ImageFont.truetype(FONT, line['size'])
                box = row_font.getbbox(line['text'] or 'Ag')
                x = max(2, (text_width - row_font.getlength(line['text'])) // 2) if opt['align'] == 'center' else 2
                text_draw.text((x, top - box[1]), line['text'], font=row_font, fill=255)
                top += line['height']
            text_mask = text_mask.point(lambda v: 255 if v >= 96 else 0)
            bounds = text_mask.getbbox()
            if bounds:
                cropped = text_mask.crop((0, bounds[1], text_width, bounds[3]))
                image.paste(rgb, (text_x, inset + (content_height - cropped.height) // 2,
                                  text_x + text_width, inset + (content_height - cropped.height) // 2 + cropped.height), cropped)
            if logo is not None:
                logo_x = (WIDTH - logo.width) // 2 if measured['logo_only'] else (WIDTH - inset - logo.width if opt['logo_position'] == 'right' else inset)
                image.paste(logo, (logo_x, (HEIGHT - logo.height) // 2), logo)
            if opt['frame'] != 'none':
                border = COLORS[opt['frame_color']]
                for depth in range(opt['frame_width']):
                    edge = ([(x, depth) for x in range(depth, WIDTH-depth)]
                            + [(WIDTH-1-depth, y) for y in range(depth+1, HEIGHT-depth)]
                            + [(x, HEIGHT-1-depth) for x in range(WIDTH-2-depth, depth-1, -1)]
                            + [(depth, y) for y in range(HEIGHT-2-depth, depth, -1)])
                    for index, point in enumerate(edge):
                        if opt['frame'] == 'solid' or (index % 6 < 3 if opt['frame'] == 'dashed' else index % 2 == 0):
                            draw.point(point, fill=border)
            pages.append(image)
    if len(pages) > MAX_PAGES:
        raise ValueError(f'Der Text erzeugt mehr als {MAX_PAGES} Seiten. Bitte kürzen.')
    # Quantize before both preview and upload so their pixels agree.
    pages = [image.point(lambda v: 255 if v >= 96 else 0) for image in pages]
    return opt, pages


def raster(image):
    result = bytearray(1536)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            pixel = image.getpixel((x, y))
            # This panel uses R/B/G plane order; previews remain standard RGB.
            for plane, channel in enumerate((0, 2, 1)):
                if pixel[channel] >= 96:
                    result[plane * 512 + y * 16 + x // 8] |= 1 << (x % 8)
    return bytes(result)


def assemble(rendered):
    template = ROOT.joinpath('image-template.bin').read_bytes()
    if len(template) != 2136:
        raise RuntimeError('Die geprüfte Programmvorlage fehlt oder ist beschädigt.')
    program = bytearray(template[:576])
    all_pages = [(scene['options'], scene['effective_mode'], image)
                 for scene in rendered for image in scene['images']]
    if not 1 <= len(all_pages) <= MAX_PAGES:
        raise ValueError(f'Eine Folge darf insgesamt höchstens {MAX_PAGES} Anzeigeseiten enthalten.')
    # A linked list of 24-byte page headers and three 512-byte color planes.
    for i, (opt, effective, image) in enumerate(all_pages):
        header = bytearray(template[576:600])
        next_offset = 576 + (i + 1) * 1560 if i + 1 < len(all_pages) else 0
        struct.pack_into('<I', header, 0, next_offset)
        struct.pack_into('<H', header, 4, 0 if effective == 'ticker' else opt['duration'] * 10)
        header[6] = 1
        header[7] = 2
        # PowerLED's TF-C2 records: +8 exit mode, +9 device-specific effect.
        # Writing to +8 leaves +9 at random (0) and causes changing effects.
        header[8] = 0
        header[9] = EFFECTS[opt['effect']][0]
        header[10] = opt['speed']
        struct.pack_into('<I', header, 20, opt['duration'] * 10)
        program.extend(header)
        program.extend(raster(image))
    return bytes(program)


def compile_program(value):
    opt, pages = render(value)
    program = assemble([{'options': opt, 'effective_mode': layout(opt)['effective_mode'], 'images': pages}])
    return program, opt, pages


def render_timeline(value):
    scenes = value.get('scenes')
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 30:
        raise ValueError('Eine Timeline benötigt 1 bis 30 Szenen.')
    rendered, identifiers, total_pages = [], set(), 0
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict) or not isinstance(scene.get('options'), dict):
            raise ValueError(f'Szene {index + 1}: Anzeigeeinstellungen fehlen.')
        identifier = str(scene.get('id') or f'scene-{index + 1}')
        if not re.fullmatch('[A-Za-z0-9_-]{1,64}', identifier) or identifier in identifiers:
            raise ValueError('Szenen benötigen eindeutige IDs.')
        identifiers.add(identifier)
        name = str(scene.get('name') or f'Szene {index + 1}').strip()[:80] or f'Szene {index + 1}'
        scene_type = scene.get('type', 'text')
        if scene_type not in ('text', 'clock'):
            raise ValueError('Unbekannter Szenentyp.')
        try:
            if scene_type == 'clock':
                import clocks
                opt = clocks.options(scene['options'])
                duration = int(scene['options'].get('duration', 5))
                if not 2 <= duration <= 30:
                    raise ValueError('Uhrszenen benötigen 2 bis 30 Sekunden.')
                image, _ = clocks.preview(opt)
                images, effective = [image], 'clock'
                opt['duration'] = duration
            else:
                opt, images = render(scene['options'])
                effective = layout(opt)['effective_mode']
        except ValueError as exc:
            raise ValueError(f'Szene {index + 1} „{name}“: {exc}') from exc
        total_pages += len(images)
        if total_pages > MAX_PAGES:
            raise ValueError(f'Die Timeline enthält mehr als {MAX_PAGES} Seiten. Bitte Szenen kürzen oder entfernen.')
        rendered.append({'id': identifier, 'name': name, 'type': scene_type, 'options': opt, 'images': images,
                         'effective_mode': effective, 'preview_seconds': len(images) * opt['duration']})
    return rendered


def timeline_project(value, rendered=None):
    rendered = render_timeline(value) if rendered is None else rendered
    return {'name': str(value.get('name') or 'Meine Timeline').strip()[:80] or 'Meine Timeline',
            'scenes': [{'id': scene['id'], 'name': scene['name'], 'type': scene['type'], 'options': scene['options']} for scene in rendered]}


def compile_timeline(value):
    rendered = render_timeline(value)
    project = timeline_project(value, rendered)
    clock_scenes = [s for s in rendered if s['type'] == 'clock']
    extra = {}
    if clock_scenes:
        import clocks
        import programs
        import datetime
        instant = datetime.datetime.now(datetime.timezone.utc)
        reference = clocks.options(clock_scenes[0]['options'])
        reference_offset = clocks.now(reference, instant).utcoffset()
        entries = []
        for scene in rendered:
            if scene['type'] == 'clock':
                data, opt = clocks.compile_program(scene['options'], instant)
                data = bytearray(data)
                delta = int((clocks.now(opt, instant).utcoffset()-reference_offset).total_seconds()/60)
                for _,page,*_ in clocks.windows(data):
                    if data[page+7] in (10,11):
                        current = struct.unpack_from('<h', data, page+18)[0]
                        struct.pack_into('<h', data, page+18, current+delta)
                data = bytes(data)
            else:
                data = assemble([scene])
            # Text programs finish their pages/effects once; live clocks use
            # a fixed display duration, as in native PowerLED program lists.
            entries.append((data, scene['preview_seconds'], 1 if scene['type']=='clock' else 0))
        program = programs.merge(entries)
        extra = {'has_clock': True, 'clock_reference': reference,
                 'clock_signature': timeline_clock_signature(project, instant)}
    else:
        program = assemble(rendered)
    first_options = rendered[0]['options'] if rendered[0]['type'] != 'clock' else {'text': rendered[0]['name'], 'logo_id': rendered[0]['options'].get('logo_id')}
    return program, {'options': first_options, 'name': project['name'], **extra,
                     'scenes': project['scenes'], 'scene_count': len(rendered),
                     'pages': sum(len(s['images']) for s in rendered), 'bytes': len(program),
                     'preview_seconds': sum(s['preview_seconds'] for s in rendered)}


def timeline_clock_signature(value, instant=None):
    import clocks
    from zoneinfo import ZoneInfo
    result = []
    for scene in value.get('scenes', []):
        if scene.get('type') != 'clock':
            continue
        opt = clocks.options(scene['options'])
        local = clocks.now(opt, instant)
        second = local.astimezone(ZoneInfo(opt['second_timezone']))
        result.append([scene['id'], local.date().isoformat() if opt['content'] in ('date','both') else None,
                       int(local.utcoffset().total_seconds()), int(second.utcoffset().total_seconds()) if opt['style']=='world' else None])
    return result


def upload(value, progress=lambda percent, message: None):
    if 'scenes' in value:
        program, result = compile_timeline(value)
    else:
        program, opt, pages = compile_program(value)
        result = {'pages': len(pages), 'bytes': len(program), 'options': opt}
    return upload_program(program, result, progress)


def upload_program(program, result, progress=lambda percent, message: None):
    backup = ROOT / 'data'
    backup.mkdir(exist_ok=True)
    with serial_port() as fd:
        info = probe_fd(fd)
        backup.joinpath('panel-parameters.json').write_text(__import__('json').dumps(info, indent=2))
        progress(2, 'Controller antwortet. Übertragung startet …')
        # Read-only identification handshake captured from this controller's PowerLED session.
        exchange(fd, bytes.fromhex('56100ed31e5e9b16c72a37251f01551a'))
        sequence = 8

        def send(cmd, payload=b'', sub=0):
            nonlocal sequence
            sequence = sequence + 1 if sequence < 250 else 6
            response = exchange(fd, packet(cmd, payload, sub, sequence))
            if len(response) != 12 or response[3:6] != b'\0\0\0':
                raise RuntimeError('Der Controller hat das Programmpaket nicht bestätigt.')

        send(0x14, struct.pack('<II', 1536, len(program)))
        for offset in range(0, len(program), 512):
            send(0x13, struct.pack('<I', offset) + program[offset:offset + 512])
            progress(3 + round(90 * min(offset + 512, len(program)) / len(program)),
                     f"Übertrage {result['pages']} Anzeigeseite(n) …")
        send(0x15, struct.pack('<II', (~sum(program)) & 0xffffffff, len(program)), sub=5)
        progress(96, 'Programm bestätigt. Display startet …')
        time.sleep(1)
        for attempt in range(3):
            try:
                termios.tcflush(fd, termios.TCIFLUSH)
                current = probe_fd(fd)
                if current['raw_parameters'] != info['raw_parameters']:
                    raise RuntimeError('Die Displayparameter haben sich unerwartet geändert.')
                break
            except RuntimeError:
                if attempt == 2:
                    raise
                time.sleep(1)
    backup.joinpath('last-program.bin').write_bytes(program)
    if 'scene_count' in result:
        backup.joinpath('last-timeline-program.bin').write_bytes(program)
    progress(100, 'Vom Controller bestätigt.')
    result['encoder_version'] = ENCODER_VERSION
    return result


def png(image):
    out = io.BytesIO()
    image.save(out, format='PNG')
    return out.getvalue()
