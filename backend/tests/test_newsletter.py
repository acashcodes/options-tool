"""Tests for the newsletter module."""

from __future__ import annotations

import os
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure backend is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from newsletter.parser import parse_email
from newsletter.crypto import EmailCrypto
from newsletter.relevance import extract_relevance
from newsletter.openai_headline import generate_headline, _strip_digits
from newsletter.store import NewsletterStore
from newsletter.service import NewsletterService
from newsletter.config import NewsletterConfig

FIXTURES = Path(__file__).parent / "fixtures"


# ---- Parser tests ----

class TestParser:
    def _load_fixture(self) -> bytes:
        return (FIXTURES / "sample_newsletter.eml").read_bytes()

    def test_parse_email_extracts_fields(self):
        raw = self._load_fixture()
        parsed = parse_email(raw)

        assert parsed.message_id == "test-message-001@substack.com"
        assert parsed.from_email == "tmtbreakout@substack.com"
        assert "NVDA Surges" in parsed.subject
        assert parsed.received_at.startswith("2026-02-22")
        assert parsed.web_url == "https://tmtbreakout.substack.com/p/tmt-breakout-142"

    def test_parse_email_prefers_text_plain(self):
        raw = self._load_fixture()
        parsed = parse_email(raw)
        assert "semiconductor" in parsed.text_body.lower()

    def test_parse_email_removes_unsubscribe_footer(self):
        raw = self._load_fixture()
        parsed = parse_email(raw)
        assert "unsubscribe" not in parsed.text_body.lower()

    def test_parse_email_normalizes_crlf(self):
        raw = b"From: test@example.com\r\nSubject: Test\r\nMessage-ID: <crlf-test>\r\n\r\nHello\r\nWorld\r\n"
        parsed = parse_email(raw)
        assert "\r" not in parsed.text_body


# ---- Crypto tests ----

class TestCrypto:
    def _make_crypto(self) -> EmailCrypto:
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        return EmailCrypto(key)

    def test_encrypt_decrypt_roundtrip_bytes(self):
        crypto = self._make_crypto()
        original = b"Hello, this is raw MIME content."
        encrypted = crypto.encrypt(original)
        assert encrypted != original
        decrypted = crypto.decrypt(encrypted)
        assert decrypted == original

    def test_encrypt_decrypt_roundtrip_string(self):
        crypto = self._make_crypto()
        original = "NVDA reported strong earnings."
        encrypted = crypto.encrypt(original)
        decrypted = crypto.decrypt_text(encrypted)
        assert decrypted == original

    def test_encrypted_output_is_bytes(self):
        crypto = self._make_crypto()
        encrypted = crypto.encrypt("test")
        assert isinstance(encrypted, bytes)


# ---- Relevance tests ----

class TestRelevance:
    SAMPLE_TEXT = """Good morning, here is your TMT Breakout newsletter for today.

The semiconductor sector continues to show strength as artificial intelligence spending accelerates.

Key developments to watch this week include several major earnings reports.

NVDA reported earnings that beat expectations by a wide margin.

AAPL announced a new partnership that could expand its services revenue.

MSFT Azure growth reaccelerated, beating consensus estimates.

TSLA deliveries came in below expectations.

AMD gained share in the server CPU market."""

    def test_context_bullets_extracted(self):
        result = extract_relevance(self.SAMPLE_TEXT, [], [])
        assert len(result.context_bullets) >= 2
        assert len(result.context_bullets) <= 3

    def test_portfolio_bullets_match_tickers(self):
        result = extract_relevance(self.SAMPLE_TEXT, ["NVDA", "AAPL"], [])
        assert len(result.portfolio_bullets) >= 2
        assert any("NVDA" in b for b in result.portfolio_bullets)
        assert any("AAPL" in b for b in result.portfolio_bullets)

    def test_watchlist_bullets_separate_from_portfolio(self):
        result = extract_relevance(self.SAMPLE_TEXT, ["NVDA"], ["AAPL", "MSFT"])
        assert any("NVDA" in b for b in result.portfolio_bullets)
        assert any("AAPL" in b for b in result.watchlist_bullets)
        # AAPL should not be in portfolio
        assert not any("AAPL" in b for b in result.portfolio_bullets)

    def test_no_matches_returns_empty_bullets(self):
        result = extract_relevance(self.SAMPLE_TEXT, ["ZZZ"], ["XXX"])
        assert len(result.portfolio_bullets) == 0
        assert len(result.watchlist_bullets) == 0

    def test_max_bullets_enforced(self):
        long_text = "\n".join(f"NVDA line number {i} with content." for i in range(20))
        result = extract_relevance(long_text, ["NVDA"], [])
        assert len(result.portfolio_bullets) <= 8

    def test_word_boundary_matching(self):
        text = "The AI sector saw gains. AMD processors are popular. AMDA is not a ticker."
        result = extract_relevance(text, ["AMD"], [])
        matched = [b for b in result.portfolio_bullets if "AMDA" in b and "AMD " not in b]
        # AMDA should not match AMD
        assert len(matched) == 0


