from rest_framework import serializers
from .models import Lead, LeadActivity, Client, LeadStatus, RentalApplication, ApplicationStatus, Referrer, ReferralPayout, ReferralStatus  # noqa: F401


class LeadCreateSerializer(serializers.ModelSerializer):
    """Used by public inquiry forms — minimal required fields."""

    # Phone-first strategy: email is optional so callback-only leads can be captured
    email = serializers.EmailField(required=False, allow_blank=True, default="")

    class Meta:
        model = Lead
        fields = [
            "id", "full_name", "email", "phone",
            "source", "interest_type",
            "budget_min", "budget_max", "preferred_location",
            "property_interest", "agent_interest",
            "services_requested", "message",
            "utm_source", "utm_medium", "utm_campaign",
            "detected_city",
            # Lead intelligence
            "move_in_timeline", "occupants_count", "has_pets",
            "preferred_contact", "referral_source",
            # Referral program
            "referral_code",
        ]

    def validate_services_requested(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Must be a list.")
        return value

    def create(self, validated_data):
        instance = super().create(validated_data)
        # Auto-create a ReferralPayout record if the code matches a live Referrer
        code = instance.referral_code.strip().upper() if instance.referral_code else ""
        if code:
            try:
                referrer = Referrer.objects.get(code=code, is_active=True)
                ReferralPayout.objects.create(referrer=referrer, lead=instance)
            except Referrer.DoesNotExist:
                pass
        return instance


class LeadActivitySerializer(serializers.ModelSerializer):
    agent_name = serializers.CharField(source="agent.full_name", read_only=True)

    class Meta:
        model = LeadActivity
        fields = ["id", "activity_type", "note", "agent", "agent_name", "created_at"]
        read_only_fields = ["id", "created_at"]


class LeadListSerializer(serializers.ModelSerializer):
    """Lightweight — for kanban and list views."""
    assigned_agent_name = serializers.CharField(source="assigned_agent.full_name", read_only=True, default=None)
    property_title = serializers.CharField(source="property_interest.title", read_only=True, default=None)

    class Meta:
        model = Lead
        fields = [
            "id", "full_name", "email", "phone",
            "source", "interest_type", "status",
            "assigned_agent", "assigned_agent_name",
            "property_interest", "property_title",
            "budget_min", "budget_max",
            "created_at", "last_contacted_at",
        ]


class LeadDetailSerializer(serializers.ModelSerializer):
    activities = LeadActivitySerializer(many=True, read_only=True)
    assigned_agent_name = serializers.CharField(source="assigned_agent.full_name", read_only=True, default=None)
    property_title = serializers.CharField(source="property_interest.title", read_only=True, default=None)

    class Meta:
        model = Lead
        fields = [
            "id", "full_name", "email", "phone",
            "source", "interest_type", "status",
            "budget_min", "budget_max", "preferred_location",
            "property_interest", "property_title",
            "agent_interest",
            "services_requested", "message",
            "assigned_agent", "assigned_agent_name",
            "activities",
            "created_at", "updated_at", "last_contacted_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class LeadAssignSerializer(serializers.Serializer):
    agent_id = serializers.IntegerField()

    def validate_agent_id(self, value):
        from apps.accounts.models import CustomUser, Role
        try:
            CustomUser.objects.get(id=value, role=Role.AGENT, is_active=True)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError("Active agent not found.")
        return value


class ClientSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="lead.full_name", read_only=True)
    email = serializers.CharField(source="lead.email", read_only=True)
    phone = serializers.CharField(source="lead.phone", read_only=True)
    preferred_agent_name = serializers.CharField(source="preferred_agent.full_name", read_only=True, default=None)
    lead_source = serializers.CharField(source="lead.source", read_only=True)
    interest_type = serializers.CharField(source="lead.interest_type", read_only=True)

    class Meta:
        model = Client
        fields = [
            "id", "full_name", "email", "phone",
            "lead", "lead_source", "interest_type",
            "preferred_agent", "preferred_agent_name",
            "kyc_verified", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


_NEW_FIELDS = [
    # Personal extras
    "marital_status", "preferred_contact", "phone_type",
    "emergency_contact_name", "emergency_contact_relationship",
    "emergency_contact_phone", "emergency_contact_phone_type",
    # Identity (ssn_last4 is read-only derived; ssn is write-only on create)
    "date_of_birth", "id_type", "ssn_last4", "ein",
    "has_drivers_license", "drivers_license_number", "drivers_license_state",
    # Income / Employment
    "gross_monthly_income", "employer_name", "employer_phone",
    "job_title", "employment_start_date",
    # Address history
    "how_long_at_address", "reason_for_leaving",
    "current_landlord_name", "current_landlord_phone",
    # Household extras
    "has_vehicles", "number_of_vehicles", "animals",
    # Background
    "has_felony_eviction_bankruptcy", "is_active_military", "has_housing_assistance",
]


class RentalApplicationCreateSerializer(serializers.ModelSerializer):
    """Used by the public /apply form (no payment required)."""

    rental_property = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=__import__("apps.properties.models", fromlist=["Property"]).Property.objects.filter(is_published=True),
        required=False,
        allow_null=True,
    )

    # Write-only: frontend sends full SSN (XXX-XX-XXXX or 9 digits).
    # Encrypted into ssn_encrypted on save; ssn_last4 is auto-derived.
    ssn = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        max_length=11,
        help_text="Full SSN (XXX-XX-XXXX). Encrypted before storage.",
    )

    class Meta:
        model = RentalApplication
        fields = [
            "id",
            "first_name", "middle_name", "last_name",
            "email", "cell_phone", "home_phone",
            "has_kids", "number_of_kids",
            "present_address", "city", "state", "zip_code",
            "move_in_date", "intended_stay_duration", "months_rent_upfront",
            "has_pets", "pet_description",
            "smokes", "drinks",
            "rental_property",
            "certification_text",
            "application_fee", "is_fee_paid", "status",
            "utm_source", "utm_medium", "utm_campaign",
            "ssn",
        ] + _NEW_FIELDS
        read_only_fields = ["id", "application_fee", "is_fee_paid", "status", "ssn_last4"]

    def validate(self, data):
        if data.get("has_kids") and not data.get("number_of_kids"):
            raise serializers.ValidationError(
                {"number_of_kids": "Please specify how many children."}
            )
        return data

    def create(self, validated_data):
        raw_ssn = validated_data.pop("ssn", "").strip()
        instance = super().create(validated_data)
        if raw_ssn:
            from apps.notifications.encryption import encrypt_ssn
            cleaned = raw_ssn.replace("-", "").replace(" ", "")
            instance.ssn_encrypted = encrypt_ssn(raw_ssn)
            instance.ssn_last4 = cleaned[-4:] if len(cleaned) >= 4 else cleaned
            instance.save(update_fields=["ssn_encrypted", "ssn_last4"])
        return instance


