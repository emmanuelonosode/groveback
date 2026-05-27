import uuid

from django.db import models


def _generate_referral_code():
    return uuid.uuid4().hex[:8].upper()


class LeadSource(models.TextChoices):
    CONTACT_FORM = "CONTACT_FORM", "Contact Form"
    PROPERTY_INQUIRY = "PROPERTY_INQUIRY", "Property Inquiry"
    AGENT_INQUIRY = "AGENT_INQUIRY", "Agent Inquiry"
    REFERRAL = "REFERRAL", "Referral"
    GOOGLE = "GOOGLE", "Google"
    INSTAGRAM = "INSTAGRAM", "Instagram"
    FACEBOOK = "FACEBOOK", "Facebook"
    DIRECT = "DIRECT", "Direct"


class InterestType(models.TextChoices):
    BUY = "BUY", "Buy"
    RENT = "RENT", "Rent"
    SELL = "SELL", "Sell"
    INVEST = "INVEST", "Invest"


class LeadStatus(models.TextChoices):
    NEW = "NEW", "New"
    CONTACTED = "CONTACTED", "Contacted"
    QUALIFIED = "QUALIFIED", "Qualified"
    VIEWING = "VIEWING", "Viewing Scheduled"
    NEGOTIATING = "NEGOTIATING", "Negotiating"
    CONVERTED = "CONVERTED", "Converted"
    LOST = "LOST", "Lost"


class MoveInTimeline(models.TextChoices):
    ASAP          = "ASAP",          "As Soon As Possible"
    ONE_THREE     = "1_3_MONTHS",    "1–3 Months"
    THREE_SIX     = "3_6_MONTHS",    "3–6 Months"
    SIX_PLUS      = "6_PLUS",        "6+ Months"
    JUST_BROWSING = "JUST_BROWSING", "Just Browsing"


class PreferredContact(models.TextChoices):
    PHONE = "PHONE", "Phone Call"
    TEXT  = "TEXT",  "Text / SMS"
    EMAIL = "EMAIL", "Email"


class ActivityType(models.TextChoices):
    CALL = "CALL", "Phone Call"
    EMAIL = "EMAIL", "Email"
    NOTE = "NOTE", "Note"
    STATUS_CHANGE = "STATUS_CHANGE", "Status Change"
    VIEWING_BOOKED = "VIEWING_BOOKED", "Viewing Booked"


