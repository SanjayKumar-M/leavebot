import json
import os
import re
from datetime import datetime
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
from django.conf import settings
from .models import LeaveApplication
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

slack_bot_token = 'xoxb-7211024649319-7255010358368-9IEQs3Ns2aRnvhdQtUSqLUPX'
slack_signing_secret = '41e10601bd16ef9d8073063904f9262b'

client = WebClient(token=slack_bot_token)
verifier = SignatureVerifier(signing_secret=slack_signing_secret)

@csrf_exempt
def slack_events(request):
    if request.method == 'POST':
        if not verifier.is_valid_request(request.body, request.headers):
            return JsonResponse({'error': 'invalid request'}, status=400)

        event_data = json.loads(request.body)
        logger.info(f"Event data received: {event_data}")

        if 'challenge' in event_data:
            return JsonResponse({'challenge': event_data['challenge']})

        if 'event' in event_data:
            event = event_data['event']
            if event.get('type') == 'app_mention':
                handle_app_mention(event)

        return JsonResponse({'status': 'ok'})

def handle_app_mention(event):
    text = event.get('text')
    user = event.get('user')
    leaves_channel_id = get_channel_id("leaves")

    if "apply leave" in text.lower():
        details = extract_leave_details(text)
        if details:
            leave_app = LeaveApplication.objects.create(
                employee_name=details['name'],
                start_date=details['start_date'],
                end_date=details['end_date'],
                leave_type=details['leave_type'],
                reason=details['reason'],
                employee_id=user
            )

            client.chat_postMessage(
                channel=leaves_channel_id,
                text=f"Leave application submitted by <@{user}> for {details['start_date']} to {details['end_date']}"
            )

            send_leave_request_to_manager(leave_app)
        else:
            client.chat_postMessage(
                channel=leaves_channel_id,
                text="Sorry, I couldn't understand your leave request. Please follow the format: `apply leave <name> <start_date> <end_date> <leave_type> <reason>`"
            )

def extract_leave_details(text):
    pattern = r"apply leave (?P<name>[\w\s]+) (?P<start_date>\d{4}-\d{2}-\d{2}) (?P<end_date>\d{4}-\d{2}-\d{2}) (?P<leave_type>\w+) (?P<reason>.*)"
    match = re.search(pattern, text, re.IGNORECASE)

    if match:
        start_date = datetime.strptime(match.group('start_date'), "%Y-%m-%d").date()
        end_date = datetime.strptime(match.group('end_date'), "%Y-%m-%d").date()
        leave_type = match.group('leave_type').lower()

        if leave_type not in ['full', 'half']:
            return None

        return {
            "name": match.group('name'),
            "start_date": start_date,
            "end_date": end_date,
            "leave_type": leave_type,
            "reason": match.group('reason')
        }

    return None

def send_leave_request_to_manager(leave_app):
    manager_channel_id = get_channel_id("leave_manager")
    if not manager_channel_id:
        logger.error("Manager channel not found. Cannot send leave request.")
        return

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Leave Application*\n*Employee:* {leave_app.employee_name}\n*From:* {leave_app.start_date}\n*To:* {leave_app.end_date}\n*Type:* {leave_app.leave_type}\n*Reason:* {leave_app.reason}"
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Approve"
                    },
                    "style": "primary",
                    "action_id": f"approve_{leave_app.id}"
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Reject"
                    },
                    "style": "danger",
                    "action_id": f"reject_{leave_app.id}"
                }
            ]
        }
    ]

    client.chat_postMessage(
        channel=manager_channel_id,
        text="A leave application has been submitted.",
        blocks=blocks
    )

@csrf_exempt
def slack_interactive(request):
    if request.method == 'POST':
        if not verifier.is_valid_request(request.body, request.headers):
            return JsonResponse({'error': 'invalid request'}, status=400)

        payload = json.loads(request.POST['payload'])
        logger.info(f"Interactive payload received: {payload}")

        action = payload['actions'][0]
        action_id = action['action_id']
        leave_app_id = action_id.split('_')[1]
        leave_app = LeaveApplication.objects.get(id=leave_app_id)
        user = payload['user']['id']

        if action_id.startswith('approve'):
            leave_app.status = 'approved'
            leave_app.save()
            response_text = f"Leave application for {leave_app.employee_name} has been approved."
            notify_employee(leave_app, response_text)
        elif action_id.startswith('reject'):
            leave_app.status = 'rejected'
            leave_app.save()
            response_text = f"Leave application for {leave_app.employee_name} has been rejected."
            notify_employee(leave_app, response_text)

        client.chat_postMessage(
            channel=user,
            text=response_text
        )

        return JsonResponse({'status': 'ok'})

def notify_employee(leave_app, response_text):
    leaves_channel_id = get_channel_id("leaves")
    if leaves_channel_id:
        client.chat_postMessage(
            channel=leaves_channel_id,
            text=response_text
        )
    else:
        logger.error("Leaves channel not found. Cannot notify employee.")

def get_channel_id(channel_name):
    try:
        result = client.conversations_list(types="public_channel,private_channel")
        channels = result["channels"]
        for channel in channels:
            if re.search(channel_name, channel["name"], re.IGNORECASE):
                return channel["id"]
    except Exception as e:
        logger.error(f"Error fetching channels: {e}")
    return None