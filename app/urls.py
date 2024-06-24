from django.urls import path
from . import views

urlpatterns = [
    path('slack/events/', views.slack_events, name='slack_events'),
    path('slack/slash_command/', views.slack_slash_command, name='slack_slash_command'),
    path('slack/interactions/', views.handle_interactions, name='handle_interactions'),  
]