class Lead(models.Model):
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    source = models.CharField(max_length=30, choices=LeadSource.choices, default=LeadSource.CONTACT_FORM)
    interest_type = models.CharField(max_length=10, choices=InterestType.choices, default=InterestType.BUY)

    # Budget
    budget_min = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    budget_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    preferred_location = models.CharField(max_length=200, blank=True)

    # Property / agent interest (from inquiry forms)
    property_interest = models.ForeignKey(
        "properties.Property",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="inquiries",
    )
    agent_interest = models.ForeignKey(
        "accounts.CustomUser",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="requested_leads",
    )

    # What services they're interested in
    services_requested = models.JSONField(
        default=list,
        blank=True,
        help_text='e.g. ["Buyer Representation", "Property Valuation"]',
    )

    message = models.TextField(blank=True)

    # UTM attribution — captured from the landing URL
    utm_source   = models.CharField(max_length=100, blank=True)
    utm_medium   = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=200, blank=True)

    # Geo-intelligence — city detected from browser IP or search intent
    detected_city  = models.CharField(max_length=100, blank=True)

    # Lead intelligence — lifecycle, household, contact preference
    move_in_timeline  = models.CharField(
        max_length=20, choices=MoveInTimeline.choices, blank=True,
        help_text="How soon the prospect wants to move — key urgency signal"
    )
    occupants_count   = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Total number of people who will live in the property"
    )
    has_pets          = models.BooleanField(
        null=True, blank=True,
        help_text="Whether the prospect has pets — affects property eligibility"
    )
    preferred_contact = models.CharField(
        max_length=10, choices=PreferredContact.choices, blank=True,
        help_text="How the prospect prefers to be reached"
    )
    referral_source   = models.CharField(
        max_length=150, blank=True,
        help_text="How the prospect heard about us (self-reported)"
    )

    referral_code = models.CharField(
        max_length=20, blank=True,
        help_text="Referral code used when this lead was captured (links to a Referrer)",
        db_index=True,
    )

    drip_opted_out = models.BooleanField(default=False,
        help_text="Suppress automated drip sequence for this lead")

    # CRM pipeline
    status = models.CharField(max_length=20, choices=LeadStatus.choices, default=LeadStatus.NEW)
    assigned_agent = models.ForeignKey(
        "accounts.CustomUser",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_leads",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_contacted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["assigned_agent", "status"]),
            models.Index(fields=["source"]),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.get_status_display()})"

    @property
    def lead_score(self) -> int:
        from django.utils import timezone as tz
        score = 0
        if self.source == LeadSource.PROPERTY_INQUIRY:                   score += 25
        if self.phone:                                                     score += 15
        if self.property_interest_id:                                      score += 15
        if self.budget_min or self.budget_max:                             score += 10
        if self.utm_source in ("google", "facebook", "instagram"):        score += 10
        # Urgency signal — move-in timeline
        if self.move_in_timeline == MoveInTimeline.ASAP:                  score += 15
        elif self.move_in_timeline in (MoveInTimeline.ONE_THREE, MoveInTimeline.THREE_SIX): score += 8
        # Engagement signals — more info filled = higher intent
        if self.occupants_count:                                           score += 5
        if self.has_pets is not None:                                      score += 3
        if self.preferred_contact:                                         score += 4
        score += min(self.activities.count() * 5, 20)
        days_old = (tz.now() - self.created_at).days
        if days_old > 30 and self.status == LeadStatus.NEW:               score -= 15
        if self.status == LeadStatus.LOST:                                 score  = max(score - 30, 0)
        if self.status in (LeadStatus.CONVERTED, LeadStatus.NEGOTIATING): score = min(score + 20, 100)
        return min(max(score, 0), 100)


class LeadActivity(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="activities")
    agent = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.PROTECT,
        related_name="lead_activities",
    )
    activity_type = models.CharField(max_length=20, choices=ActivityType.choices)
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Lead Activity"
        verbose_name_plural = "Lead Activities"

    def __str__(self):
        return f"{self.get_activity_type_display()} on {self.lead}"


class Client(models.Model):
    """A Lead that has been converted into a paying client."""
    user = models.OneToOneField(
        "accounts.CustomUser",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="client_profile",
        help_text="Portal access account — created when client registers.",
    )
    lead = models.OneToOneField(Lead, on_delete=models.PROTECT, related_name="client")
    preferred_agent = models.ForeignKey(
        "accounts.CustomUser",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="clients",
    )
    kyc_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Client: {self.lead.full_name}"

    @property
    def full_name(self):
        return self.lead.full_name

    @property
    def email(self):
        return self.lead.email


class ApplicationStatus(models.TextChoices):
    DRAFT                = "DRAFT",                "Draft"
    PENDING_PAYMENT      = "PENDING_PAYMENT",      "Pending Payment"
    PENDING_VERIFICATION = "PENDING_VERIFICATION", "Pending Verification"
    SUBMITTED            = "SUBMITTED",            "Submitted"
    REVIEWED             = "REVIEWED",             "Reviewed"
    APPROVED             = "APPROVED",             "Approved"
    REJECTED             = "REJECTED",             "Rejected"
    PAYMENT_FAILED       = "PAYMENT_FAILED",       "Payment Failed"


