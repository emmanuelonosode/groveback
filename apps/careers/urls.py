from django.urls import path
from . import views

urlpatterns = [
    path("apply/", views.JobApplicationCreateView.as_view(), name="job-application-create"),
    path("applications/", views.JobApplicationListView.as_view(), name="job-application-list"),
    path("applications/<int:pk>/", views.JobApplicationDetailView.as_view(), name="job-application-detail"),
]
