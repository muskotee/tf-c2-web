#!/usr/bin/env python3
import base64
import datetime
import json
import logging
import os
from pathlib import Path
import queue
import re
import secrets
import signal
import socket
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import display
import feeds
import logos
import clocks

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)
DB = DATA / 'control.sqlite3'
PORT = int(os.environ.get('TF_WEB_PORT', '8080'))
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')


def connection():
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    return db


def init():
    with connection() as db:
        db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS presets(id TEXT PRIMARY KEY,name TEXT NOT NULL,options TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS feeds(id TEXT PRIMARY KEY,name TEXT NOT NULL,url TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1,items TEXT NOT NULL DEFAULT '[]',updated REAL,error TEXT);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,created REAL,kind TEXT,message TEXT);
        CREATE TABLE IF NOT EXISTS logos(id TEXT PRIMARY KEY,name TEXT NOT NULL,width INTEGER,height INTEGER,created REAL);
        CREATE TABLE IF NOT EXISTS timelines(id TEXT PRIMARY KEY,name TEXT NOT NULL,scenes TEXT NOT NULL,updated REAL);
        ''')


def setting(key, default=None):
    with connection() as db:
        row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else default


def save_setting(key, value):
    with connection() as db:
        db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (key, json.dumps(value)))


def event(kind, message):
    with connection() as db:
        db.execute('INSERT INTO events(created,kind,message) VALUES(?,?,?)', (time.time(), kind, message))
        db.execute('DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 150)')


DEFAULT_AUTO = {'enabled': False, 'interval': 15, 'headlines': 5, 'mode': 'pages',
                'size': 14, 'color': 'red', 'duration': 5, 'speed': 10, 'next': 0}


class Controller:
    def __init__(self):
        self.lock = threading.Lock()
        self.hardware_lock = threading.Lock()
        self.jobs = queue.Queue(maxsize=3)
        self.job = {'state': 'idle', 'progress': 0, 'message': 'Bereit.'}
        self.device = {'connected': False, 'checking': True, 'width': 128, 'height': 32,
                       'baud': 57600, 'firmware': 'TF-C2 0.5.9'}
        self.stopping = threading.Event()
        clock = setting('clock', {})
        migrate_clock = None
        if clock.get('enabled') and (clock.get('engine') != 2 or (clock.get('style') == 'analog' and clock.get('station_layout') != 2)):
            migrate_clock = clocks.options({**clock, 'style': clock.get('style') if clock.get('style') in clocks.SUPPORTED_STYLES else 'digital'})
            save_setting('clock', {**clock, 'enabled': False})
        threading.Thread(target=self.worker, daemon=True).start()
        threading.Thread(target=self.scheduler, daemon=True).start()
        if migrate_clock:
            self.enqueue('clock', migrate_clock)

    def update(self, **value):
        with self.lock:
            self.job.update(value)

    def enqueue(self, kind, value):
        identifier = secrets.token_hex(6)
        with self.lock:
            if self.job['state'] in ('queued', 'running'):
                raise ValueError('Eine Übertragung läuft bereits. Bitte kurz warten.')
            self.job = {'id': identifier, 'state': 'queued', 'progress': 0,
                        'message': 'Auftrag wird vorbereitet …', 'kind': kind}
            self.jobs.put_nowait((identifier, kind, value))
        return {'id': identifier}

    def refresh(self, selected=None):
        with connection() as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM feeds ORDER BY rowid')]
        if selected:
            rows = [r for r in rows if r['id'] == selected]
            if not rows:
                raise ValueError('Feed nicht gefunden.')
        else:
            rows = [r for r in rows if r['enabled']]
        combined, errors = [], []
        for row in rows:
            try:
                result = feeds.fetch(row['url'])
                with connection() as db:
                    db.execute('UPDATE feeds SET items=?,updated=?,error=NULL WHERE id=?',
                               (json.dumps(result['items']), time.time(), row['id']))
                combined.append((row['name'], result['items']))
            except Exception as exc:
                errors.append(row['name'] + ': ' + str(exc))
                with connection() as db:
                    db.execute('UPDATE feeds SET error=? WHERE id=?', (str(exc), row['id']))
        if errors:
            event('error', ' · '.join(errors))
        if not combined:
            raise ValueError('Kein aktiver Feed lieferte Schlagzeilen. ' + ' · '.join(errors))
        return combined

    def rss_options(self, value):
        auto = {**DEFAULT_AUTO, **setting('auto', {})}
        groups = self.refresh(value.get('feed_id'))
        # Interleave sources so the first feed cannot occupy the whole display playlist.
        headlines = []
        for i in range(30):
            for name, items in groups:
                if i < len(items):
                    headlines.append(items[i]['title'][:250])
            if len(headlines) >= auto['headlines']:
                break
        text = '\n'.join(headlines[:auto['headlines']])[:2000]
        return {**auto, 'text': text, 'align': 'left'}

    def worker(self):
        while not self.stopping.is_set():
            try:
                identifier, kind, value = self.jobs.get(timeout=1)
            except queue.Empty:
                continue
            self.update(state='running', message='Bereite Anzeige vor …', progress=1)
            try:
                if kind == 'refresh':
                    self.refresh(value.get('feed_id'))
                    self.update(state='done', progress=100, message='Feeds wurden aktualisiert.')
                    continue
                if kind == 'brightness':
                    with self.hardware_lock:
                        info = display.set_brightness(value['level'])
                    save_setting('brightness', {'level': info['brightness'], 'updated': time.time()})
                    with self.lock:
                        self.device = {**info, 'checked': time.time(), 'checking': False}
                    self.update(state='done', progress=100, message=f"Helligkeit: Stufe {info['brightness'] + 1} von 16, vom Display bestätigt.")
                    continue
                if kind == 'probe':
                    with self.hardware_lock:
                        info = display.probe()
                    with self.lock:
                        self.device = {**info, 'checked': time.time(), 'checking': False}
                    self.update(state='done', progress=100, message='Display antwortet.')
                    continue
                if kind in ('clock', 'clock_sync', 'clock_stop'):
                    self.clock_job(kind, value)
                    continue
                clock = {**clocks.DEFAULT, **setting('clock', {})}
                if clock['enabled']:
                    clock['enabled'] = False
                    save_setting('clock', clock)
                if kind == 'rss':
                    self.update(message='Lade RSS-Schlagzeilen …')
                    value = self.rss_options(value)
                    previous = setting('last')
                    if (previous and previous['source'] == 'rss'
                            and previous.get('encoder_version') == display.ENCODER_VERSION
                            and previous['options'] == display.options(value)):
                        self.update(state='done', progress=100, message='Schlagzeilen unverändert. Das Display spielt weiter.')
                        event('info', 'RSS geprüft: Schlagzeilen unverändert.')
                        continue
                else:
                    auto = {**DEFAULT_AUTO, **setting('auto', {})}
                    auto['enabled'] = False
                    save_setting('auto', auto)
                with self.hardware_lock:
                    result = display.upload(value, lambda p, m: self.update(progress=p, message=m))
                save_setting('last', {**result, 'source': kind, 'sent': time.time()})
                with self.lock:
                    self.device.update(connected=True, checking=False, checked=time.time(), error=None)
                self.update(state='done', progress=100,
                            message=(f"Timeline gesendet: {result['scene_count']} Szenen, {result['pages']} Seiten, vom Display bestätigt."
                                     if kind == 'timeline' else f"Gesendet: {result['pages']} Seite(n), vom Display bestätigt."))
                event('success', f"{'Timeline' if kind == 'timeline' else 'RSS' if kind == 'rss' else 'Text'} gesendet: {result['pages']} Seite(n).")
            except Exception as exc:
                logging.exception('Auftrag %s fehlgeschlagen', kind)
                self.update(state='error', message=str(exc), progress=0)
                event('error', str(exc))
            finally:
                self.jobs.task_done()

    def clock_job(self, kind, value):
        opt = clocks.options(setting('clock', {}) if kind == 'clock_sync' else value)
        if kind == 'clock_stop':
            previous = setting('clock_previous') or {}
            last = previous.get('last')
            with self.hardware_lock:
                if last and last['source'] == 'timeline':
                    result = display.upload({'name': last['name'], 'scenes': last['scenes']})
                else:
                    result = display.upload(last['options'] if last and last['source'] != 'clock' else {'text': 'Uhr beendet', 'mode': 'static'})
            save_setting('last', {**result, 'source': last['source'] if last else 'text', 'sent': time.time()})
            save_setting('clock', {**opt, 'enabled': False})
            if previous.get('auto'):
                save_setting('auto', {**previous['auto'], 'next': 0})
            self.update(state='done', progress=100, message='Vorherige Anzeige wiederhergestellt.')
            return
        if kind == 'clock':
            previous = setting('clock', {})
            if not previous.get('enabled') and (setting('last') or {}).get('source') != 'clock':
                save_setting('clock_previous', {'last': setting('last'), 'auto': setting('auto', DEFAULT_AUTO)})
            program, opt = clocks.compile_program(opt)
            with self.hardware_lock:
                result = display.upload_program(program, {'pages': len(clocks.windows(program)), 'bytes': len(program),
                    'options': {'text': clocks.STYLES[opt['style']], 'logo_id': None}},
                    lambda p,m: self.update(progress=p,message=m))
                info = clocks.sync(opt)
            save_setting('auto', {**DEFAULT_AUTO, **setting('auto', {}), 'enabled': False})
            save_setting('last', {**result, 'source': 'clock', 'sent': time.time(), 'clock': opt})
        else:
            if not opt['enabled']:
                self.update(state='done',progress=100,message='Uhr ist nicht aktiv.')
                return
            with self.hardware_lock:
                if opt['style'] == 'world':
                    program, _ = clocks.compile_program(opt)
                    delta = int.from_bytes(program[clocks.windows(program)[1][1]+18:clocks.windows(program)[1][1]+20], 'little', signed=True)
                    if setting('clock', {}).get('world_offset') != delta:
                        display.upload_program(program, {'pages': 2, 'bytes': len(program), 'options': {'text': 'Weltzeit'}})
                info = clocks.sync(opt)
        extra = {}
        if opt['style'] == 'analog':
            extra['station_layout'] = 2
        if opt['style'] == 'world':
            program, _ = clocks.compile_program(opt)
            page = clocks.windows(program)[1][1]
            extra['world_offset'] = int.from_bytes(program[page+18:page+20], 'little', signed=True)
        save_setting('clock', {**opt, **extra, 'enabled': True, 'engine': 2, 'synced': time.time()})
        with self.lock:
            self.device = {**info, 'checked': time.time(), 'checking': False}
        self.update(state='done', progress=100, message='Uhrprogramm und Zeitabgleich vom Controller bestätigt.')

    def scheduler(self):
        last_probe = 0
        while not self.stopping.wait(2):
            with self.lock:
                busy = self.job['state'] in ('queued', 'running')
            if busy:
                continue
            now = time.time()
            if now - last_probe > 60:
                last_probe = now
                try:
                    with self.hardware_lock:
                        info = display.probe()
                    with self.lock:
                        self.device = {**info, 'checking': False, 'checked': now}
                except Exception as exc:
                    with self.lock:
                        self.device.update(connected=False, checking=False, error=str(exc), checked=now)
            auto = {**DEFAULT_AUTO, **setting('auto', {})}
            clock = {**clocks.DEFAULT, **setting('clock', {})}
            if clock['enabled']:
                if now >= clock.get('next_sync', clock.get('synced', 0) + 60):
                    # Retry failures at a bounded rate; native RTC keeps ticking.
                    clock['next_sync'] = now + 60
                    save_setting('clock', clock)
                    try:
                        self.enqueue('clock_sync', {})
                    except ValueError:
                        pass
                continue
            if auto['enabled'] and auto['next'] <= now:
                auto['next'] = now + auto['interval'] * 60
                save_setting('auto', auto)
                try:
                    self.enqueue('rss', {})
                except ValueError:
                    pass

    def snapshot(self):
        with self.lock:
            device, job = dict(self.device), dict(self.job)
        device.pop('raw_parameters', None)
        with connection() as db:
            sources = [dict(r) for r in db.execute('SELECT * FROM feeds ORDER BY rowid')]
            presets = [dict(r) for r in db.execute('SELECT * FROM presets ORDER BY name')]
            events = [dict(r) for r in db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 40')]
            images = [dict(r) for r in db.execute('SELECT * FROM logos ORDER BY created DESC')]
            projects = [dict(r) for r in db.execute('SELECT * FROM timelines ORDER BY updated DESC')]
        for source in sources:
            source['items'] = json.loads(source['items'])
            source['enabled'] = bool(source['enabled'])
        for preset in presets:
            preset['options'] = json.loads(preset['options'])
        for image in images:
            image['url'] = '/api/logo/' + image['id'] + '.png'
        for project in projects:
            project['scene_count'] = len(json.loads(project.pop('scenes')))
        return {'device': device, 'job': job, 'feeds': sources, 'presets': presets,
                'events': events, 'logos': images, 'last': setting('last'), 'auto': {**DEFAULT_AUTO, **setting('auto', {})},
                'timelines': projects, 'clock': {**clocks.DEFAULT, **setting('clock', {})},
                'clock_supported_styles': list(clocks.SUPPORTED_STYLES),
                'effects': [{'value': k, 'label': v[1], 'ticker': k.startswith('ticker_')} for k, v in display.EFFECTS.items()],
                'server_time': time.time()}


class Handler(BaseHTTPRequestHandler):
    server_version = 'TF-C2-Web/1.0'

    def log_message(self, fmt, *args):
        if args and str(args[0]).startswith('POST'):
            logging.info(fmt, *args)

    def host_ok(self):
        try:
            host = urlsplit('http://' + self.headers.get('Host', '')).hostname
            return host in self.server.allowed_hosts
        except ValueError:
            return False

    def reply(self, data, status=200, content='application/json; charset=utf-8'):
        if isinstance(data, (dict, list)):
            data = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if not self.host_ok():
            return self.reply({'error': 'Unzulässiger Hostname.'}, 403)
        path = urlsplit(self.path).path
        if path == '/api/state':
            return self.reply(self.server.controller.snapshot())
        if path == '/api/health':
            return self.reply({'ok': True})
        if re.fullmatch('/api/logo/[0-9a-f]{64}\\.png', path):
            try:
                return self.reply(logos.image_path(path[10:-4]).read_bytes(), content='image/png')
            except ValueError:
                return self.reply({'error': 'Logo nicht gefunden.'}, 404)
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                 '/studio.js': ('studio.js', 'text/javascript; charset=utf-8'),
                 '/clock.js': ('clock.js', 'text/javascript; charset=utf-8'),
                 '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if path in files:
            filename, content = files[path]
            return self.reply((ROOT / 'static' / filename).read_bytes(), content=content)
        return self.reply({'error': 'Nicht gefunden.'}, 404)

    def do_POST(self):
        if not self.host_ok():
            return self.reply({'error': 'Unzulässiger Hostname.'}, 403)
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            return self.reply({'error': 'Anfrage von einer fremden Webseite blockiert.'}, 403)
        if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
            return self.reply({'error': 'JSON erwartet.'}, 415)
        try:
            path = urlsplit(self.path).path
            length = int(self.headers.get('Content-Length', '0'))
            limit = 3 * 1024 * 1024 if path == '/api/logo/upload' else 262144 if path.startswith('/api/timeline/') else 65536
            if not 0 < length <= limit:
                raise ValueError('Ungültige Anfragegröße.')
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise ValueError('JSON-Objekt erwartet.')
            controller = self.server.controller
            if path == '/api/clock/preview':
                image, opt = clocks.preview(value)
                return self.reply({'image': base64.b64encode(display.png(image)).decode(), 'options': opt,
                                   'time': clocks.now(opt).isoformat()})
            if path == '/api/clock/start':
                opt = clocks.options(value)
                clocks.compile_program(opt)
                return self.reply(controller.enqueue('clock', opt), 202)
            if path == '/api/clock/stop':
                if not setting('clock', {}).get('enabled'):
                    raise ValueError('Die Uhr ist nicht aktiv.')
                return self.reply(controller.enqueue('clock_stop', setting('clock', {})), 202)
            controller = self.server.controller
            if path == '/api/timeline/preview':
                scenes = display.render_timeline(value)
                return self.reply({'name': display.timeline_project(value, scenes)['name'],
                                   'scenes': [{k: v for k, v in scene.items() if k != 'images'} |
                                              {'pages': [base64.b64encode(display.png(im)).decode() for im in scene['images']]}
                                              for scene in scenes],
                                   'page_count': sum(len(s['images']) for s in scenes),
                                   'preview_seconds': sum(s['preview_seconds'] for s in scenes)})
            if path == '/api/timeline/save':
                project = display.timeline_project(value)
                identifier = value.get('id') or secrets.token_hex(8)
                if not isinstance(identifier, str) or not re.fullmatch('[A-Za-z0-9_-]{1,64}', identifier):
                    raise ValueError('Ungültige Projekt-ID.')
                with connection() as db:
                    db.execute('INSERT OR REPLACE INTO timelines VALUES(?,?,?,?)',
                               (identifier, project['name'], json.dumps(project['scenes']), time.time()))
                return self.reply({'id': identifier, **project})
            if path == '/api/timeline/load':
                with connection() as db:
                    row = db.execute('SELECT * FROM timelines WHERE id=?', (str(value.get('id', '')),)).fetchone()
                if not row:
                    raise ValueError('Timeline nicht gefunden.')
                return self.reply({'id': row['id'], 'name': row['name'], 'scenes': json.loads(row['scenes'])})
            if path == '/api/timeline/delete':
                with connection() as db:
                    db.execute('DELETE FROM timelines WHERE id=?', (str(value.get('id', '')),))
                return self.reply({'ok': True})
            if path == '/api/timeline/send':
                display.compile_timeline(value)
                return self.reply(controller.enqueue('timeline', value), 202)
            if path == '/api/logo/upload':
                image = logos.store(value.get('data'), value.get('name', 'Logo'))
                with connection() as db:
                    db.execute('''INSERT INTO logos(id,name,width,height,created) VALUES(?,?,?,?,?)
                      ON CONFLICT(id) DO UPDATE SET name=excluded.name''',
                               (image['id'], image['name'], image['width'], image['height'], time.time()))
                return self.reply(image, 201)
            if path == '/api/preview':
                opt = display.options(value)
                measured = display.layout(opt)
                adjusted = False
                adjustments = []
                if not measured['allowed_modes']:
                    candidates = [p for p in measured['sizes'] if p['pages_allowed'] or p['ticker_allowed']]
                    if candidates:
                        opt['size'] = max((p['size'] for p in candidates if p['size'] <= opt['size']), default=candidates[0]['size'])
                        measured = display.layout(opt)
                        adjustments.append(f"Schriftgröße auf {opt['size']} px angepasst.")
                if opt['mode'] not in measured['allowed_modes']:
                    opt['mode'] = 'auto'
                    adjusted = True
                    adjustments.append('Auf Automatik umgestellt, damit der vollständige Text angezeigt wird.')
                opt, images = display.render(opt)
                return self.reply({'pages': [base64.b64encode(display.png(im)).decode() for im in images],
                                   'options': opt, 'layout': display.layout(opt), 'adjusted': adjusted,
                                   'adjustments': adjustments,
                                   'bytes': 576 + len(images) * 1560})
            if path == '/api/send':
                display.compile_program(value)
                return self.reply(controller.enqueue('text', value), 202)
            if path == '/api/brightness':
                level = value.get('level')
                if type(level) is not int or not 0 <= level <= 15:
                    raise ValueError('Bitte eine Helligkeitsstufe von 1 bis 16 wählen.')
                return self.reply(controller.enqueue('brightness', {'level': level}), 202)
            if path == '/api/probe':
                return self.reply(controller.enqueue('probe', {}), 202)
            if path == '/api/rss/send':
                return self.reply(controller.enqueue('rss', value), 202)
            if path == '/api/rss/refresh':
                return self.reply(controller.enqueue('refresh', value), 202)
            if path == '/api/feed/check':
                return self.reply(feeds.fetch(value.get('url', '')))
            if path == '/api/feed/save':
                name = str(value.get('name', '')).strip()[:80]
                url = feeds.validate_url(value.get('url', ''))
                identifier = value.get('id') or secrets.token_hex(6)
                if not isinstance(identifier, str) or len(identifier) > 40 or not name:
                    raise ValueError('Bitte einen Namen und eine Feed-URL eingeben.')
                with connection() as db:
                    db.execute('''INSERT INTO feeds(id,name,url,enabled) VALUES(?,?,?,?)
                      ON CONFLICT(id) DO UPDATE SET name=excluded.name,url=excluded.url,
                      enabled=excluded.enabled,items=CASE WHEN feeds.url=excluded.url THEN feeds.items ELSE '[]' END,
                      updated=CASE WHEN feeds.url=excluded.url THEN feeds.updated ELSE NULL END,error=NULL''',
                               (identifier, name, url, int(bool(value.get('enabled', True)))))
                return self.reply({'id': identifier})
            if path in ('/api/feed/delete', '/api/preset/delete'):
                table = 'feeds' if 'feed/' in path else 'presets'
                with connection() as db:
                    db.execute(f'DELETE FROM {table} WHERE id=?', (str(value.get('id', '')),))
                return self.reply({'ok': True})
            if path == '/api/preset/save':
                name = str(value.get('name', '')).strip()[:80]
                opt = display.options(value)
                identifier = value.get('id') or secrets.token_hex(6)
                if not name:
                    raise ValueError('Bitte einen Namen für die Vorlage eingeben.')
                with connection() as db:
                    db.execute('INSERT OR REPLACE INTO presets VALUES(?,?,?)',
                               (identifier, name, json.dumps(opt)))
                return self.reply({'id': identifier})
            if path == '/api/rss/settings':
                auto = {**DEFAULT_AUTO, **setting('auto', {})}
                auto.update({k: value[k] for k in ('enabled', 'interval', 'headlines', 'mode', 'size', 'color', 'duration', 'speed', 'effect') if k in value})
                auto['interval'] = int(auto['interval'])
                auto['headlines'] = int(auto['headlines'])
                auto['enabled'] = bool(auto['enabled'])
                if not 5 <= auto['interval'] <= 1440 or not 1 <= auto['headlines'] <= 10:
                    raise ValueError('Intervall: 5 bis 1440 Minuten; Schlagzeilen: 1 bis 10.')
                display.options({**auto, 'text': 'RSS'})
                if auto['enabled']:
                    with connection() as db:
                        if not db.execute('SELECT 1 FROM feeds WHERE enabled=1').fetchone():
                            raise ValueError('Bitte zuerst einen Feed hinzufügen und aktivieren.')
                auto['next'] = time.time() if auto['enabled'] else 0
                save_setting('auto', auto)
                if auto['enabled']:
                    save_setting('clock', {**clocks.DEFAULT, **setting('clock', {}), 'enabled': False})
                return self.reply({'ok': True})
            return self.reply({'error': 'Nicht gefunden.'}, 404)
        except (ValueError, TypeError, OverflowError, KeyError) as exc:
            return self.reply({'error': str(exc)}, 400)
        except Exception:
            logging.exception('HTTP-Anfrage fehlgeschlagen')
            return self.reply({'error': 'Interner Fehler. Bitte das Protokoll prüfen.'}, 500)


def main():
    init()
    server = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    server.daemon_threads = True
    server.allowed_hosts = {'localhost', '127.0.0.1', 'raspberrypi', 'raspberrypi.local', socket.gethostname()}
    server.allowed_hosts.add(socket.gethostname() + '.local')
    server.allowed_hosts.update(h.strip().lower() for h in os.environ.get('TF_ALLOWED_HOSTS', '').split(',') if h.strip())
    try:
        server.allowed_hosts.update(a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None))
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('8.8.8.8', 80))
            server.allowed_hosts.add(s.getsockname()[0])
    except OSError:
        pass
    server.controller = Controller()

    def stop(*_):
        server.controller.stopping.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    logging.info('TF-C2-Web läuft auf Port %s', PORT)
    server.serve_forever()
    server.server_close()


if __name__ == '__main__':
    main()
