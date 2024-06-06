from django.urls import path
from .views import slack_events, handle_leave_approval

urlpatterns = [
    path('slack/events/', slack_events, name='slack_events'),
    path('slack/approve/', handle_leave_approval, name='handle_leave_approval'),
]
