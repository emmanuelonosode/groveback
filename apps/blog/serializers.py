from rest_framework import serializers
from .models import Post


class PostListSerializer(serializers.ModelSerializer):
    author_name        = serializers.CharField(source="author.get_full_name", read_only=True)
    author_avatar_url  = serializers.SerializerMethodField()
    author_role        = serializers.SerializerMethodField()
    featured_image_url = serializers.SerializerMethodField()
    category_display   = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = Post
        fields = [
            "id", "slug", "title", "excerpt",
            "category", "category_display",
            "featured_image_url",
            "author_name", "author_avatar_url", "author_role",
            "is_featured", "is_published", "published_at",
            "tags", "read_time_minutes",
        ]

    def get_featured_image_url(self, obj):
        if obj.featured_image:
            return obj.featured_image.url
        return None

    def get_author_avatar_url(self, obj):
        try:
            if obj.author.avatar:
                return obj.author.avatar.url
        except Exception:
            pass
        return None

    def get_author_role(self, obj):
        try:
            profile = obj.author.agent_profile
            if profile.specialties:
                return profile.specialties[0]
        except Exception:
            pass
        return obj.author.get_role_display()


class PostDetailSerializer(PostListSerializer):
    class Meta(PostListSerializer.Meta):
        fields = PostListSerializer.Meta.fields + ["content", "created_at", "updated_at"]
