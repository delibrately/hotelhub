# HotelHub

HotelHub is a Django-based internal management system for small hotels and
guesthouses. The current application manages rooms, guests, and reservations
through server-rendered Django pages.

> The repository is currently configured for local development. A production
> deployment still requires a production database, an HTTPS reverse proxy, a
> WSGI/ASGI server, backups, monitoring, and environment-specific host/domain
> configuration.

## Requirements

- Python 3.12 or 3.13 (development is tested with Python 3.13)
- Django 5.2.16 LTS, pinned in `requirements.txt`

No Node.js frontend or additional third-party Python package is required.

## Local setup

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Copy the example environment file and replace the example secret with a newly
generated development value:

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

The project intentionally does not add a package that automatically reads
`.env`. Export the variables into the current shell before running Django:

```bash
set -a
source .env
set +a
```

Supported variables:

- `DJANGO_SECRET_KEY`: required whenever `DJANGO_DEBUG=false`.
- `DJANGO_DEBUG`: accepts `true/false`, `1/0`, `yes/no`, or `on/off`.
- `DJANGO_ALLOWED_HOSTS`: comma-separated hostnames. Local development defaults
  to `localhost,127.0.0.1,[::1]`.
- `DJANGO_SECURE_HSTS_SECONDS`: production HSTS duration; ignored in debug mode.

For deployment tooling that already provides conventional names, `DEBUG`,
`SECRET_KEY`, and `ALLOWED_HOSTS` are accepted as fallbacks. The `DJANGO_*`
names take precedence when both forms are present.

The committed `.env.example` contains examples only. `.env`, SQLite databases,
collected static files, and local settings are ignored by Git.

## Database and administrator

Apply migrations:

```bash
python manage.py migrate
```

Create a superuser interactively. Do not store its password in source control:

```bash
python manage.py createsuperuser
```

Run the development server:

```bash
python manage.py runserver
```

The Django Admin is available at `http://127.0.0.1:8000/admin/`.

## Staff accounts and permissions

An internal business user needs both:

1. `is_staff=True`; and
2. the relevant Django model permissions.

The safest workflow is to sign in to Django Admin as a superuser, open
**Authentication and Authorization → Groups**, create a group such as
`Front Desk`, assign only the required permissions, and then add users to that
group.

Common permissions are:

- Rooms: `room.view_room`, `room.add_room`, `room.change_room`
- Guests: `guest.view_guest`, `guest.add_guest`, `guest.change_guest`
- Masked government ID: `guest.view_guest_sensitive_data`
- Reservations: `main.view_reservation`, `main.add_reservation`,
  `main.change_reservation`
- Reservation status operations: `main.manage_reservation_status` together with
  `main.view_reservation`
- Read-only administrator operation logs: `main.view_adminoperationlog`

Set staff status from Django Admin, or from an interactive shell after selecting
the intended user:

```bash
python manage.py shell
```

```python
from django.contrib.auth import get_user_model

user = get_user_model().objects.get(username="employee_username")
user.is_staff = True
user.save(update_fields=["is_staff"])
```

Model permissions can also be assigned in Django Admin under the user's
**User permissions** field. Superusers automatically have all permissions.

## Reservation status workflow

New reservations start as `pending`. Existing reservations are migrated to
`confirmed`. The allowed workflow is deliberately restricted:

```text
pending   -> confirmed | cancelled | no_show
confirmed -> checked_in | cancelled | no_show
checked_in -> checked_out
checked_out, cancelled, no_show -> terminal
```

Only `pending`, `confirmed`, and `checked_in` reservations occupy room
inventory. `cancelled`, `no_show`, and `checked_out` reservations release their
date range. Date ranges remain half-open: `[check_in_date, check_out_date)`.

Status changes use explicit POST actions and are handled by `main/services.py`.
The service reloads the reservation inside `transaction.atomic()`, requests
`select_for_update()` locks, validates the transition and business date, then
writes the status and audit log in the same transaction.

SQLite does not provide effective row-level `SELECT FOR UPDATE` locking. The
service still re-queries the room and active reservations, but SQLite cannot
fully prevent two simultaneous requests from both passing the overlap check.
A production deployment that accepts concurrent bookings should use a database
with row-level locking, such as PostgreSQL, and keep the service-layer
transaction boundary.

## Operation logs

Reservation, room, and guest creation/update actions and every reservation
status transition create an `AdminOperationLog`. The business log page is
read-only and requires `main.view_adminoperationlog`.

Descriptions contain only model type, database ID, action, and safe field
categories. They intentionally exclude guest names, phone numbers, government
IDs, addresses, passwords, secrets, reservation `additional` content, and any
future internal note body. Logs cannot be edited or deleted through the normal
management UI or Django Admin.

## Tests and checks

Run the automated test suite:

```bash
python manage.py test
```

Run Django's normal checks and verify that models match migration files:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
```

Before deployment, provide real production environment values and run:

```bash
DJANGO_DEBUG=false \
DJANGO_SECRET_KEY='replace-with-a-real-long-random-secret' \
DJANGO_ALLOWED_HOSTS='hotel.example.com' \
python manage.py check --deploy
```

## Production notes

When `DJANGO_DEBUG=false`, secure session/CSRF cookies, HTTPS redirect, and HSTS
are enabled. Before enabling a production site:

- terminate HTTPS correctly at the web server or reverse proxy;
- configure proxy HTTPS headers explicitly for that deployment;
- use a real domain in `DJANGO_ALLOWED_HOSTS`;
- use a strong secret supplied by the deployment environment;
- configure a production database and automated backups;
- run `python manage.py collectstatic` and serve static files separately;
- use a production WSGI/ASGI server instead of `runserver`;
- review HSTS settings before adding the domain to browser preload lists.

Never commit user passwords, guest identity documents, phone exports, database
files, or deployment secrets.
