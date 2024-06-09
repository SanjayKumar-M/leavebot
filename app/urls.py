from django.urls import path
from . import views

urlpatterns = [
    path('slack/events/', views.slack_events, name='slack_events'),
    path('slack/interactive/', views.slack_interactive, name='slack_interactive'),
]
