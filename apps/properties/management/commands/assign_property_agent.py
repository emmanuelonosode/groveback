"""
Management command: assign_property_agent

Puts listings under an agent whose public profile actually resolves.

    python manage.py assign_property_agent --dry-run       # preview
    python manage.py assign_property_agent                 # repair broken links only
    python manage.py assign_property_agent --all           # reassign EVERY property
    python manage.py assign_property_agent --agent-email jerry@example.com

WHY
---
AgentListView and AgentDetailView both filter `role=AGENT, is_active=True`. A property
owned by a staff or admin account therefore renders a "View profile" link to
/agents/<id> that 404s — the id is real, it just isn't served publicly.

That is exactly what happened when the importer picked its owner with `is_staff=True`:
every imported listing went to the admin account rather than the agent one.

Default scope is deliberately narrow — only properties whose current owner would 404 are
touched, so any per-property agent set deliberately in the admin survives. Pass --all to
move everything regardless.

Uses queryset.update(), which bypasses Model.save(). `updated_at` is auto_now, so a
per-row save would restamp thousands of listings and tell Google the whole catalogue
changed — poisoning the <lastmod> signal the sitemap depends on.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role
from apps.properties.models import Property

User = get_user_model()


class Command(BaseCommand):
    help = "Assign properties to an agent whose /agents/<id> page resolves publicly."

    def add_arguments(self, parser):
        parser.add_argument("--agent-email", help="Agent to assign to. Defaults to the lowest-id active AGENT.")
        parser.add_argument("--all", action="store_true", help="Reassign every property, not just broken ones.")
        parser.add_argument("--dry-run", action="store_true", help="Report without writing.")

    def handle(self, *args, **opts):
        email = opts.get("agent_email")
        if email:
            agent = User.objects.filter(email__iexact=email, is_active=True).first()
            if agent is None:
                raise CommandError(f"No active user with email {email!r}.")
            if agent.role != Role.AGENT:
                raise CommandError(
                    f"{agent.email} has role={agent.role}, not AGENT. /agents/{agent.id} would 404. "
                    f"Change their role first, or pick a different user."
                )
        else:
            agent = User.objects.filter(is_active=True, role=Role.AGENT).order_by("id").first()
            if agent is None:
                raise CommandError(
                    "No active role=AGENT user exists. Create one, or promote an existing user, "
                    "otherwise every property page links to a 404."
                )

        qs = Property.objects.all() if opts["all"] else Property.objects.exclude(agent__role=Role.AGENT)
        total = Property.objects.count()
        target = qs.count()

        self.stdout.write(
            f"Agent  : {agent.get_full_name() or agent.email} (id={agent.id}) -> /agents/{agent.id}\n"
            f"Scope  : {'ALL properties' if opts['all'] else 'properties with an unresolvable agent'}\n"
            f"Match  : {target} of {total}\n"
        )

        if opts["dry_run"]:
            for p in qs.select_related("agent")[:10]:
                current = f"{p.agent_id} ({p.agent.role})" if p.agent_id else "none"
                self.stdout.write(f"    {p.slug[:48]:<50} {current} -> {agent.id}")
            self.stdout.write(self.style.WARNING("\nDry run — nothing written."))
            return

        updated = qs.update(agent=agent)
        broken = Property.objects.exclude(agent__role=Role.AGENT).count()

        self.stdout.write(self.style.SUCCESS(
            f"Reassigned {updated} properties.\n"
            f"  still unresolvable: {broken}\n"
            f"  agent now owns    : {Property.objects.filter(agent=agent).count()}"
        ))