class RentalApplicationDraftSerializer(serializers.ModelSerializer):
    """
    Used by POST /api/v1/leads/apply/save-draft/
    All fields optional except email (minimum for admin follow-up).
    Accepts partial data from any step of the form.
    """

    rental_property = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=__import__("apps.properties.models", fromlist=["Property"]).Property.objects.filter(is_published=True),
        required=False,
        allow_null=True,
    )

    _draft_base = [
        "first_name", "middle_name", "last_name",
        "cell_phone", "home_phone",
        "has_kids", "number_of_kids",
        "present_address", "city", "state", "zip_code",
        "move_in_date", "intended_stay_duration", "months_rent_upfront",
        "has_pets", "pet_description",
        "smokes", "drinks",
        "rental_property",
        "utm_source", "utm_medium", "utm_campaign",
    ]

    class Meta:
        model = RentalApplication
        fields = [
            "id",
            "first_name", "middle_name", "last_name",
            "email", "cell_phone", "home_phone",
            "has_kids", "number_of_kids",
            "present_address", "city", "state", "zip_code",
            "move_in_date", "intended_stay_duration", "months_rent_upfront",
            "has_pets", "pet_description",
            "smokes", "drinks",
            "rental_property",
            "utm_source", "utm_medium", "utm_campaign",
        ] + _NEW_FIELDS
        extra_kwargs = {f: {"required": False} for f in [
            "first_name", "middle_name", "last_name",
            "cell_phone", "home_phone",
            "has_kids", "number_of_kids",
            "present_address", "city", "state", "zip_code",
            "move_in_date", "intended_stay_duration", "months_rent_upfront",
            "has_pets", "pet_description",
            "smokes", "drinks",
            "rental_property",
            "utm_source", "utm_medium", "utm_campaign",
        ] + _NEW_FIELDS}


