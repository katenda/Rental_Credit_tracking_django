# Rental Credit API (Django)

REST API for the [Real Estate Rental Credit Tracking System](../README.md): JWT authentication, rental agreements, tenant consent, landlord reports, rental credit scoring, disputes, and tenant invitations.

---

## Stack

| Component | Package |
|-----------|---------|
| Framework | Django 5+ |
| API | Django REST Framework |
| Auth | djangorestframework-simplejwt (access + refresh tokens) |
| CORS | django-cors-headers |
| Database | SQLite (`db.sqlite3` by default) |

---

## Project layout

```
backend/
├── config/           # settings, root URLconf, WSGI, health check
├── accounts/         # Custom User (roles), register, login, me, admin user list
├── rentals/          # Models, serializers, views, scoring, invitations, signals
│   └── management/commands/
│       └── recalculate_credit_scores.py
├── manage.py
└── requirements.txt
```

---

## Quick start

```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

The API base is typically **`http://127.0.0.1:8000`**. Health check: **`GET /api/health/`**.

### Admin user (SPA + `/api/auth/users/`)

```bash
python manage.py createsuperuser
```

In Django admin, open the new user and set **`role`** to **`admin`** (the custom `User` model). Public registration cannot create admins.

---

## Configuration

| Setting / variable | Purpose |
|--------------------|---------|
| `FRONTEND_BASE_URL` | Env var; base URL for tenant invitation links (default `http://localhost:3000`). Set in production. |
| `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` | Standard Django; do not use default `SECRET_KEY` in production. |
| `CORS_ALLOWED_ORIGINS` | SPA origins allowed to call the API (`config/settings.py`). |
| `DATABASES` | Defaults to SQLite; point at PostgreSQL or another engine for production. |

---

## Notable HTTP routes (prefix `/api/`)

| Area | Examples |
|------|----------|
| Auth | `POST /api/auth/register/`, `POST /api/auth/token/`, `GET/PATCH /api/auth/me/`, `GET /api/auth/users/` (admin) |
| Core | `GET/POST /api/agreements/`, `GET/POST /api/consents/`, `GET/POST /api/reports/`, `GET /api/credit-scores/`, `GET/POST/PATCH /api/disputes/` |
| Profiles | `GET/PATCH /api/profiles/landlord/me/`, `GET/PATCH /api/profiles/tenant/me/` |
| Other | `GET /api/dashboard/stats/`, `GET /api/tenants/search/`, invitations under `/api/invitations/` and `GET /api/invitations/validate/` |

Full detail: **[`../README.md`](../README.md)** (API tables and domain model).

---

## Credit scoring

- **Implementation:** `rentals/scoring.py` → `recalculate_tenant_credit_score(tenant_user_id)`.
- **When it runs:** After each **`RentalReport`** create (`RentalReportViewSet.perform_create`).
- **Bulk recompute:** `python manage.py recalculate_credit_scores`.

**Full specification** (penalties table, 0–100 clamp, `factors` JSON, consent vs reports order, MVP limits): **[`../README.md` — Rental credit score](../README.md#rental-credit-score)**.

---

## Django admin

**`/admin/`** — register superuser as above. Models such as users, profiles, agreements, consents, reports, credit scores, disputes, and invitations are registered for inspection and support.

---

## Documentation

- **Monorepo overview & API**: [`../README.md`](../README.md)  
- **Product proposal**: [`../Fundamentals_of_Software_Eng_Proposal.md`](../Fundamentals_of_Software_Eng_Proposal.md)  
- **Frontend app**: [`../frontend/README.md`](../frontend/README.md)
