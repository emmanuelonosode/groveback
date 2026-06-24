from django.urls import path
from . import views

urlpatterns = [
    path("calendar/", views.viewing_calendar, name="viewing-calendar"),
    # Public tour requests (lead-first + ID verification)
    path("tour-requests/", views.TourRequestCreateView.as_view(), name="tour-request-create"),
    path("tour-requests/<uuid:public_id>/verify-id/", views.upload_tour_id, name="tour-request-verify-id"),
    path("", views.ViewingListCreateView.as_view(), name="viewing-list-create"),
    path("<int:pk>/", views.ViewingDetailView.as_view(), name="viewing-detail"),
]
