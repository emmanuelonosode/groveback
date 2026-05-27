from django.urls import path
from . import views

urlpatterns = [
    path("", views.MaintenanceRequestListCreateView.as_view(), name="maintenance-list-create"),
    path("<int:pk>/", views.MaintenanceRequestDetailView.as_view(), name="maintenance-detail"),
]
