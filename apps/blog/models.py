from django.db import models
from django.utils.text import slugify
from cloudinary.models import CloudinaryField


class PostCategory(models.TextChoices):
    MARKET_ANALYSIS = "MARKET_ANALYSIS", "Market Analysis"
    BUYERS_GUIDE    = "BUYERS_GUIDE",    "Buyer's Guide"
    SELLERS_GUIDE   = "SELLERS_GUIDE",   "Seller's Guide"
    INVESTMENT      = "INVESTMENT",      "Investment"
    MARKET_UPDATE   = "MARKET_UPDATE",   "Market Update"


class Post(models.Model):
    title             = models.CharField(max_length=300)
    slug              = models.SlugField(max_length=320, unique=True, blank=True)
    excerpt           = models.TextField()
    content           = models.TextField(help_text="HTML content is supported.")
    category          = models.CharField(max_length=30, choices=PostCategory.choices)
    author            = models.ForeignKey(
                            "accounts.CustomUser",
                            on_delete=models.PROTECT,
                            related_name="blog_posts",
                            limit_choices_to={"is_active": True},
                        )
    featured_image    = CloudinaryField("featured_image", blank=True, null=True)
    is_published      = models.BooleanField(default=False)
    is_featured       = models.BooleanField(default=False)
    published_at      = models.DateTimeField(null=True, blank=True)
    tags              = models.JSONField(default=list, blank=True)
    read_time_minutes = models.PositiveIntegerField(default=5)
    created_at        = models.DateTimeField(auto_now_add=True)
    updated_at        = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["is_published", "is_featured"]),
            models.Index(fields=["category", "is_published"]),
            models.Index(fields=["slug"]),
        ]
        verbose_name = "Post"
        verbose_name_plural = "Posts"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Auto-generate unique slug from title
        if not self.slug:
            base = slugify(self.title)[:300]
            self.slug = base
            counter = 1
            while Post.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{base}-{counter}"
                counter += 1
        # Auto-set published_at when first published
        if self.is_published and not self.published_at:
            from django.utils import timezone
            self.published_at = timezone.now()
        super().save(*args, **kwargs)
