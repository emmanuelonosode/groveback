from django.urls import path
from . import views

urlpatterns = [
    path("posts/",              views.PostListView.as_view(),   name="blog-post-list"),
    path("sitemap/",            views.blog_sitemap,             name="blog-sitemap"),
    path("posts/<slug:slug>/",  views.PostDetailView.as_view(), name="blog-post-detail"),
]
