import struct
import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from PIL import Image

import display
import feeds
import logos


def decode(value):
    value = bytearray(value)
    key = value[2]
    for i in range(len(value)):
        if i != 2:
            value[i] ^= ((i + 1 + key) if i % 2 else (i + 5) * key) & 255
    return bytes(value)


class ProtocolTests(unittest.TestCase):
    def test_visible_text_is_vertically_centered(self):
        cases = [dict(text='HALLO', size=14), dict(text='gyp', size=20),
                 dict(text='HALLO\nWELT', size=14),
                 dict(text='GROSS\nklein', size=16, size2=11, split_sizes=True),
                 dict(text='HALLO\nWELT', size=11, frame='solid', frame_width=2, frame_color='blue'),
                 dict(text='ÄÖÜ\ngyp', size=11, background='blue')]
        for case in cases:
            with self.subTest(case=case):
                _, pages = display.render({**case, 'color': 'red', 'mode': 'auto'})
                for image in pages:
                    # The red channel isolates text from blue background/frame.
                    bounds = image.getchannel('R').getbbox()
                    self.assertIsNotNone(bounds)
                    self.assertLessEqual(abs(bounds[1] - (display.HEIGHT - bounds[3])), 1)

    def test_brightness_changes_only_native_brightness_fields_and_reads_back(self):
        raw = bytearray(range(112))
        current = raw.copy()
        current[80:82] = bytes((7, 1))
        before = {'raw_parameters': raw.hex()}
        after = {'raw_parameters': current.hex(), 'brightness': 7}
        with mock.patch.object(display, 'serial_port') as port, mock.patch.object(display, 'probe_fd', side_effect=[before, after]), mock.patch.object(display.termios, 'tcflush'), mock.patch.object(display.time, 'sleep'), mock.patch.object(display, 'exchange', return_value=bytes.fromhex('0c000a000000010000051c00')) as exchange:
            port.return_value.__enter__.return_value = 123
            self.assertEqual(display.set_brightness(7), after)
            command = decode(exchange.call_args.args[1])
            self.assertEqual(command[3:6], bytes((0x20, 2, 0)))
            self.assertEqual(command[8:-4], current)
        for invalid in (-1, 16, True, 2.5, '7'):
            with self.assertRaises(ValueError):
                display.set_brightness(invalid)

    def test_frame_background_and_content_reservation(self):
        value = {'text': 'TEST', 'size': 14, 'mode': 'auto', 'color': 'white', 'background': 'blue', 'frame': 'solid', 'frame_color': 'red', 'frame_width': 2}
        measured = display.layout(value)
        self.assertEqual(measured['content_height'], 26)
        self.assertEqual(measured['text_width'], 122)
        self.assertNotIn('ticker', measured['allowed_modes'])
        opt, images = display.render(value)
        image = images[0]
        self.assertEqual(image.getpixel((0, 0)), (255, 0, 0))
        self.assertEqual(image.getpixel((127, 31)), (255, 0, 0))
        self.assertEqual(image.getpixel((2, 2)), (0, 0, 255))
        self.assertEqual(image.getpixel((3, 3)), (0, 0, 255))
        self.assertIn((255, 255, 255), set(image.get_flattened_data()))
        _, timeline = display.compile_timeline({'scenes': [{'id': 'framed', 'options': value}]})
        self.assertEqual(timeline['scenes'][0]['options']['background'], 'blue')
        self.assertEqual(timeline['scenes'][0]['options']['frame'], 'solid')

    def test_frame_patterns_and_ticker_background(self):
        for pattern in ('dashed', 'dots'):
            _, images = display.render({'text': 'Hi', 'frame': pattern, 'background': 'blue', 'frame_color': 'green'})
            edge = {images[0].getpixel((x, 0)) for x in range(128)}
            self.assertEqual(edge, {(0, 0, 255), (0, 255, 0)})
        _, images = display.render({'text': 'A long scrolling text', 'mode': 'ticker', 'background': 'blue'})
        self.assertTrue(all(im.getpixel((0, 0)) == (0, 0, 255) for im in images))

    def test_query_matches_hardware_capture(self):
        self.assertEqual(display.packet(0x12).hex(), '240a081e480e59106a145714')

    def test_large_packet_length_and_checksum(self):
        payload = bytes(range(256)) * 2
        p = decode(display.packet(0x13, payload, sequence=249))
        self.assertEqual(struct.unpack_from('<H', p)[0], len(p))
        self.assertEqual(p[8:-4], payload)
        self.assertEqual(sum(p[:-2]) & 65535, int.from_bytes(p[-2:], 'little'))

    def test_raster_plane_order_and_pixel_endianness(self):
        im = Image.new('RGB', (128, 32))
        im.putpixel((0, 0), (255, 0, 0))
        im.putpixel((7, 0), (255, 255, 0))
        im.putpixel((127, 31), (0, 255, 0))
        im.putpixel((1, 0), (0, 0, 255))
        pixels = display.raster(im)
        self.assertEqual(pixels[0], 129)
        self.assertEqual(pixels[512], 2)
        self.assertEqual(pixels[1024], 128)
        self.assertEqual(pixels[1535], 128)

    def test_page_link_chain_and_no_panel_config_changes(self):
        p, opt, pages = display.compile_program({'text': 'Erste Seite\nZweite Seite\nDritte Seite', 'size': 24})
        self.assertGreater(len(pages), 1)
        template = display.ROOT.joinpath('image-template.bin').read_bytes()
        self.assertEqual(p[:576], template[:576])
        offset = 576
        for i in range(len(pages)):
            self.assertEqual(p[offset + 6:offset + 8], b'\x01\x02')
            next_offset = struct.unpack_from('<I', p, offset)[0]
            self.assertEqual(next_offset, offset + 1560 if i < len(pages) - 1 else 0)
            offset += 1560
        self.assertEqual(offset, len(p))

    def test_all_seven_colors_use_the_verified_rbg_planes(self):
        for name, rgb in display.COLORS.items():
            with self.subTest(color=name):
                image = Image.new('RGB', (128, 32), rgb)
                packed = display.raster(image)
                for plane, channel in enumerate((0, 2, 1)):
                    self.assertEqual(packed[plane * 512:(plane + 1) * 512],
                                     bytes([255 if rgb[channel] else 0]) * 512)

    def test_umlauts_and_ticker_stay_within_panel(self):
        opt, pages = display.render({'text': 'Grüße aus Lübben – Straße & Wetter', 'mode': 'ticker'})
        self.assertGreater(len(pages), 1)
        self.assertTrue(all(im.size == (128, 32) for im in pages))
        self.assertTrue(any(im.getbbox() for im in pages))