# ---- OpenAI headline tests ----

class TestOpenAIHeadline:
    def test_fallback_when_no_api_key(self):
        headline = generate_headline(
            ["NVDA beat earnings"],
            "TMT Breakout #142",
            api_key="",
        )
        assert headline  # Should return subject-based fallback
        assert not any(c.isdigit() for c in headline)

    def test_fallback_when_no_bullets(self):
        headline = generate_headline(
            [],
            "Newsletter #99 - 50% gains",
            api_key="fake-key",
        )
        # Falls back to subject with digits stripped
        assert not any(c.isdigit() for c in headline)
        assert "%" not in headline

    @patch("newsletter.openai_headline.OpenAI", create=True)
    def test_successful_api_call(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.output_text = "Semiconductor Sector Rallies on Strong AI Demand"
        mock_client.responses.create.return_value = mock_response

        headline = generate_headline(
            ["NVDA beat earnings", "AI spending accelerates"],
            "Fallback Subject",
            api_key="sk-test-key",
            model="gpt-4o",
        )
        assert headline == "Semiconductor Sector Rallies on Strong AI Demand"
        mock_client.responses.create.assert_called_once()

    @patch("newsletter.openai_headline.OpenAI", create=True)
    def test_api_failure_uses_fallback(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.responses.create.side_effect = Exception("API timeout")

        headline = generate_headline(
            ["NVDA beat earnings"],
            "TMT Breakout #142 - 30% gains",
            api_key="sk-test-key",
        )
        # Should fallback to sanitized subject
        assert not any(c.isdigit() for c in headline)
        assert "%" not in headline

    def test_strip_digits(self):
        assert _strip_digits("NVDA up 10% today") == "NVDA up today"
        assert _strip_digits("No digits here") == "No digits here"
        assert _strip_digits("42 percent gain") == "percent gain"


# ---- Store tests ----

class TestStore:
    def _make_store(self, tmp_path) -> NewsletterStore:
        db_path = str(tmp_path / "test_newsletter.db")
        store = NewsletterStore(db_path)
        store.init_db()
        return store

    def test_init_creates_table(self, tmp_path):
        store = self._make_store(tmp_path)
        # Should not raise
        assert store.get_latest() is None

    def test_insert_and_retrieve(self, tmp_path):
        store = self._make_store(tmp_path)
        issue = {
            "id": "test-id-1",
            "source_name": "TMT Breakout",
            "from_email": "tmtbreakout@substack.com",
            "subject": "Test Subject",
            "received_at": "2026-02-22T08:00:00",
            "message_id": "msg-001",
            "web_url": "https://example.com",
            "raw_mime_enc": b"encrypted-mime",
            "raw_text_enc": b"encrypted-text",
            "raw_html_enc": None,
            "headline": "Test Headline",
            "context_bullets": ["Bullet 1", "Bullet 2"],
            "portfolio_bullets": ["NVDA is up"],
            "watchlist_bullets": [],
        }
        store.insert_issue(issue)

        latest = store.get_latest()
        assert latest is not None
        assert latest["id"] == "test-id-1"
        assert latest["headline"] == "Test Headline"
        assert latest["context_bullets"] == ["Bullet 1", "Bullet 2"]
        assert latest["portfolio_bullets"] == ["NVDA is up"]

    def test_duplicate_message_id_rejected(self, tmp_path):
        store = self._make_store(tmp_path)
        issue = {
            "id": "test-id-1",
            "source_name": "Test",
            "from_email": "test@test.com",
            "subject": "Test",
            "received_at": "2026-01-01",
            "message_id": "unique-msg",
            "web_url": None,
            "raw_mime_enc": None,
            "raw_text_enc": None,
            "raw_html_enc": None,
            "headline": "Test",
            "context_bullets": [],
            "portfolio_bullets": [],
            "watchlist_bullets": [],
        }
        store.insert_issue(issue)
        assert store.message_id_exists("unique-msg")
        assert not store.message_id_exists("other-msg")

    def test_mark_read(self, tmp_path):
        store = self._make_store(tmp_path)
        issue = {
            "id": "read-test",
            "source_name": "Test",
            "from_email": "test@test.com",
            "subject": "Test",
            "received_at": "2026-01-01",
            "message_id": "read-msg",
            "web_url": None,
            "raw_mime_enc": None,
            "raw_text_enc": None,
            "raw_html_enc": None,
            "headline": "Read Test",
            "context_bullets": [],
            "portfolio_bullets": [],
            "watchlist_bullets": [],
        }
        store.insert_issue(issue)
        assert not store.get_latest()["read"]
        store.mark_read("read-test")
        assert store.get_latest()["read"]

    def test_history(self, tmp_path):
        store = self._make_store(tmp_path)
        for i in range(5):
            store.insert_issue({
                "id": f"hist-{i}",
                "source_name": "Test",
                "from_email": "test@test.com",
                "subject": f"Issue {i}",
                "received_at": f"2026-02-{20+i:02d}T08:00:00",
                "message_id": f"hist-msg-{i}",
                "web_url": None,
                "raw_mime_enc": None,
                "raw_text_enc": None,
                "raw_html_enc": None,
                "headline": f"Headline {i}",
                "context_bullets": [],
                "portfolio_bullets": [],
                "watchlist_bullets": [],
            })
        history = store.get_history(limit=3)
        assert len(history) == 3
        # Newest first
        assert history[0]["id"] == "hist-4"

    def test_encrypted_content_not_in_summary(self, tmp_path):
        store = self._make_store(tmp_path)
        issue = {
            "id": "enc-test",
            "source_name": "Test",
            "from_email": "test@test.com",
            "subject": "Test",
            "received_at": "2026-01-01",
            "message_id": "enc-msg",
            "web_url": None,
            "raw_mime_enc": b"secret-data",
            "raw_text_enc": b"secret-text",
            "raw_html_enc": b"secret-html",
            "headline": "Encrypted Test",
            "context_bullets": [],
            "portfolio_bullets": [],
            "watchlist_bullets": [],
        }
        store.insert_issue(issue)
        summary = store.get_latest()
        assert "raw_mime_enc" not in summary
        assert "raw_text_enc" not in summary

    def test_full_issue_includes_encrypted(self, tmp_path):
        store = self._make_store(tmp_path)
        issue = {
            "id": "full-test",
            "source_name": "Test",
            "from_email": "test@test.com",
            "subject": "Test",
            "received_at": "2026-01-01",
            "message_id": "full-msg",
            "web_url": None,
            "raw_mime_enc": b"secret-mime",
            "raw_text_enc": b"secret-text",
            "raw_html_enc": None,
            "headline": "Full Test",
            "context_bullets": [],
            "portfolio_bullets": [],
            "watchlist_bullets": [],
        }
        store.insert_issue(issue)
        full = store.get_issue("full-test", include_encrypted=True)
        assert full["raw_mime_enc"] == b"secret-mime"
        assert full["raw_text_enc"] == b"secret-text"


# ---- Integration test ----

class TestIntegration:
    """End-to-end: ingest sample email -> verify encrypted storage -> check API structure."""

    def _make_config(self, tmp_path) -> NewsletterConfig:
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        return NewsletterConfig(
            enabled=True,
            db_path=str(tmp_path / "integration.db"),
            encryption_key=key,
            from_allowlist=["tmtbreakout@substack.com"],
            openai_api_key="",  # Will use fallback
        )

    def test_ingest_sample_email(self, tmp_path):
        config = self._make_config(tmp_path)
        service = NewsletterService(config)

        raw = (FIXTURES / "sample_newsletter.eml").read_bytes()
        result = service.process_raw_email(
            raw,
            portfolio_tickers=["NVDA", "AAPL"],
            watchlist_tickers=["MSFT", "TSLA"],
        )

        assert result is not None
        assert result["headline"]
        assert not any(c.isdigit() for c in result["headline"])

        # Verify storage
        latest = service.get_latest()
        assert latest is not None
        assert latest["id"] == result["id"]
        assert len(latest["context_bullets"]) >= 2
        assert any("NVDA" in b for b in latest["portfolio_bullets"])

        # Verify encrypted storage (raw blobs exist in DB)
        full = service.get_issue_full(result["id"])
        assert full is not None
        # Decrypted text should contain the original content
        assert "semiconductor" in full.get("raw_text", "").lower()
        # No encrypted blobs in the response
        assert "raw_mime_enc" not in full
        assert "raw_text_enc" not in full

    def test_duplicate_rejected(self, tmp_path):
        config = self._make_config(tmp_path)
        service = NewsletterService(config)

        raw = (FIXTURES / "sample_newsletter.eml").read_bytes()
        result1 = service.process_raw_email(raw, [], [])
        assert result1 is not None

        result2 = service.process_raw_email(raw, [], [])
        assert result2 is None  # Duplicate

    def test_non_allowlisted_sender_rejected(self, tmp_path):
        config = self._make_config(tmp_path)
        service = NewsletterService(config)

        raw = b"From: unknown@example.com\nSubject: Test\nMessage-ID: <unknown-001>\n\nBody text here."
        result = service.process_raw_email(raw, [], [])
        assert result is None

    def test_history_endpoint_structure(self, tmp_path):
        config = self._make_config(tmp_path)
        service = NewsletterService(config)

        raw = (FIXTURES / "sample_newsletter.eml").read_bytes()
        service.process_raw_email(raw, ["NVDA"], [])

        history = service.get_history()
        assert len(history) == 1
        item = history[0]
        assert "id" in item
        assert "headline" in item
        assert "received_at" in item
        assert "read" in item
        # History should not include encrypted blobs
        assert "raw_mime_enc" not in item

    def test_mark_read(self, tmp_path):
        config = self._make_config(tmp_path)
        service = NewsletterService(config)

        raw = (FIXTURES / "sample_newsletter.eml").read_bytes()
        result = service.process_raw_email(raw, [], [])
        assert not service.get_latest()["read"]

        service.mark_read(result["id"])
        assert service.get_latest()["read"]
