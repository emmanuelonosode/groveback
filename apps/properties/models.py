from django.db import models
from django.utils.text import slugify


class PropertyCondition(models.TextChoices):
    NEW = "new", "New Construction"
    EXCELLENT = "excellent", "Excellent"
    GOOD = "good", "Good"
    FAIR = "fair", "Fair"


class PropertyType(models.TextChoices):
    RESIDENTIAL = "residential", "Residential"
    APARTMENT = "apartment", "Apartment"
    COMMERCIAL = "commercial", "Commercial"
    LAND = "land", "Land"
    CONDO = "condo", "Condo"
    TOWNHOUSE = "townhouse", "Townhouse"


class ListingType(models.TextChoices):
    FOR_SALE = "for-sale", "For Sale"
    FOR_RENT = "for-rent", "For Rent"
    FOR_LEASE = "for-lease", "For Lease"


class PropertyStatus(models.TextChoices):
    AVAILABLE = "available", "Available"
    UNDER_CONTRACT = "under-contract", "Under Contract"
    SOLD = "sold", "Sold"
    RENTED = "rented", "Rented"
    OFF_MARKET = "off-market", "Off Market"


class Property(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=250, unique=True, blank=True)
    description = models.TextField()
    type = models.CharField(max_length=20, choices=PropertyType.choices, default=PropertyType.RESIDENTIAL)
    listing_type = models.CharField(max_length=20, choices=ListingType.choices, default=ListingType.FOR_SALE)
    status = models.CharField(max_length=20, choices=PropertyStatus.choices, default=PropertyStatus.AVAILABLE)

    # Pricing
    # `price` is what the site displays. `original_price` is the untouched source/list
    # price captured at import — the anchor every markdown is computed FROM.
    #
    # Without it a percentage discount is unrepeatable: applying 15% to an already
    # discounted `price` compounds (2000 → 1700 → 1445 → 1228) and the source figure is
    # gone for good after the first run. Deriving from `original_price` instead means
    # sanitize_listings can be re-run any number of times, and the percentage can be
    # changed freely, always landing on the same answer.
    price = models.DecimalField(max_digits=12, decimal_places=2)
    original_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Source list price before any markdown. Set once at import; never overwritten by sanitize_listings.",
    )
    price_label = models.CharField(max_length=20, blank=True, help_text='e.g. "/mo" for rentals')

    # Physical
    bedrooms = models.PositiveIntegerField(default=0)
    bathrooms = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    sqft = models.PositiveIntegerField(default=0)
    lot_size = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Acres")
    year_built = models.PositiveIntegerField(null=True, blank=True)
    garage = models.PositiveIntegerField(default=0)
    stories = models.PositiveIntegerField(default=1)

    # Location
    address = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    zip_code = models.CharField(max_length=10)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    neighborhood = models.CharField(max_length=100, blank=True)

    # Physical condition
    condition = models.CharField(
        max_length=20,
        choices=PropertyCondition.choices,
        default=PropertyCondition.GOOD,
        blank=True,
    )
    cross_street = models.CharField(max_length=200, blank=True, help_text="Nearest cross street")

    # Media
    virtual_tour_url = models.URLField(blank=True, help_text="360-degree virtual tour embed URL")
    tour_360_url = models.URLField(blank=True, help_text="Matterport / Zillow 3D Home URL")

    # Flags
    is_featured = models.BooleanField(default=False)
    homepage_featured = models.BooleanField(
        default=False,
        help_text='Show in the "Available Now" section on the homepage. Independent of the Featured badge.',
    )
    is_published = models.BooleanField(default=False)

    # Raw Schema Data
    raw_data = models.JSONField(default=dict, blank=True, help_text="Stores raw JSON schema data from scrapers")

    # Relations
    agent = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.PROTECT,
        related_name="listings",
        limit_choices_to={"role": "AGENT"},
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Scraped Fields
    available_on = models.CharField(max_length=100, blank=True, null=True)
    is_pet_friendly = models.BooleanField(default=False)
    has_pool = models.BooleanField(default=False)
    allow_selfshow = models.BooleanField(default=False)
    
    # JSON Fields for complex data
    schools = models.JSONField(blank=True, null=True, help_text="List of nearby schools")
    fees = models.JSONField(blank=True, null=True, help_text="Monthly fees and costs")
    floor_plans = models.JSONField(blank=True, null=True, help_text="Floor plan images/data")
    office_info = models.JSONField(blank=True, null=True, help_text="Management office contact info")



    class Meta:
        verbose_name = "Property"
        verbose_name_plural = "Properties"
        ordering = ["-created_at"]
        indexes = [
            # Composite indexes for common filter combinations
            models.Index(fields=["status", "is_published"]),
            models.Index(fields=["city", "state"]),
            models.Index(fields=["listing_type"]),
            models.Index(fields=["is_featured"]),
            # Single-column indexes for map bounding-box and price queries
            models.Index(fields=["latitude"]),
            models.Index(fields=["longitude"]),
            models.Index(fields=["price"]),
            models.Index(fields=["is_published"]),
            models.Index(fields=["bedrooms"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(f"{self.address} {self.city}")
            self.slug = base
            counter = 1
            while Property.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{base}-{counter}"
                counter += 1
        super().save(*args, **kwargs)

    @property
    def primary_image(self):
        return self.images.filter(is_primary=True).first() or self.images.first()


class PropertyImage(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="images")
    image = models.URLField("image", max_length=500)
    caption = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)



    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"Image for {self.property.title}"

    def save(self, *args, **kwargs):
        # Ensure only one primary image per property
        if self.is_primary:
            PropertyImage.objects.filter(property=self.property, is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class AmenityCategory(models.Model):
    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=50, blank=True, help_text="Lucide icon name, e.g. 'home'")
    order = models.PositiveIntegerField(default=0)



    class Meta:
        ordering = ["order"]
        verbose_name = "Amenity Category"
        verbose_name_plural = "Amenity Categories"

    def __str__(self):
        return self.name


class PropertyAmenity(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="amenities")
    category = models.ForeignKey(
        AmenityCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="property_amenities",
    )
    name = models.CharField(max_length=100)



    class Meta:
        verbose_name_plural = "Amenities"

    def __str__(self):
        return self.name

class FavoriteProperty(models.Model):
    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name="favorite_properties")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)



    class Meta:
        verbose_name = "Favorite Property"
        verbose_name_plural = "Favorite Properties"
        unique_together = ("user", "property")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.property.title}"