class LayoutTests(unittest.TestCase):
    def test_every_effect_matches_a_real_powerled_capture(self):
        fixture = json.loads(display.ROOT.joinpath('native-effect-reference.json').read_text())
        records = {r['gui_action']: r for r in fixture['records']}
        gui = {'direct':1,'left':4,'right':6,'up':7,'down':8,'rain':10,'fountain':11,
               'flash':12,'laser_left':16,'laser_right':17,'open_h':32,'open_v':34,
               'shutter_h':36,'shutter_v':37,'mosaic':42,'diamond':43,'fall':45,
               'ticker_left':3,'ticker_right':5}
        for key, gui_action in gui.items():
            with self.subTest(effect=key):
                data, opt, _ = display.compile_program({'text':'Effekt','mode':'ticker' if key.startswith('ticker_') else 'static','effect':key,'speed':6})
                captured = bytes.fromhex(records[gui_action]['header'])
                self.assertEqual(data[584:587], captured[8:11])
                self.assertNotEqual(data[585], 0)
        self.assertEqual(display.options({'text':'Alt','effect':'random'})['effect'], 'direct')

    def test_auto_uses_static_only_for_a_complete_fitting_text(self):
        short = display.layout({'text': 'Hallo', 'mode': 'auto', 'size': 14})
        self.assertTrue(short['current']['fits'])
        self.assertEqual(short['effective_mode'], 'static')
        long = display.layout({'text': 'W' * 100, 'mode': 'auto', 'size': 14})
        self.assertNotIn('static', long['allowed_modes'])
        self.assertEqual(long['effective_mode'], 'ticker')
        with self.assertRaises(ValueError):
            display.compile_program({'text': 'W' * 100, 'mode': 'static', 'size': 14})

    def test_auto_preserves_all_multiline_text_as_pages(self):
        text = '\n'.join(['Erste Nachricht', 'Zweite Nachricht', 'Dritte Nachricht'])
        info = display.layout({'text': text, 'mode': 'auto', 'size': 14})
        self.assertEqual(info['effective_mode'], 'pages')
        options, pages = display.render({'text': text, 'mode': 'auto', 'size': 14})
        self.assertEqual(len(pages), info['current']['pages'])

    def test_font_fit_is_measured_for_each_actual_size(self):
        info = display.layout({'text': 'Hallo Welt!', 'mode': 'static', 'size': 14})
        fits = {p['size']: p['fits'] for p in info['sizes']}
        self.assertTrue(fits[12])
        self.assertFalse(fits[28])

    def test_effect_codes_follow_powerled_action_catalog(self):
        for effect, native_code in [('rain', 9), ('fountain', 10), ('flash', 11), ('mosaic', 41), ('diamond', 42)]:
            with self.subTest(effect=effect):
                data, opt, pages = display.compile_program({'text': 'Effekt', 'mode': 'static', 'effect': effect})
                self.assertEqual(data[576 + 8], 0)
                self.assertEqual(data[576 + 9], native_code)
                self.assertEqual(opt['effect'], effect)

    def test_ticker_has_only_compatible_effects_and_reverses_strip_order(self):
        value = {'text': 'Ein langer Text mit allen Buchstaben', 'mode': 'ticker'}
        opt, left = display.render({**value, 'effect': 'rain'})
        self.assertEqual(opt['effect'], 'ticker_left')
        opt, right = display.render({**value, 'effect': 'ticker_right'})
        self.assertEqual([im.tobytes() for im in right], [im.tobytes() for im in reversed(left)])
        data, _, _ = display.compile_program({**value, 'effect': 'ticker_right'})
        self.assertEqual(data[584], 0)
        self.assertEqual(data[585], 5)


