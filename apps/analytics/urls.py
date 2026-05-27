from django.urls import path
from . import views

urlpatterns = [
    path("overview/", views.analytics_overview, name="analytics-overview"),
    path("pipeline/", views.analytics_pipeline, name="analytics-pipeline"),
    path("revenue/", views.analytics_revenue, name="analytics-revenue"),
]
