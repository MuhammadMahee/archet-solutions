"""Run the persistent local AI queue: python scripts/workforce_worker.py."""
import argparse
import logging
from pathlib import Path
import signal
import sys
from threading import Event, Thread
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.index import app
from api.workforce import get_store
from api.workforce_ai import execute


def run_worker(store, stop, once=False):
    worker = str(uuid4())
    heartbeat_stop = Event()
    def pulse():
        while not heartbeat_stop.is_set():
            try:
                store.heartbeat(worker)
            except Exception:
                logging.warning('Worker heartbeat unavailable; check local storage.')
            heartbeat_stop.wait(10)
    heartbeat = Thread(target=pulse, daemon=True)
    heartbeat.start()
    try:
        while not stop.is_set():
            task = store.claim(worker)
            if task:
                logging.info('Processing assignment %s', task['id'])
                execute(store, task)
            if once:
                break
            if not task:
                stop.wait(1)
    finally:
        heartbeat_stop.set()
        heartbeat.join(timeout=12)
        with store.connection(True) as conn:
            conn.execute('DELETE FROM workers WHERE id=?', (worker,))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true', help='Process at most one pending assignment.')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    stop = Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    with app.app_context():
        store = get_store()
    logging.info('AI worker ready. Press Ctrl+C to stop after the current assignment.')
    run_worker(store, stop, args.once)


if __name__ == '__main__':
    main()
