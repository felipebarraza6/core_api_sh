from django.urls import path
from .views import PresentationView

app_name = "presentation"

urlpatterns = [
    path("", PresentationView.as_view(), name="landing"),
]
