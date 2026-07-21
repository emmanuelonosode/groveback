# Celery on a VPS (systemd) — PrimeFamilyHousing

Runs a **worker** (async tasks) and **beat** (scheduler). Beat enables the
already-defined jobs: abandoned-application recovery, weekly lead follow-up,
viewing reminders, and draining the analytics telemetry spool every minute.

Prereqs: a VPS with `sudo`, Redis installed, the project deployed, and the
backend virtualenv created.

---

## 1. Make sure Redis is running

```bash
sudo systemctl enable --now redis-server   # Debian/Ubuntu (RHEL: redis)
redis-cli ping                              # must print: PONG
```

If your Redis needs a password or a non-default port, set it in the backend env
(next step). Otherwise the default `redis://localhost:6379/0` is used.

## 2. Point the app at your Redis

In the backend `.env` (production env file), set:

```
REDIS_URL=redis://localhost:6379/0
```

(Use `redis://:PASSWORD@localhost:6379/0` if you configured a password.)

## 3. Install deps + run migrations (creates the scheduler tables)

```bash
cd /full/path/to/backend
source venv/bin/activate
pip install -r requirements/base.txt
python manage.py migrate          # includes django_celery_beat tables
```

## 4. Find the three values you'll plug in

```bash
whoami                            # -> your USER
pwd                               # run inside the backend folder -> PROJECT DIR
which celery                      # with venv active -> CELERY_BIN path
```

## 5. Install the env file

```bash
sudo cp deploy/etc-default-celery /etc/default/celery
sudo nano /etc/default/celery     # fill CELERY_BIN and CELERYD_CHDIR
```

## 6. Install the systemd services

Edit `deploy/celery.service` and `deploy/celerybeat.service`: replace
`<REPLACE_USER>` (your user) and `<REPLACE: /full/path/to/backend>` (WorkingDirectory).
Then:

```bash
sudo cp deploy/celery.service /etc/systemd/system/celery.service
sudo cp deploy/celerybeat.service /etc/systemd/system/celerybeat.service
sudo systemctl daemon-reload
sudo systemctl enable --now celery celerybeat
```

## 7. Verify

```bash
sudo systemctl status celery celerybeat        # both: active (running)
sudo tail -n 50 /var/log/celery/w1*.log        # worker log
sudo tail -n 50 /var/log/celery/beat.log       # beat log (shows scheduled sends)

# Worker reachable?
cd /full/path/to/backend && source venv/bin/activate
celery -A config inspect ping                  # -> pong
```

Within ~1 minute, the analytics spool should drain on its own
(Admin → Raw Telemetry Events: `processed=False` count near zero).

## Day-to-day

```bash
sudo systemctl restart celery celerybeat       # after a deploy / code change
sudo journalctl -u celery -f                   # live worker logs
```

## Notes

- **One beat only.** Never run two beat processes — duplicate scheduled sends.
- After every code deploy, `systemctl restart celery celerybeat` so they load new code.
- Emails still also work synchronously without Celery; the worker just makes
  scheduled jobs and heavier tasks run out-of-band.