class RentalApplication(models.Model):
    # ── Application Meta ──────────────────────────────────────────────────────
    application_fee = models.DecimalField(max_digits=10, decimal_places=2, default=100.00)
    is_fee_paid     = models.BooleanField(default=False)
    payment_intent_id = models.CharField(max_length=200, blank=True, null=True)

    # ── Personal Info ─────────────────────────────────────────────────────────
    first_name  = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name   = models.CharField(max_length=100)
    email       = models.EmailField()
    cell_phone  = models.CharField(max_length=20)
    home_phone  = models.CharField(max_length=20, blank=True)

    # ── Household ─────────────────────────────────────────────────────────────
    has_kids       = models.BooleanField(default=False)
    number_of_kids = models.PositiveIntegerField(default=0)

    # ── Current Address ───────────────────────────────────────────────────────
    present_address = models.CharField(max_length=300)
    city            = models.CharField(max_length=100)
    state           = models.CharField(max_length=50)
    zip_code        = models.CharField(max_length=10)

    # ── Rental Intent ─────────────────────────────────────────────────────────
    move_in_date           = models.DateField()
    intended_stay_duration = models.CharField(max_length=100, help_text='e.g. "12 months"')
    months_rent_upfront    = models.PositiveIntegerField(default=1)

    # ── Personal extras ───────────────────────────────────────────────────────
    marital_status                 = models.CharField(max_length=20, blank=True)
    preferred_contact              = models.CharField(max_length=10, blank=True)
    phone_type                     = models.CharField(max_length=10, blank=True)
    emergency_contact_name         = models.CharField(max_length=100, blank=True)
    emergency_contact_relationship = models.CharField(max_length=50, blank=True)
    emergency_contact_phone        = models.CharField(max_length=20, blank=True)
    emergency_contact_phone_type   = models.CharField(max_length=10, blank=True)

    # ── Identity ──────────────────────────────────────────────────────────────
    date_of_birth           = models.DateField(null=True, blank=True)
    id_type                 = models.CharField(max_length=10, blank=True)
    ssn_last4               = models.CharField(max_length=4, blank=True)
    ssn_encrypted           = models.TextField(
        blank=True, default="",
        help_text="Full SSN encrypted at rest (Fernet/AES). Never edit directly. Superadmin-only via admin panel.",
    )
    ein                     = models.CharField(max_length=10, blank=True)
    has_drivers_license     = models.BooleanField(default=True)
    drivers_license_number  = models.CharField(max_length=50, blank=True)
    drivers_license_state   = models.CharField(max_length=2, blank=True)

    # ── Income / Employment ───────────────────────────────────────────────────
    gross_monthly_income  = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    employer_name         = models.CharField(max_length=200, blank=True)
    employer_phone        = models.CharField(max_length=20, blank=True)
    job_title             = models.CharField(max_length=100, blank=True)
    employment_start_date = models.DateField(null=True, blank=True)

    # ── Address history ───────────────────────────────────────────────────────
    how_long_at_address   = models.CharField(max_length=50, blank=True)
    reason_for_leaving    = models.CharField(max_length=300, blank=True)
    current_landlord_name = models.CharField(max_length=100, blank=True)
    current_landlord_phone = models.CharField(max_length=20, blank=True)

    # ── Lifestyle ─────────────────────────────────────────────────────────────
    has_pets        = models.BooleanField(default=False)
    pet_description = models.CharField(max_length=300, blank=True)
    smokes          = models.BooleanField(default=False)
    drinks          = models.BooleanField(default=False)

    # ── Household extras ──────────────────────────────────────────────────────
    has_vehicles      = models.BooleanField(default=False)
    number_of_vehicles = models.PositiveIntegerField(default=0)
    animals           = models.JSONField(default=list, blank=True)

    # ── Background ────────────────────────────────────────────────────────────
    has_felony_eviction_bankruptcy = models.BooleanField(null=True, blank=True)
    is_active_military             = models.BooleanField(null=True, blank=True)
    has_housing_assistance         = models.BooleanField(null=True, blank=True)

    # ── Relations ─────────────────────────────────────────────────────────────
    rental_property = models.ForeignKey(
        "properties.Property",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="rental_applications",
    )
    lead = models.ForeignKey(
        Lead,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="rental_applications",
    )

    # ── Status & Meta ─────────────────────────────────────────────────────────
    status       = models.CharField(max_length=20, choices=ApplicationStatus.choices, default=ApplicationStatus.DRAFT)
    submitted_at = models.DateTimeField(auto_now_add=True)
    ip_address   = models.GenericIPAddressField(null=True, blank=True)

    # ── UTM Attribution ───────────────────────────────────────────────────────
    utm_source   = models.CharField(max_length=100, blank=True)
    utm_medium   = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=200, blank=True)

    # ── Recovery Email ────────────────────────────────────────────────────────
    recovery_email_sent = models.BooleanField(default=False)

    # ── Legal ─────────────────────────────────────────────────────────────────
    certification_text = models.CharField(
        max_length=500,
        blank=True,
        help_text="Auto-populated: applicant certifies information is true.",
    )

    # ── Generated PDF ─────────────────────────────────────────────────────────
    application_pdf = models.CharField(
        max_length=500,
        blank=True,
        help_text="Cloudinary URL of the generated application PDF.",
    )

    class Meta:
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["email"]),
            models.Index(fields=["rental_property", "status"]),
        ]
        verbose_name = "Rental Application"
        verbose_name_plural = "Rental Applications"

    def __str__(self):
        prop = str(self.rental_property) if self.rental_property else "No property"
        return f"{self.full_name} — {prop}"

    @property
    def full_name(self):
        parts = [self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        parts.append(self.last_name)
        return " ".join(parts)

    def save(self, *args, **kwargs):
        # Auto-generate certification text
        if not self.certification_text:
            self.certification_text = (
                f"I, {self.full_name}, certify that the answers given herein are true and "
                f"complete to the best of my knowledge. I authorize investigation of all "
                f"statements contained in this application."
            )
        # Auto-link to an existing Lead by email
        if not self.lead_id and self.email:
            match = Lead.objects.filter(email=self.email).order_by("-created_at").first()
            if match:
                self.lead = match
        super().save(*args, **kwargs)


# ── Referral Program ──────────────────────────────────────────────────────────

class Referrer(models.Model):
    """A person who refers prospective tenants and earns a commission."""
    name  = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    code  = models.CharField(
        max_length=20, unique=True, default=_generate_referral_code,
        help_text="Unique code shared in referral links (?ref=CODE)",
    )
    is_active = models.BooleanField(default=True)
    notes     = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def referral_link_path(self):
        return f"/?ref={self.code}"


class ReferralStatus(models.TextChoices):
    PENDING   = "PENDING",   "Pending"
    CONVERTED = "CONVERTED", "Tenant Converted"
    PAID      = "PAID",      "Commission Paid"
    VOID      = "VOID",      "Void"


class ReferralPayout(models.Model):
    """
    Tracks one referral event — referrer → lead → (optionally) paying tenant.
    Commission = monthly_rent × commission_months × commission_rate
    Default: 40% of first 2 months = 80% of one month's rent.
    """
    referrer = models.ForeignKey(
        Referrer, on_delete=models.PROTECT, related_name="payouts",
    )
    lead = models.ForeignKey(
        Lead, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="referral_payout",
    )
    rental_application = models.ForeignKey(
        RentalApplication, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="referral_payout",
    )
    status = models.CharField(
        max_length=20, choices=ReferralStatus.choices, default=ReferralStatus.PENDING,
    )
    monthly_rent     = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Actual rent amount — set when tenant pays first month",
    )
    commission_rate   = models.DecimalField(max_digits=4, decimal_places=2, default=0.40,
        help_text="Fraction of monthly rent paid per month (default 40%)",
    )
    commission_months = models.PositiveSmallIntegerField(default=2,
        help_text="Number of months the commission applies to (default 2)",
    )
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Auto-calculated: monthly_rent × commission_months × commission_rate",
    )
    notes        = models.TextField(blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    converted_at = models.DateTimeField(null=True, blank=True)
    paid_at      = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Referral Payout"
        verbose_name_plural = "Referral Payouts"

    def __str__(self):
        return f"{self.referrer.name} → {self.lead or 'unlinked lead'}"

    def calculate_commission(self):
        if self.monthly_rent:
            return self.monthly_rent * self.commission_months * self.commission_rate
        return None

    def save(self, *args, **kwargs):
        if self.monthly_rent and not self.commission_amount:
            self.commission_amount = self.calculate_commission()
        super().save(*args, **kwargs)