class TimelineTests(unittest.TestCase):
    def test_scenes_preserve_order_effects_durations_and_pixels(self):
        scenes = [{'id':'a','name':'Anfang','options':{'text':'A','color':'red','mode':'static','effect':'direct','duration':2}},
                  {'id':'b','name':'Mitte','options':{'text':'B','color':'green','mode':'static','effect':'rain','duration':4}},
                  {'id':'c','name':'Ende','options':{'text':'C','color':'blue','mode':'static','effect':'flash','duration':3}}]
        rendered = display.render_timeline({'scenes':scenes})
        data, result = display.compile_timeline({'name':'Meine Folge','scenes':scenes})
        self.assertEqual(result['scene_count'], 3)
        self.assertEqual(result['preview_seconds'], 9)
        self.assertEqual([s['id'] for s in result['scenes']], ['a','b','c'])
        offset = 576
        for i, (effect, delay) in enumerate([(1,20),(9,40),(11,30)]):
            self.assertEqual(data[offset+8], 0)
            self.assertEqual(data[offset+9], effect)
            self.assertEqual(struct.unpack_from('<H',data,offset+4)[0],delay)
            self.assertEqual(struct.unpack_from('<I',data,offset+20)[0],delay)
            self.assertEqual(data[offset+24:offset+1560],display.raster(rendered[i]['images'][0]))
            next_offset=struct.unpack_from('<I',data,offset)[0]
            self.assertEqual(next_offset,offset+1560 if i<2 else 0)
            offset+=1560

    def test_multiple_pages_of_a_scene_stay_together(self):
        scenes = [{'id':'long','options':{'text':'Erste\nZweite\nDritte','size':24,'mode':'pages','effect':'mosaic'}},
                  {'id':'last','options':{'text':'Ende','mode':'static','effect':'direct'}}]
        data, result=display.compile_timeline({'scenes':scenes})
        self.assertEqual(result['pages'],4)
        self.assertEqual([data[576+i*1560+9] for i in range(4)],[41,41,41,1])

    def test_invalid_or_oversized_sequences_are_rejected(self):
        valid={'id':'x','options':{'text':'Text'}}
        for scenes in ([],[valid]*2,[{'id':str(i),'options':{'text':'x'}} for i in range(31)]):
            with self.subTest(count=len(scenes)),self.assertRaises(ValueError):
                display.compile_timeline({'scenes':scenes})
        with mock.patch.object(display,'MAX_PAGES',2),self.assertRaises(ValueError):
            display.compile_timeline({'scenes':[{'id':str(i),'options':{'text':'x','mode':'static'}} for i in range(3)]})


