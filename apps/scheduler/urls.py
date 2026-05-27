from django.urls import path
from . import views

urlpatterns = [
    path("calendar/", views.viewing_calendar, name="viewing-calendar"),
    path("", views.ViewingListCreateView.as_view(), name="viewing-list-create"),
    path("<int:pk>/", views.ViewingDetailView.as_view(), name="viewing-detail"),
]
