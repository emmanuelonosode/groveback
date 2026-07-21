from rest_framework import serializers
from .models import CustomUser, AgentProfile, Role


class AgentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentProfile
        fields = [
            "bio", "license_number", "specialties", "languages",
            "social_links", "commission_rate", "total_sales", "years_experience",
        ]


class UserSerializer(serializers.ModelSerializer):
    agent_profile = AgentProfileSerializer(read_only=True)
    full_name = serializers.CharField(read_only=True)
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            "id", "email", "first_name", "last_name", "full_name",
            "phone", "role", "avatar_url", "is_active", "date_joined", "agent_profile",
        ]
        read_only_fields = ["id", "date_joined"]

    def get_avatar_url(self, obj):
        return obj.avatar_url


class PublicAgentSerializer(serializers.ModelSerializer):
    """Minimal agent data for public-facing endpoints."""
    agent_profile = AgentProfileSerializer(read_only=True)
    full_name = serializers.CharField(read_only=True)
    active_listings = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            "id", "first_name", "last_name", "full_name",
            "phone", "email", "avatar_url", "agent_profile", "active_listings",
        ]

    def get_active_listings(self, obj):
        return obj.listings.filter(is_published=True, status="available").count()

    def get_avatar_url(self, obj):
        # Prefer the agent profile photo; fall back to the user account avatar.
        url = None
        try:
            if hasattr(obj, "agent_profile") and obj.agent_profile and obj.agent_profile.avatar:
                url = obj.agent_profile.avatar.url
        except Exception:
            url = None
        if not url:
            url = obj.avatar_url
        # Locally-stored media returns a relative "/media/..." path; make it absolute
        # so the separate frontend domain can load it (absolute URLs pass through).
        request = self.context.get("request")
        if url and url.startswith("/") and request is not None:
            return request.build_absolute_uri(url)
        return url


class MeSerializer(serializers.ModelSerializer):
    agent_profile = AgentProfileSerializer(read_only=True)
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            "id", "email", "first_name", "last_name", "phone",
            "role", "avatar_url", "agent_profile",
            "onboarding_completed", "preferences"
        ]
        read_only_fields = ["id", "email", "role"]

    def get_avatar_url(self, obj):
        return obj.avatar_url


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = CustomUser
        fields = ["email", "first_name", "last_name", "phone", "password"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = CustomUser(**validated_data, role=Role.CLIENT)
        user.set_password(password)
        user.save()
        return user


class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6)


class ResendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password     = serializers.CharField(write_only=True, min_length=8)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value
