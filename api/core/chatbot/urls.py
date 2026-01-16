from django.urls import path
from .views import google_chat_handler

urlpatterns = [
    path('', google_chat_handler, name='google_chat_handler'),
]
