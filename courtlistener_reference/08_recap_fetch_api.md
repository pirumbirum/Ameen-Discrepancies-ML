# RECAP Fetch API - Buying Documents from PACER

The RECAP Fetch API lets you programmatically purchase dockets and documents from PACER through CourtListener.

---

## How It Works

1. **You POST** a fetch request to CourtListener with your PACER credentials
2. **CourtListener** uses your credentials to get a PACER session cookie, then immediately discards your password
3. **CourtListener** purchases the document/docket from PACER on your behalf
4. **PACER bills** your PACER account (not CourtListener)
5. **The document** is stored in the RECAP Archive for everyone
6. **You get notified** when it's ready (webhook or polling)

---

## Endpoint

```
POST /api/rest/v4/recap-fetch/
```

---

## Request Types

| `request_type` | What It Fetches | Description |
|----------------|-----------------|-------------|
| `1` | Docket report | Full docket sheet with all entries |
| `2` | PDF document | Individual document (by `pacer_doc_id`) |
| `3` | Attachment page | List of attachments for a docket entry |

---

## Request Parameters

### For Docket Reports (`request_type=1`)
```json
{
    "request_type": 1,
    "pacer_case_id": "123456",
    "court_id": "nysd",
    "pacer_username": "your_pacer_username",
    "pacer_password": "your_pacer_password"
}
```

### For PDF Documents (`request_type=2`)
```json
{
    "request_type": 2,
    "pacer_doc_id": "04506123456",
    "court_id": "nysd",
    "pacer_username": "your_pacer_username",
    "pacer_password": "your_pacer_password"
}
```

### For Attachment Pages (`request_type=3`)
```json
{
    "request_type": 3,
    "pacer_doc_id": "04506123456",
    "court_id": "nysd",
    "pacer_username": "your_pacer_username",
    "pacer_password": "your_pacer_password"
}
```

---

## Response

The response is immediate but the actual fetch is **asynchronous**:

```json
{
    "id": 12345,
    "date_created": "2024-01-15T10:30:00Z",
    "date_modified": "2024-01-15T10:30:00Z",
    "date_completed": null,
    "status": 1,
    "request_type": 2,
    "court_id": "nysd",
    "pacer_case_id": "123456",
    "pacer_doc_id": "04506123456",
    "docket": null,
    "recap_document": null,
    "message": ""
}
```

### Status Codes

| Status | Meaning |
|--------|---------|
| `1` | Awaiting processing |
| `2` | In processing |
| `3` | Successfully completed |
| `4` | Failed |

### Checking Status

Poll the fetch request:
```
GET /api/rest/v4/recap-fetch/12345/
```

When `status=3`, the `docket` or `recap_document` field will contain the URL to the fetched resource.

---

## Costs

| Item | Cost |
|------|------|
| **CourtListener API** | Free |
| **PACER per page** | $0.10 |
| **PACER cap per document** | $3.00 |
| **PACER quarterly fee waiver** | Under $30/quarter = free |
| **Opinions on PACER** | Free (always) |

---

## Security Model

1. You send your PACER username and password in the POST request
2. CourtListener uses them to authenticate with PACER and get a session cookie
3. Your password is **immediately discarded** -- it is never stored
4. The session cookie is used for the purchase, then discarded
5. All communication happens over HTTPS

---

## Pray & Pay System

If a document isn't available in the RECAP Archive and you don't want to buy it yourself:

### Prayers Endpoint
```
POST /api/rest/v4/prayers/
```

You can "pray" for a document -- essentially requesting it. If another user later purchases it, you'll be notified.

### How It Works
1. You request a document via the Prayers endpoint
2. Your prayer is recorded
3. If someone else purchases that document later, you get notified
4. The document becomes available to everyone in the RECAP Archive

### Limits
- Free Law Project members get higher daily prayer limits
- Non-members have lower limits

---

## Webhook Notifications

You can set up webhooks to be notified when:
- A fetch request completes
- A prayed-for document becomes available
- A docket alert triggers

---

## Sources
- PACER Fetch API Blog Post: https://free.law/2019/11/05/pacer-fetch-api/
- CourtListener PACER APIs: https://www.courtlistener.com/help/api/rest/pacer/
- CourtListener REST API: https://www.courtlistener.com/help/api/rest/