class RentalApplicationLatestProfileSerializer(serializers.ModelSerializer):
    """Used to pre-fill the form for returning applicants."""
    class Meta:
        model = RentalApplication
        fields = [
            "first_name", "middle_name", "last_name",
            "email", "cell_phone", "home_phone",
            "marital_status", "phone_type", "preferred_contact",
            "emergency_contact_name", "emergency_contact_relationship",
            "emergency_contact_phone", "emergency_contact_phone_type",
            "date_of_birth", "id_type", "ssn_last4", "ein",
            "has_drivers_license", "drivers_license_number", "drivers_license_state",
            "gross_monthly_income", "employer_name", "employer_phone",
            "job_title", "employment_start_date",
            "has_kids", "number_of_kids",
            "has_vehicles", "number_of_vehicles",
            "present_address", "city", "state", "zip_code",
            "how_long_at_address",
            "intended_stay_duration", "months_rent_upfront",
            "has_pets", "pet_description", "animals",
            "smokes", "drinks",
        ]
class RentalApplicationAdminSerializer(serializers.ModelSerializer):
    """Full serializer for staff views."""
    full_name      = serializers.CharField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    property_title = serializers.CharField(source="rental_property.title", read_only=True, default=None)
    lead_name      = serializers.SerializerMethodField()

    class Meta:
        model = RentalApplication
        fields = "__all__"
        read_only_fields = ["submitted_at", "application_pdf", "ip_address"]

    def get_lead_name(self, obj):
        return obj.lead.full_name if obj.lead else None


class ReferrerSerializer(serializers.ModelSerializer):
    payout_count = serializers.SerializerMethodField()
    total_earned = serializers.SerializerMethodField()

    class Meta:
        model = Referrer
        fields = [
            "id", "name", "email", "phone", "code",
            "is_active", "notes", "created_at",
            "payout_count", "total_earned",
        ]
        read_only_fields = ["id", "code", "created_at"]

    def get_payout_count(self, obj):
        return obj.payouts.count()

    def get_total_earned(self, obj):
        from django.db.models import Sum  # local — serializers don't import db.models at module level
        result = obj.payouts.filter(status=ReferralStatus.PAID).aggregate(t=Sum("commission_amount"))
        return result["t"] or 0


class ReferralPayoutSerializer(serializers.ModelSerializer):
    referrer_name = serializers.CharField(source="referrer.name", read_only=True)
    referrer_code = serializers.CharField(source="referrer.code", read_only=True)
    lead_name     = serializers.CharField(source="lead.full_name", read_only=True, default=None)
    lead_email    = serializers.CharField(source="lead.email", read_only=True, default=None)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    property_title = serializers.CharField(
        source="rental_application.rental_property.title", read_only=True, default=None
    )

    class Meta:
        model = ReferralPayout
        fields = [
            "id", "referrer", "referrer_name", "referrer_code",
            "lead", "lead_name", "lead_email",
            "rental_application", "property_title",
            "status", "status_display",
            "monthly_rent", "commission_rate", "commission_months", "commission_amount",
            "notes", "created_at", "converted_at", "paid_at",
        ]
        read_only_fields = ["id", "created_at", "commission_amount"]
