"""
Management command: python manage.py seed_blog

Populates the blog with PrimeFamilyHousing's renter-facing guides — the article
bodies live in apps/blog/seed_content.py, this file is just the loader.

Idempotent: posts are matched on their hand-written slug, so re-running updates the
existing rows in place instead of creating duplicates. Safe to run on every deploy.

    python manage.py seed_blog
    python manage.py seed_blog --draft                    # stage without publishing
    python manage.py seed_blog --no-images                # skip image downloads
    python manage.py seed_blog --author-email a@b.com     # attribute to a specific user
"""

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from apps.blog.models import Post
from apps.blog.seed_content import POSTS

User = get_user_model()

IMAGE_TIMEOUT_SECONDS = 30


class Command(BaseCommand):
    help = "Seed the blog with PrimeFamilyHousing's renter guides (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--author-email",
            help="Email of the user to attribute posts to. Defaults to the first active superuser.",
        )
        parser.add_argument(
            "--draft",
            action="store_true",
            help="Seed with is_published=False so nothing goes live until reviewed.",
        )
        parser.add_argument(
            "--no-images",
            action="store_true",
            help="Skip featured-image downloads (useful offline, or to re-run quickly).",
        )

    # ── Author ────────────────────────────────────────────────────────────────
    def resolve_author(self, email):
        """
        Post.author is a required FK with on_delete=PROTECT, so a real user must exist.
        Never create one here — inventing a user to satisfy a seed would put a fake
        byline on published articles.
        """
        if email:
            author = User.objects.filter(email__iexact=email, is_active=True).first()
            if not author:
                raise CommandError(f"No active user with email {email!r}.")
            return author

        author = (
            User.objects.filter(is_active=True, is_superuser=True).order_by("id").first()
            or User.objects.filter(is_active=True, is_staff=True).order_by("id").first()
        )
        if not author:
            raise CommandError(
                "No active superuser or staff user to attribute posts to. "
                "Create one with `python manage.py createsuperuser`, or pass --author-email."
            )
        return author

    # ── Images ────────────────────────────────────────────────────────────────
    def attach_image(self, post, url):
        """
        Download the hero image and save it into MEDIA_ROOT. Failures are warnings, not
        errors: the article is the payload, and a missing hero degrades gracefully (the
        blog index falls back to a stock image).
        """
        if post.featured_image:
            return "kept"

        try:
            import requests

            response = requests.get(url, timeout=IMAGE_TIMEOUT_SECONDS)
            response.raise_for_status()
            post.featured_image.save(f"{post.slug}.jpg", ContentFile(response.content), save=True)
            return "downloaded"
        except Exception as exc:  # noqa: BLE001 — any failure here is non-fatal by design
            self.stdout.write(self.style.WARNING(f"    image failed ({exc.__class__.__name__}: {exc})"))
            return "failed"

    # ── Entry point ───────────────────────────────────────────────────────────
    def handle(self, *args, **options):
        author = self.resolve_author(options.get("author_email"))
        published = not options["draft"]

        self.stdout.write(f"Author:    {author.get_full_name() or author.email}")
        self.stdout.write(f"Publish:   {'yes' if published else 'no (draft)'}")
        self.stdout.write(f"Images:    {'skipped' if options['no_images'] else 'download'}\n")

        created_count = updated_count = image_count = 0

        for entry in POSTS:
            post, created = Post.objects.update_or_create(
                slug=entry["slug"],
                defaults={
                    "title": entry["title"],
                    "excerpt": entry["excerpt"],
                    "content": entry["content"],
                    "category": entry["category"],
                    "tags": entry["tags"],
                    "read_time_minutes": entry["read_time_minutes"],
                    "is_featured": entry.get("is_featured", False),
                    "is_published": published,
                    "author": author,
                },
            )
            created_count += created
            updated_count += not created

            verb = "created" if created else "updated"
            self.stdout.write(f"  {verb}: {post.title[:66]}")

            if not options["no_images"]:
                if self.attach_image(post, entry["image_url"]) == "downloaded":
                    image_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone — {created_count} created, {updated_count} updated, {image_count} images downloaded."
            )
        )
