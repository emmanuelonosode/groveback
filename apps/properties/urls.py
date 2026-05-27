from django.urls import path
from . import views

urlpatterns = [
    path("", views.PropertyListCreateView.as_view(), name="property-list-create"),
    path("sitemap/", views.property_sitemap, name="property-sitemap"),
    path("featured/", views.FeaturedPropertiesView.as_view(), name="property-featured"),
    path("homepage/", views.HomepagePropertiesView.as_view(), name="property-homepage"),
    path("favorites/", views.FavoritePropertyListView.as_view(), name="property-favorites"),
    path("favorites/<int:property_id>/", views.FavoritePropertyDetailView.as_view(), name="property-favorites-detail"),
    path("map-pins/", views.MapPinsView.as_view(), name="property-map-pins"),
    path("cities/", views.city_stats, name="property-cities"),
    path("<slug:slug>/", views.PropertyDetailView.as_view(), name="property-detail"),
    path("<slug:slug>/inquiries/", views.property_inquiry, name="property-inquiry"),
]
