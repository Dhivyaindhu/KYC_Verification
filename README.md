# Playto KYC System

A full-stack KYC (Know Your Customer) pipeline for merchant onboarding before international payment processing.

---

## Architecture

```
React Frontend (index.html)
        ↓ Token Auth (DRF)
Django REST Framework API
        ↓
State Machine + Validation + RBAC
        ↓
SQLite / PostgreSQL
        ↓
Local Media Storage (/media/)
```

### Project Layout

```
playto_kyc/
├── config/              # Django settings, root URLs
├── users/               # Custom User model (merchant | reviewer)
├── kyc/                 # Core: submissions, documents, state machine, views
├── notifications/       # Audit event log
├── frontend/
│   └── index.html       # Full React SPA (no build step)
├── requirements.txt
├── manage.py
└── setup.sh
```

---

## Quick Start

```bash
cd playto_kyc
chmod +x setup.sh
./setup.sh

# Start backend
source venv/bin/activate
python manage.py runserver

# Open frontend
open frontend/index.html
```

**Demo accounts created by setup.sh:**

| Role     | Email                | Password  |
|----------|----------------------|-----------|
| Merchant | merchant@demo.com    | demo1234  |
| Reviewer | reviewer@demo.com    | demo1234  |

---

## Key Design Decisions

### 1. State Machine (kyc/models.py)

All state transitions are enforced centrally in `KYCSubmission.transition_to()`:

```python
VALID_TRANSITIONS = {
    'draft':               ['submitted'],
    'submitted':           ['under_review'],
    'under_review':        ['approved', 'rejected', 'more_info_requested'],
    'more_info_requested': ['submitted'],
    'approved':            [],   # Terminal
    'rejected':            [],   # Terminal
}
```

The method raises `ValueError` for invalid transitions — views catch and return HTTP 400.

```
draft → submitted → under_review → approved
                                 → rejected
                                 → more_info_requested → submitted (loop)
```

### 2. File Upload Security (kyc/serializers.py)

Three-layer validation in `DocumentUploadSerializer`:

1. **Extension check** — `.pdf`, `.jpg`, `.jpeg`, `.png` only
2. **Size check** — max 5MB enforced
3. **MIME type check** — `python-magic` reads file bytes (prevents extension spoofing)

### 3. Role-Based Access Control (kyc/permissions.py)

```python
class IsMerchantOwnerOrReviewer(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.is_reviewer:
            return True          # Reviewers: full access
        return obj.merchant == request.user  # Merchants: own data only
```

### 4. Reviewer Queue + SLA (kyc/views.py)

```
GET /api/kyc/reviewer/queue/
```

- Returns `submitted` + `under_review` submissions ordered by `submitted_at` ASC (oldest first = FIFO)
- `is_at_risk` property: True if `hours in review > KYC_SLA_HOURS` (default 24h)
- `hours_in_review` calculated at runtime, no DB write needed

### 5. Audit Logging (notifications/models.py)

Every state change writes an immutable `NotificationEvent`:

```python
NotificationEvent(
    submission=...,
    actor=request.user,
    event_type='approve',
    old_status='under_review',
    new_status='approved',
    notes='...',
    created_at=auto
)
```

Serves as the full audit trail — queryable per submission or globally.

---

## API Reference

### Auth

| Method | Endpoint              | Description        |
|--------|-----------------------|--------------------|
| POST   | `/api/auth/register/` | Sign up            |
| POST   | `/api/auth/login/`    | Get token          |
| POST   | `/api/auth/logout/`   | Invalidate token   |
| GET    | `/api/auth/me/`       | Current user info  |

### Merchant

| Method | Endpoint                                     | Description               |
|--------|----------------------------------------------|---------------------------|
| GET    | `/api/kyc/submissions/`                      | List own submissions      |
| POST   | `/api/kyc/submissions/`                      | Create draft              |
| GET    | `/api/kyc/submissions/{id}/`                 | Get detail                |
| PATCH  | `/api/kyc/submissions/{id}/`                 | Update draft fields       |
| POST   | `/api/kyc/submissions/{id}/submit/`          | Submit for review         |
| POST   | `/api/kyc/submissions/{id}/documents/`       | Upload document           |
| DELETE | `/api/kyc/submissions/{id}/documents/?doc_type=pan` | Remove document    |

### Reviewer

| Method | Endpoint                                       | Description              |
|--------|------------------------------------------------|--------------------------|
| GET    | `/api/kyc/reviewer/queue/`                     | Pending queue (FIFO)     |
| GET    | `/api/kyc/reviewer/submissions/`               | All submissions          |
| GET    | `/api/kyc/reviewer/submissions/{id}/`          | Full detail              |
| POST   | `/api/kyc/reviewer/submissions/{id}/pickup/`   | Start reviewing          |
| POST   | `/api/kyc/reviewer/submissions/{id}/action/`   | Approve/Reject/RequestInfo |
| GET    | `/api/kyc/reviewer/stats/`                     | Dashboard metrics        |

### Action Payload

```json
POST /api/kyc/reviewer/submissions/{id}/action/
{
  "action": "approve" | "reject" | "request_info",
  "reason": "Required if action=reject",
  "notes": "Required if action=request_info"
}
```

### Notifications

```
GET /api/notifications/submission/{id}/   # Per-submission audit log
GET /api/notifications/all/               # All events (reviewer only)
```

---

## Frontend

Single-file React SPA at `frontend/index.html`. No build step — loads React from CDN.

**Merchant flow:**
1. Sign up → Multi-step KYC form (Personal → Business → Documents → Review)
2. Save draft at any step
3. Upload documents (drag & drop or click)
4. Submit → track status in My Applications

**Reviewer flow:**
1. Dashboard with 4 key metrics (Total, In Queue, Approved, At Risk)
2. Queue view: FIFO list with SLA indicators
3. Detail view: full merchant data + documents
4. Action buttons: Approve / Reject (with reason) / Request Info (with notes)
5. Audit timeline showing full history

---

## Configuration

In `config/settings.py`:

```python
# Adjust SLA threshold
KYC_SLA_HOURS = 24

# Allowed file types
ALLOWED_DOCUMENT_TYPES = ['application/pdf', 'image/jpeg', 'image/png']
ALLOWED_DOCUMENT_EXTENSIONS = ['.pdf', '.jpg', '.jpeg', '.png']
MAX_DOCUMENT_SIZE = 5 * 1024 * 1024   # 5 MB
```

Switch to PostgreSQL:
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'playto_kyc',
        'USER': 'postgres',
        'PASSWORD': 'yourpassword',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

---

## Production Checklist

- [ ] Set `DEBUG = False` and real `SECRET_KEY` via env var
- [ ] Configure PostgreSQL
- [ ] Set `CORS_ALLOW_ALL_ORIGINS = False` with specific origins
- [ ] Use S3/GCS for media storage (replace `MEDIA_ROOT`)
- [ ] Add rate limiting (`django-ratelimit`)
- [ ] Enable HTTPS / run behind nginx
- [ ] Set up celery for async notification emails
- [ ] Add comprehensive test suite (pytest-django)
