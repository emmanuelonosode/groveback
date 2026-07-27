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

    def _absolute(self, url):
        """
        Locally-stored media returns a relative "/media/..." path. The frontend runs on a
        different domain (primefamilyhousing.com) than this API (admin.primefamilyhousing.com),
        so a relative path resolves against the frontend host, where /media/ does not exist —
        every blog image would 404. Mirrors PublicAgentSerializer.get_avatar_url in
        apps/accounts/serializers.py. Absolute URLs (e.g. cloud storage) pass through.
        """
        request = self.context.get("request")
        if url and url.startswith("/") and request is not None:
            return request.build_absolute_uri(url)
        return url

    def get_featured_image_url(self, obj):
        if obj.featured_image:
            return self._absolute(obj.featured_image.url)
        return None

    def get_author_avatar_url(self, obj):
        try:
            if obj.author.avatar:
                return self._absolute(obj.author.avatar.url)
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
