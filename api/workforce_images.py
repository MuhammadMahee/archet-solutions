"""Bounded raster attachments, report cards and public website captures."""
import base64
from io import BytesIO
import ipaddress
import json
import re
import socket
import textwrap
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
import warnings

from PIL import Image, ImageDraw, ImageFont, ImageOps
from api.portal import PortalError

MAX_IMAGE_BYTES = 1024 * 1024


def normalize_image(raw, name='Screenshot', source='upload'):
    if not raw or len(raw) > 2 * MAX_IMAGE_BYTES:
        raise PortalError('Choose an image under 2 MB after resizing.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as original:
                if original.format not in ('PNG', 'JPEG', 'WEBP') or original.width * original.height > 20_000_000:
                    raise ValueError()
                original.load()
                picture = ImageOps.exif_transpose(original).convert('RGB')
                picture.thumbnail((1800, 1800))
                # Re-encoding removes metadata, animation and any trailing payload.
                output = BytesIO()
                picture.save(output, format='PNG')
                mime = 'image/png'
                if output.tell() > MAX_IMAGE_BYTES:
                    output = BytesIO()
                    picture.save(output, format='JPEG', quality=85)
                    mime = 'image/jpeg'
                if output.tell() > MAX_IMAGE_BYTES:
                    raise ValueError()
                return {'name': name[:100], 'mime': mime, 'width': picture.width, 'height': picture.height,
                        'size': output.tell(), 'data': base64.b64encode(output.getvalue()).decode(), 'source': source}
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise PortalError('Use a valid PNG, JPEG or WebP image, up to 20 megapixels.') from None


def upload_images(items):
    if not isinstance(items, list) or len(items) > 2:
        raise PortalError('Attach up to two screenshots per message.')
    result = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get('data'), str) or len(item['data']) > 1_400_000:
            raise PortalError('This screenshot is too large. Resize it and try again.')
        try:
            raw = base64.b64decode(item['data'], validate=True)
        except ValueError:
            raise PortalError('The screenshot could not be read.') from None
        result.append(normalize_image(raw))
    return result


def text_image(title, text, source='Generated summary'):
    font, heading = ImageFont.load_default(size=22), ImageFont.load_default(size=32)
    lines = []
    for paragraph in text[:6000].splitlines():
        lines.extend(textwrap.wrap(paragraph, width=78, break_long_words=True) or [''])
    truncated = len(lines) > 42
    lines = lines[:42]
    if truncated:
        lines[-1] = '... Continued in the chat message or downloadable report.'
    picture = Image.new('RGB', (1120, 190 + 31 * len(lines)), '#101e26')
    draw = ImageDraw.Draw(picture)
    draw.text((42, 30), title[:55], font=heading, fill='#9ce9d5')
    draw.text((42, 82), source[:90], font=font, fill='#8faab6')
    for index, line in enumerate(lines):
        draw.text((42, 136 + index * 31), line, font=font, fill='#e2edef')
    output = BytesIO()
    picture.save(output, format='PNG')
    return normalize_image(output.getvalue(), title, source)


def report_image(report):
    totals = report['totals']
    text = f"Dates: {report['start']} to {report['end']}\nMatching stores: {len(report['rows'])}\nTotal boxes: {totals.get('total_boxes', 'Unavailable')}\nAccessory sales (USD): {totals.get('accessory', 'Unavailable')}\nCoverage: {report['coverage']['complete']}/{report['coverage']['expected']} source-days\n\n"
    text += '\n'.join(f"{r.get('store', 'Store')}: {r.get('total_boxes', '?')} boxes; USD {r.get('accessory', '?')} accessory sales" for r in report['rows'][:12])
    text += '\n\nFirst 12 stores shown. Full data is in the CSV. Missing data is not zero.'
    return text_image('Saved sales report', text, 'Report snapshot from saved source records')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise PortalError('The screenshot service redirected unexpectedly. Retry later.', 502)


def public_url(url, request_text):
    if not isinstance(url, str) or len(url) > 1500 or url not in [u.rstrip('.,);') for u in re.findall(r'https?://[^\s<>"`\]]+', request_text)]:
        raise PortalError('Include the exact public website URL in your message.')
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or
                parsed.query or parsed.fragment or parsed.port not in (None, 443) or
                parsed.hostname.endswith(('.local', '.internal', '.localhost')) or
                parsed.hostname == 'internal.archetsolutions.com'):
            raise ValueError()
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError()
    except (ValueError, OSError):
        raise PortalError('Use a public HTTPS page without login credentials, query parameters or a private network address.') from None
    return url


def website_image(url, request_text):
    url = public_url(url, request_text)
    # Only the user-supplied public URL goes to Microlink. Never send chat,
    # uploaded images, cookies, authorization headers or database credentials.
    target = 'https://api.microlink.io/?' + urlencode({'url': url, 'screenshot': 'true', 'meta': 'false',
                'viewport.width': 1280, 'viewport.height': 800, 'viewport.deviceScaleFactor': 1, 'screenshot.type': 'png'})
    opener = build_opener(NoRedirect())
    try:
        with opener.open(Request(target, headers={'User-Agent': 'ArchetWorkforce/1.0'}), timeout=35) as response:
            raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError()
            result = json.loads(raw)
        if result.get('status') != 'success':
            raise ValueError()
        image_url = result['data']['screenshot']['url']
        parsed = urlsplit(image_url)
        if parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.microlink.io') or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError()
        with opener.open(Request(image_url, headers={'User-Agent': 'ArchetWorkforce/1.0'}), timeout=20) as response:
            data = response.read(2 * MAX_IMAGE_BYTES + 1)
        return normalize_image(data, 'Website screenshot', url)
    except HTTPError as exc:
        if exc.code == 429:
            raise PortalError('The free website screenshot quota is used up. Try again after it resets.', 429) from None
        raise PortalError('The website screenshot service could not capture that page. It may block automated browsers.', 502) from None
    except (URLError, OSError, ValueError, KeyError, TypeError):
        raise PortalError('The website screenshot service is unavailable or could not capture this page.', 502) from None
