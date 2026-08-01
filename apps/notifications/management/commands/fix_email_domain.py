"""
Management command: fix_email_domain

Finds and rewrites email addresses still on a pre-rebrand domain. The old
"Hargrove Realty Group" domain survives in DATA (user accounts, the
EmailConfiguration row), not in code — so it shows up in live email links even
though every template is clean:

  * EmailConfiguration.from_email  -> the "From" on every outgoing email
  * User.email (agents)            -> the "Contact Agent" mailto in approval,
                                      inquiry and post-viewing emails

    python manage.py fix_email_domain                       # audit only (default)
    python manage.py fix_email_domain --apply               # rewrite to primefamilyhousing.com
    python manage.py fix_email_domain --old hargrovrealtygroup.com --new primefamilyhousing.com --apply

Dry-run by default. Rewrites only the domain part; the local part (before @) is
untouched, so info@old  ->  info@new.

CAUTION: User.email is the login identifier. Rewriting it changes what an agent
logs in with. That is usually correct after a rebrand, but confirm with the
affected users. Superusers are skipped unless --include-superusers is passed.
"""

import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.notifications.models import EmailConfiguration

User = get_user_model()

# Everything the rebrand left behind. Matched case-insensitively on the domain.
DEFAULT_OLD_DOMAINS = [
    "hargrovrealtygroup.com",
    "hargroverealtygroup.com",
    "hargrove.com",
]


class Command(BaseCommand):
    help = "Audit and rewrite email addresses still on a pre-rebrand domain."

    def add_arguments(self, parser):
        parser.add_argument("--old", action="append", help="Old domain to match (repeatable). Defaults to known rebrand domains.")
        parser.add_argument("--new", default="primefamilyhousing.com", help="Domain to rewrite to.")
        parser.add_argument("--apply", action="store_true", help="Write changes. Omitted = audit only.")
        parser.add_argument("--include-superusers", action="store_true", help="Also rewrite superuser logins (skipped by default).")

    def handle(self, *args, **opts):
        old_domains = [d.lower() for d in (opts["old"] or DEFAULT_OLD_DOMAINS)]
        new = opts["new"].lower().lstrip("@")
        apply = opts["apply"]
        pattern = re.compile(r"@(" + "|".join(re.escape(d) for d in old_domains) + r")$", re.IGNORECASE)

        def rewrite(addr):
            return pattern.sub(f"@{new}", addr or "")

        self.stdout.write(
            f"{'APPLYING' if apply else 'AUDIT (dry-run)'}  "
            f"old={old_domains} -> new=@{new}\n"
        )

        changes = 0

        # ── EmailConfiguration (the sender on every email) ───────────────────
        self.stdout.write("EmailConfiguration rows:")
        found_cfg = False
        for cfg in EmailConfiguration.objects.all():
            hits = {}
            for field in ("from_email", "email_host_user"):
                val = getattr(cfg, field, "") or ""
                new_val = rewrite(val)
                if new_val != val:
                    hits[field] = (val, new_val)
            if "hargrove" in (cfg.display_name or "").lower():
                hits["display_name"] = (cfg.display_name, "PrimeFamilyHousing")
            if hits:
                found_cfg = True
                self.stdout.write(f"  #{cfg.pk} (active={cfg.is_active}):")
                for f, (a, b) in hits.items():
                    self.stdout.write(f"      {f}: {a!r} -> {b!r}")
                changes += len(hits)   # counted in both modes so the audit total is real
                if apply:
                    for f, (_a, b) in hits.items():
                        setattr(cfg, f, b)
                    cfg.save(update_fields=list(hits.keys()))
        if not found_cfg:
            self.stdout.write("  (none on an old domain)")

        # ── User accounts (agent "Contact" links + logins) ───────────────────
        self.stdout.write("\nUser accounts:")
        qs = User.objects.filter(pattern_filter(old_domains))
        if not opts["include_superusers"]:
            qs = qs.exclude(is_superuser=True)
        users = list(qs)
        if not users:
            self.stdout.write("  (none on an old domain)")
        for u in users:
            new_email = rewrite(u.email)
            flag = " [SUPERUSER]" if u.is_superuser else ""
            collision = User.objects.filter(email__iexact=new_email).exclude(pk=u.pk).exists()
            note = "  (collision — would skip)" if collision else ""
            self.stdout.write(f"  id={u.id}{flag}  {u.email!r} -> {new_email!r}{note}")
            if collision:
                if apply:
                    self.stdout.write(self.style.WARNING(
                        f"      SKIPPED — {new_email} already belongs to another account. Merge manually."
                    ))
                continue
            changes += 1
            if apply:
                # This project's CustomUser is email-based (USERNAME_FIELD = "email"),
                # with no concrete username column — only `email` is written.
                u.email = new_email
                u.save(update_fields=["email"])

        # ── Summary ──────────────────────────────────────────────────────────
        if apply:
            self.stdout.write(self.style.SUCCESS(f"\nApplied {changes} change(s)."))
        else:
            self.stdout.write(self.style.WARNING(
                f"\n{changes} change(s) would be made. Re-run with --apply to write them."
            ))


def pattern_filter(old_domains):
    """OR of email__iendswith for each old domain."""
    from django.db.models import Q
    q = Q()
    for d in old_domains:
        q |= Q(email__iendswith=f"@{d}")
    return q
