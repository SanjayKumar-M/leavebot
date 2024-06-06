import json
import logging
import os

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from django.conf import settings
client = WebClient(token=settings.SLACK_BOT_TOKEN)
logging.basicConfig(level=logging.DEBUG)

@csrf_exempt
@require_POST
def slack_events(request):
    payload = json.loads(request.body.decode('utf-8'))
    
    if 'challenge' in payload:
        return JsonResponse({'challenge': payload['challenge']})
    
    event = payload.get('event', {})
    
    if event.get('type') == 'app_mention' or event.get('type') == 'message':
        user = event.get('user')
        text = event.get('text')
        channel = event.get('channel')
        
        if text.startswith('/applyleave'):
            try:
                _, start_date, end_date, day_type, reason = text.split(maxsplit=4)
                manager_channel = 'T07670QK39D/C076XPCHEBV'
                
                client.chat_postMessage(
                    channel=manager_channel,
                    text=f"Leave request from <@{user}>:\n"
                         f"Start Date: {start_date}\n"
                         f"End Date: {end_date}\n"
                         f"Day Type: {day_type}\n"
                         f"Reason: {reason}\n"
                         f"Please respond with `/approve <@{user}>` or `/reject <@{user}>`."
                )
                
                client.chat_postMessage(
                    channel=channel,
                    text="Your leave request has been submitted to the manager for approval."
                )
            except ValueError:
                client.chat_postMessage(
                    channel=channel,
                    text="Invalid format. Please use `/applyleave [start_date] [end_date] [half/full] [reason]`."
                )
    
    return JsonResponse({'status': 'ok'})

@csrf_exempt
@require_POST
def handle_leave_approval(request):
    payload = json.loads(request.body.decode('utf-8'))
    
    if 'challenge' in payload:
        return JsonResponse({'challenge': payload['challenge']})
    
    event = payload.get('event', {})
    
    if event.get('type') == 'app_mention' or event.get('type') == 'message':
        user = event.get('user')
        text = event.get('text')
        channel = event.get('channel')
        
        if text.startswith('/approve') or text.startswith('/reject'):
            command, target_user = text.split(maxsplit=1)
            target_user_id = target_user.strip('<@>')
            
            if command == '/approve':
                response_text = f"Your leave request has been approved by <@{user}>."
            else:
                response_text = f"Your leave request has been rejected by <@{user}>."
            
            client.chat_postMessage(
                channel=target_user_id,
                text=response_text
            )
            
            client.chat_postMessage(
                channel=channel,
                text="Your response has been recorded."
            )
    
    return JsonResponse({'status': 'ok'})
