"""IMAP listener — connects via IDLE (or polling fallback) and processes new mail."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from .config import NewsletterConfig

logger = logging.getLogger(__name__)


class IMAPListener:
    """Background IMAP listener that invokes a callback on each new email."""

    def __init__(
        self,
        config: NewsletterConfig,
        on_new_email: Callable[[bytes], None],
    ) -> None:
        self.config = config
        self.on_new_email = on_new_email
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("IMAP listener started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("IMAP listener stopped")

    def fetch_unseen_once(self) -> int:
        """One-shot fetch of unseen messages. Returns count processed."""
        return self._fetch_unseen()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                if self.config.use_idle:
                    self._run_idle()
                else:
                    self._run_poll()
            except Exception as exc:
                logger.error("IMAP listener error: %s, retrying in 30s", exc)
                self._stop_event.wait(30)

    def _run_idle(self) -> None:
        import imapclient

        with imapclient.IMAPClient(
            self.config.imap_host,
            port=self.config.imap_port,
            ssl=True,
        ) as client:
            client.login(self.config.imap_username, self.config.imap_password)
            client.select_folder(self.config.imap_folder)

            # Initial fetch
            self._fetch_with_client(client)

            while not self._stop_event.is_set():
                client.idle()
                try:
                    responses = client.idle_check(timeout=30)
                    client.idle_done()
                    if responses:
                        self._fetch_with_client(client)
                except Exception:
                    client.idle_done()
                    raise

    def _run_poll(self) -> None:
        import imapclient

        while not self._stop_event.is_set():
            try:
                with imapclient.IMAPClient(
                    self.config.imap_host,
                    port=self.config.imap_port,
                    ssl=True,
                ) as client:
                    client.login(self.config.imap_username, self.config.imap_password)
                    client.select_folder(self.config.imap_folder)
                    self._fetch_with_client(client)
            except Exception as exc:
                logger.error("Poll error: %s", exc)

            self._stop_event.wait(self.config.poll_seconds)

    def _fetch_with_client(self, client) -> int:
        """Fetch and process unseen messages using an existing IMAP client."""
        messages = client.search(["UNSEEN"])
        count = 0
        for uid in messages:
            try:
                raw_data = client.fetch([uid], ["RFC822"])
                raw_bytes = raw_data[uid][b"RFC822"]
                self.on_new_email(raw_bytes)
                client.set_flags([uid], [b"\\Seen"])
                count += 1
            except Exception as exc:
                logger.error("Failed to process message %s: %s", uid, exc)
        return count

    def _fetch_unseen(self) -> int:
        """One-shot connection and fetch."""
        import imapclient

        try:
            with imapclient.IMAPClient(
                self.config.imap_host,
                port=self.config.imap_port,
                ssl=True,
            ) as client:
                client.login(self.config.imap_username, self.config.imap_password)
                client.select_folder(self.config.imap_folder)
                return self._fetch_with_client(client)
        except Exception as exc:
            logger.error("Fetch unseen error: %s", exc)
            return 0
