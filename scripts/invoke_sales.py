"""GitHub supplies the clock. All RT-POS downloads and database writes run on Vercel."""
import json
import os
import sys
import time
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main():
    secret = os.getenv('CRON_SECRET')
    if not secret:
        raise SystemExit('Configure the CRON_SECRET repository secret first.')
    opener = build_opener(NoRedirect())
    failures = 0
    for batch in range(60):
        req = Request('https://internal.archetsolutions.com/api/jobs/sales', data=b'{}',
                      headers={'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json'})
        try:
            with opener.open(req, timeout=280) as response:
                result = json.load(response)
            print(f"Batch {batch + 1}: {result.get('status')}; remaining source-days: {result.get('remaining')}", flush=True)
            if result.get('status') == 'busy':
                time.sleep(30)
                continue
            if result.get('remaining') == 0:
                return 0
            if result.get('due') == 0:
                print('Some sources failed; saved data was retained. Check Sales Update import status. The next schedule will retry.')
                return 1
            failures = 0
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            failures += 1
            print('Vercel request failed (' + str(getattr(exc, 'code', type(exc).__name__)) + ').', flush=True)
            if failures >= 3:
                return 1
            time.sleep(30)
    print('Backfill is still pending; the next schedule will resume it.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