class MixedFontTests(unittest.TestCase):
    def test_ten_and_eleven_pixels_are_supported(self):
        for size in (10, 11):
            with self.subTest(size=size):
                opt, images = display.render({'text': 'Kleine Schrift', 'size': size, 'mode': 'auto'})
                self.assertEqual(opt['size'], size)
                self.assertTrue(images[0].getbbox())

    def test_mixed_lines_fit_together_when_uniform_large_lines_do_not(self):
        value = {'text': 'GROSS\nkleiner Text', 'size': 16, 'size2': 11, 'split_sizes': True, 'mode': 'auto'}
        info = display.layout(value)
        self.assertTrue(info['current']['fits'])
        self.assertEqual(info['current']['height'], 29)
        self.assertEqual(info['effective_mode'], 'static')
        self.assertNotIn('ticker', info['allowed_modes'])
        self.assertFalse(display.layout({**value, 'split_sizes': False})['current']['fits'])

    def test_combined_height_rejects_clipped_static_and_pages_all_lines(self):
        value = {'text': 'Oben\nunten', 'size': 24, 'size2': 14, 'split_sizes': True, 'mode': 'auto'}
        info = display.layout(value)
        self.assertNotIn('static', info['allowed_modes'])
        self.assertEqual(info['effective_mode'], 'pages')
        _, images = display.render(value)
        self.assertEqual(len(images), 2)
        with self.assertRaises(ValueError):
            display.compile_program({**value, 'mode': 'static'})

    def test_wrapped_first_text_line_keeps_its_font(self):
        lines = display.styled_lines('Ein sehr langer erster Text\nzweite', 20, 10, True, 92)
        self.assertGreater(len(lines), 2)
        self.assertEqual(lines[-1]['size'], 10)
        self.assertTrue(all(line['size'] == 20 for line in lines[:-1]))

    def test_actual_raster_contains_two_different_glyph_heights(self):
        _, images = display.render({'text': 'MMMM\nMMMM', 'size': 16, 'size2': 10,
                                    'split_sizes': True, 'mode': 'static'})
        image = images[0]
        runs = []
        for y in range(32):
            if image.crop((0, y, 128, y + 1)).getbbox():
                if runs and runs[-1][-1] == y - 1:
                    runs[-1].append(y)
                else:
                    runs.append([y])
        self.assertEqual(len(runs), 2)
        self.assertGreater(len(runs[0]), len(runs[1]))


class LogoTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(logos, 'ROOT', Path(self.folder.name))
        self.patch.start()
        image = Image.new('RGBA', (64, 64))
        image.paste((255, 0, 0, 255), (8, 8, 56, 56))
        out = io.BytesIO()
        image.save(out, format='PNG')
        self.logo = logos.store(base64.b64encode(out.getvalue()).decode(), 'test.png')

    def tearDown(self):
        self.patch.stop()
        self.folder.cleanup()

    def test_upload_crops_transparent_border_and_persists_normalized_png(self):
        self.assertEqual((self.logo['width'], self.logo['height']), (48, 48))
        with Image.open(logos.image_path(self.logo['id'])) as image:
            self.assertEqual(image.mode, 'RGBA')

    def test_logo_reserves_actual_width_and_disables_unsupported_ticker(self):
        value = {'text': 'ABC ' * 12, 'mode': 'auto', 'size': 14}
        plain = display.layout(value)
        info = display.layout({**value, 'logo_id': self.logo['id']})
        self.assertEqual(info['text_width'], 92)
        self.assertGreater(info['current']['lines'], plain['current']['lines'])
        self.assertNotIn('ticker', info['allowed_modes'])
        self.assertEqual(info['effective_mode'], 'pages')

    def test_logo_only_is_centered_without_distortion(self):
        opt, pages = display.render({'text': '', 'logo_id': self.logo['id'], 'mode': 'auto',
                                     'logo_position': 'alone', 'logo_width': 128})
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].getbbox(), (48, 0, 80, 32))

    def test_right_logo_and_gap_do_not_overwrite_text(self):
        opt, pages = display.render({'text': 'Hallo', 'logo_id': self.logo['id'],
                                     'logo_position': 'right', 'mode': 'auto'})
        self.assertEqual(pages[0].getpixel((127, 16)), (255, 0, 0))
        self.assertIsNone(pages[0].crop((92, 0, 96, 32)).getbbox())

    def test_single_color_and_inversion_preserve_alpha(self):
        value = {'text': '', 'logo_id': self.logo['id'], 'mode': 'auto'}
        opt, pages = display.render({**value, 'logo_style': 'solid', 'color': 'green'})
        self.assertEqual(pages[0].getpixel((64, 16)), (0, 255, 0))
        opt, pages = display.render({**value, 'logo_style': 'invert'})
        self.assertEqual(pages[0].getpixel((64, 16)), (0, 255, 255))

    def test_invalid_files_and_paths_are_rejected(self):
        with self.assertRaises(ValueError):
            logos.store(base64.b64encode(b'<script>invalid</script>').decode(), 'logo.png')
        with self.assertRaises(ValueError):
            logos.image_path('../outside')
        image = Image.new('RGBA', (10, 10))
        out = io.BytesIO(); image.save(out, format='PNG')
        with self.assertRaises(ValueError):
            logos.store(base64.b64encode(out.getvalue()).decode(), 'empty.png')


class FeedTests(unittest.TestCase):
    def test_rss_titles_unescaped_deduplicated(self):
        result = feeds.parse(b'<rss><channel><title>Quelle</title><item><title>A &amp; B</title></item><item><title>A &amp; B</title></item></channel></rss>')
        self.assertEqual(result['title'], 'Quelle')
        self.assertEqual(result['items'], [{'title': 'A & B', 'date': '', 'link': ''}])

    def test_atom_namespace_and_link(self):
        result = feeds.parse(b'<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom</title><entry><title>Neu</title><link href="https://example.org/news"/><updated>2026-10-31</updated></entry></feed>')
        self.assertEqual(result['items'][0]['link'], 'https://example.org/news')

    def test_entities_and_non_feeds_rejected(self):
        for data in (b'<!DOCTYPE foo><rss/>', b'<html><title>No</title></html>', b'not xml'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                feeds.parse(data)

    def test_private_feed_url_rejected(self):
        with self.assertRaises(ValueError):
            feeds.validate_url('http://127.0.0.1/admin')
        with self.assertRaises(ValueError):
            feeds.validate_url('file:///etc/passwd')


if __name__ == '__main__':
    unittest.main()
