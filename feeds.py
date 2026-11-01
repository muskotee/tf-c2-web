"""Bounded RSS 2.0 / Atom fetching without executable feed content."""
import html
import ipaddress
import re
import socket
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

MAX_BYTES = 2 * 1024 * 1024


def validate_url(url):
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError('Bitte eine gültige Feed-URL eingeben.')
    p = urllib.parse.urlsplit(url.strip())
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('Feeds benötigen eine HTTP- oder HTTPS-Adresse ohne Zugangsdaten.')
    try:
        addresses = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == 'https' else 80))
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError('Bitte eine öffentlich erreichbare Feed-Adresse verwenden.')
    except (OSError, ValueError) as exc:
        raise ValueError('Die Feed-Adresse ist nicht öffentlich erreichbar oder ungültig.') from exc
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path or '/', p.query, ''))


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, validate_url(newurl))


def clean(text):
    text = re.sub('<[^>]*>', ' ', text or '')
    return ' '.join(html.unescape(text).split())[:500]


def parse(data):
    if len(data) > MAX_BYTES or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('Der Feed ist zu groß oder enthält ein nicht unterstütztes XML-Format.')
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError('Die Adresse liefert keinen gültigen RSS- oder Atom-Feed.') from exc

    def local(node):
        return node.tag.rsplit('}', 1)[-1] if isinstance(node.tag, str) else ''

    def value(node, name):
        found = next((c for c in node if local(c) == name), None)
        return clean(''.join(found.itertext())) if found is not None else ''

    if local(root) == 'rss':
        container = next((c for c in root if local(c) == 'channel'), None)
        if container is None:
            raise ValueError('RSS-Kanal fehlt.')
        nodes = [n for n in container if local(n) == 'item']
    elif local(root) == 'feed':
        container = root
        nodes = [n for n in root if local(n) == 'entry']
    elif local(root) == 'RDF':
        container = next((c for c in root if local(c) == 'channel'), root)
        nodes = [n for n in root if local(n) == 'item']
    else:
        raise ValueError('Unterstützt werden RSS- und Atom-Feeds.')
    items, seen = [], set()
    for node in nodes:
        title = value(node, 'title')
        if not title or title in seen:
            continue
        seen.add(title)
        link = value(node, 'link')
        if not link:
            link = next((c.get('href', '') for c in node if local(c) == 'link' and c.get('rel', 'alternate') == 'alternate'), '')
        items.append({'title': title, 'link': link, 'date': value(node, 'pubDate') or value(node, 'updated')})
        if len(items) >= 30:
            break
    if not items:
        raise ValueError('Der Feed enthält keine Schlagzeilen.')
    return {'title': value(container, 'title') or 'RSS-Feed', 'items': items}


def fetch(url):
    url = validate_url(url)
    request = urllib.request.Request(url, headers={
        'User-Agent': 'TF-C2-Web/1.0 RSS Reader',
        'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9',
        'Accept-Encoding': 'identity',
    })
    try:
        with urllib.request.build_opener(Redirect()).open(request, timeout=12) as response:
            data = response.read(MAX_BYTES + 1)
        result = parse(data)
        result['url'] = url
        return result
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('Feed konnte nicht geladen werden: ' + str(exc)[:180]) from exc
