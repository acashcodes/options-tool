# Claude-Ready Implementation Spec

## IMAP Substack Newsletter → Dashboard "Alerts & News" (Email-Only)

------------------------------------------------------------------------

## 0) Goals

### Primary Goals

1.  Ingest Substack newsletters via IMAP.
2.  Process immediately upon arrival.
3.  Summarize only content relevant to portfolio/watchlist or their
    industries.
4.  Use OpenAI only for a 1-line headline (no digits allowed).
5.  Extract bullets deterministically (no paraphrasing).
6.  Encrypt raw email content at rest.
7.  Retain full searchable history.
8.  Display as a top card in Alerts & News panel with portfolio
    auto-expanded.

### Explicit Non-Goals

-   No web/news API lookups.
-   No ticker detection list displayed.
-   No sentiment scoring.
-   No external enrichment.

------------------------------------------------------------------------

# 1) Backend Architecture

Create new module:

backend/newsletter/

Files: - config.py - crypto.py - store.py - parser.py - relevance.py -
openai_headline.py - service.py - imap_listener.py

------------------------------------------------------------------------

# 2) Environment Variables

Required:

NEWSLETTER_ENABLED=true\
NEWSLETTER_IMAP_HOST=imap.gmail.com\
NEWSLETTER_IMAP_PORT=993\
NEWSLETTER_IMAP_USERNAME=your_email\
NEWSLETTER_IMAP_PASSWORD=app_password\
NEWSLETTER_IMAP_FOLDER=INBOX\
NEWSLETTER_FROM_ALLOWLIST=tmtbreakout@substack.com\
NEWSLETTER_USE_IDLE=true\
NEWSLETTER_POLL_SECONDS=30\
NEWSLETTER_DB_PATH=backend/data/newsletter.db\
NEWSLETTER_ENCRYPTION_KEY=`<Fernet key>`{=html}\
OPENAI_API_KEY=`<key>`{=html}\
OPENAI_MODEL=gpt-5.2\
OPENAI_TIMEOUT_SECONDS=20

------------------------------------------------------------------------

# 3) Database Schema (SQLite)

Table: newsletter_issues

Fields:

-   id (TEXT PRIMARY KEY)
-   source_name (TEXT)
-   from_email (TEXT)
-   subject (TEXT)
-   received_at (TEXT ISO8601)
-   message_id (TEXT UNIQUE)
-   web_url (TEXT)
-   raw_mime_enc (BLOB, encrypted)
-   raw_text_enc (BLOB, encrypted)
-   raw_html_enc (BLOB, encrypted)
-   headline (TEXT)
-   context_bullets_json (TEXT)
-   portfolio_bullets_json (TEXT)
-   watchlist_bullets_json (TEXT)
-   created_at (TEXT)
-   read (INTEGER default 0)

Raw content must always be encrypted using Fernet.

------------------------------------------------------------------------

# 4) Parsing Rules

Use Python email.parser.BytesParser.

Prefer text/plain over HTML.

Extract: - message_id - from_email - subject - received_at - web_url
(regex from "View this post on the web at ...")

Normalize text: - Convert CRLF to LF - Remove unsubscribe footer -
Preserve numeric accuracy

------------------------------------------------------------------------

# 5) Relevance Logic

Input: - full newsletter text - portfolio tickers - watchlist tickers

Output: - context_bullets (2--3 from preamble) - portfolio_bullets
(lines mentioning portfolio tickers) - watchlist_bullets (lines
mentioning watchlist tickers only)

Rules: - Exact regex word-boundary ticker matching - No paraphrasing -
Extractive only - Max 8 bullets per section

If no portfolio/watchlist mentions: - Display only context bullets

------------------------------------------------------------------------

# 6) OpenAI Headline Generation

Use OpenAI Responses API.

Rules: - One single line. - No digits. - No % symbols. - No invented
facts. - Only reflect extracted bullets.

If API fails: - Fallback headline = subject line.

------------------------------------------------------------------------

# 7) IMAP Listener

Use IMAP IDLE via imapclient.

Flow: - Connect - Select folder - On new mail: - Fetch unseen -
Process - Mark seen

Fallback to polling if IDLE fails.

------------------------------------------------------------------------

# 8) API Endpoints

GET /api/newsletter/latest\
GET /api/newsletter/issues/{id}\
GET /api/newsletter/history\
POST /api/newsletter/mark_read\
POST /api/newsletter/sync_now

Modify: GET /api/dashboard/alerts\
→ include newsletter object.

------------------------------------------------------------------------

# 9) Frontend Changes

Add NewsletterHighlightsCard.jsx.

Behavior: - Display at top of Alerts & News. - Show: - Headline -
Context bullets - Portfolio bullets (auto-expanded) - Watchlist bullets
(collapsed by default) - Button: Open full issue - Button: History

Remove detected ticker UI entirely.

------------------------------------------------------------------------

# 10) Security Requirements

-   Raw MIME and extracted content must be encrypted at rest.
-   Encryption via Fernet.
-   Only decrypt when serving full issue endpoint.
-   Never expose raw MIME via list endpoints.

------------------------------------------------------------------------

# 11) Testing

Backend unit tests:

-   Parser test (.eml fixture)
-   Encryption roundtrip test
-   Relevance extraction test
-   OpenAI fallback test

Integration test: - Ingest sample email - Verify: - Encrypted storage -
Summary endpoints return correct structure

------------------------------------------------------------------------

# 12) Definition of Done

1.  Email arrival → visible on dashboard within \~30 seconds.
2.  Portfolio bullets auto-expanded.
3.  No separate ticker detection list.
4.  Raw content encrypted in DB.
5.  Full history accessible.
6.  Headline contains no digits.

------------------------------------------------------------------------

END OF SPEC
