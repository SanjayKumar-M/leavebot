import json
import logging
import ssl
import urllib.parse
from datetime import datetime
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.signature import SignatureVerifier
from .models import LeaveApplication
import prettytable
from prettytable import PrettyTable
import io
import base64
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load Slack credentials from environment variables
slack_bot_token = ''  # Replace with os.getenv('SLACK_BOT_TOKEN')
slack_signing_secret = ''  # Replace with os.getenv('SLACK_SIGNING_SECRET')

# SSL context for Slack client
ssl_context = ssl.SSLContext()
ssl_context.verify_mode = ssl.CERT_NONE

# Initialize Slack client and verifier
slack_client = WebClient(token=slack_bot_token, ssl=ssl_context)
verifier = SignatureVerifier(signing_secret=slack_signing_secret)

@csrf_exempt
def slack_events(request):
    if request.method == 'POST':
        try:
            headers = dict(request.headers.items())
            data = json.loads(request.body.decode('utf-8'))

            if data.get('type') == 'url_verification':
                return JsonResponse({'challenge': data.get('challenge')})

            if not verifier.is_valid_request(request.body, headers):
                logger.error("Invalid Slack request")
                return JsonResponse({"success": False, "message": "Invalid request"}, status=403)

            logger.info("Received event: %s", json.dumps(data, indent=2))

            if data.get('event', {}).get('type') == 'app_mention':
                event_data = data['event']
                logger.info("App mention event data: %s", json.dumps(event_data, indent=2))
                if 'text' in event_data and 'apply leave' in event_data['text'].lower():
                    trigger_id = event_data.get('trigger_id')
                    if trigger_id:
                        open_modal(trigger_id)
                    else:
                        channel_id = event_data.get('channel')
                        user_id = event_data.get('user')
                        slack_client.chat_postMessage(
                            channel=channel_id,
                            text=f"<@{user_id}> To apply for leave, use the /apply_leave slash command."
                        )
                return JsonResponse({"success": True})

            return JsonResponse({"success": True})
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

@csrf_exempt
def slack_slash_command(request):
    if request.method == 'POST':
        try:
            data = request.POST
            logger.info("Slash command received: %s", json.dumps(data, indent=2))

            if data.get('command') == '/apply_leave':
                trigger_id = data.get('trigger_id')
                if trigger_id:
                    open_modal(trigger_id)
                    return JsonResponse({"response_type": "ephemeral", "text": "Opening leave application modal..."})
                else:
                    logger.error("Trigger ID not found in slash command data")
                    return JsonResponse({"response_type": "ephemeral", "text": "Error opening modal"}, status=400)
            elif data.get('command') == '/leave_balance':
                user_id = data.get('user_id')
                response_text = calculate_leave_balance(user_id)
                return JsonResponse({"response_type": "ephemeral", "text": response_text})
            elif data.get('command') == '/history':
                user_id = data.get('user_id')
                text = data.get('text', '').strip()
                if text == 'download':
                    send_leave_history(user_id, download=True)
                    return JsonResponse({"response_type": "ephemeral", "text": "Leave history image sent to your DM"})
                else:
                    send_leave_history(user_id)
                    return JsonResponse({"response_type": "ephemeral", "text": "Leave history sent to your DM"})
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
    return JsonResponse({"success": False}, status=400)

def send_leave_history(slack_user_id):
    try:
        applications = LeaveApplication.objects.filter(slack_user_id=slack_user_id).order_by('-submitted_at')
        if applications.exists():
            data = []
            for app in applications:
                data.append([
                    app.leave_type,
                    app.reason,
                    f"{app.start_date} to {app.end_date}",
                    app.status
                ])

            table = PrettyTable()
            table.field_names = ["TYPE", "REASON", "DATE", "STATUS"]
            for row in data:
                table.add_row(row)

            table_string = f"```\n{table}\n```"
            slack_client.chat_postMessage(
                channel=slack_user_id,
                text=f"Here is your leave history:\n{table_string}"
            )
        else:
            slack_client.chat_postMessage(
                channel=slack_user_id,
                text="No leave history found."
            )
    except Exception as e:
        logger.error(f"Error fetching leave history: {e}")

def calculate_leave_balance(user_id):
    try:
        current_year = timezone.now().year
        current_month = timezone.now().month
        days_used_this_month = 0
        days_used_this_year = 0

        applications = LeaveApplication.objects.filter(slack_user_id=user_id, status='approved')

        for application in applications:
            days_used = (application.end_date - application.start_date).days + 1

            logger.info(f"Application {application.id}: {application.start_date} to {application.end_date} ({days_used} days)")

            if application.start_date.year == current_year:
                days_used_this_year += days_used

                if application.start_date.month == current_month:
                    days_used_this_month += days_used

        remaining_days_this_month = max(0, 2 - days_used_this_month)
        remaining_days_this_year = max(0, 24 - days_used_this_year)

        response_text = (
            f"You have used {days_used_this_month} days this month. "
            f"Remaining days this month: {remaining_days_this_month}. "
            f"Remaining days this year: {remaining_days_this_year}."
        )

        logger.info(f"Leave balance response: {response_text}")

        return response_text

    except Exception as e:
        logger.error(f"Error calculating leave balance: {e}")
        return "An error occurred while calculating your leave balance."

@csrf_exempt
def handle_interactions(request):
    if request.method == 'POST':
        try:
            request_data = request.body.decode('utf-8')
            payload = urllib.parse.parse_qs(request_data).get('payload', [None])[0]

            if not payload:
                return JsonResponse({'error': 'Invalid payload'}, status=400)

            payload = json.loads(payload)
            logger.info("Interaction received: %s", json.dumps(payload, indent=2))

            if payload.get('type') == 'view_submission':
                return handle_submission(payload)
            elif payload.get('type') == 'block_actions':
                return handle_interaction_action(payload)
            else:
                return JsonResponse({'error': 'Unknown interaction type'}, status=400)

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
    return JsonResponse({"success": False}, status=400)

def handle_interaction_action(payload):
    actions = payload['actions']
    action = actions[0]
    action_id = action['action_id']
    leave_application_id = int(action['value'])
    response_url = payload['response_url']

    try:
        leave_application = LeaveApplication.objects.get(id=leave_application_id)
        if action_id == 'approve_leave':
            leave_application.status = 'approved'
            status_message = f"You approved {leave_application.employee_name}'s application."
        elif action_id == 'reject_leave':
            leave_application.status = 'rejected'
            status_message = f"You rejected {leave_application.employee_name}'s application."

        leave_application.save()

        slack_client.chat_postMessage(
            channel=leave_application.slack_user_id,
            text=f"Your leave application from {leave_application.start_date} to {leave_application.end_date} has been {leave_application.status}."
        )

        # Update the original message with the status
        slack_client.chat_update(
            channel=payload['channel']['id'],
            ts=payload['message']['ts'],
            text=status_message,
            blocks=[]
        )

        return JsonResponse({"status": "ok"})
    except LeaveApplication.DoesNotExist:
        logger.error(f"Leave application with ID {leave_application_id} does not exist")
        return JsonResponse({"status": "error", "message": "Leave application not found"}, status=404)
    except Exception as e:
        logger.error(f"Error handling leave application action: {e}")
        return JsonResponse({"status": "error", "message": "An error occurred"}, status=500)

def handle_submission(payload):
    user_id = payload['user']['id']
    submission = payload['view']['state']['values']
    reason = submission['reason_block']['reason']['value']
    leave_type = submission['leave_type_block']['leave_type']['selected_option']['value']
    start_date = submission['start_date_block']['start_date']['selected_date']
    end_date = submission['end_date_block']['end_date']['selected_date']

    try:
        user_info = get_slack_user_info(user_id)
        real_name = user_info.get('real_name', 'Unknown User')
        email = user_info.get('profile', {}).get('email', 'unknown@example.com')

        # Check if the user has reached the leave limit for the month
        if not can_apply_leave(user_id, leave_type, start_date, end_date):
            return JsonResponse({"response_action": "errors", "errors": {"reason_block": "You have reached the leave limit for this month."}})

        leave_application = LeaveApplication(
            slack_user_id=user_id,
            employee_name=real_name,
            employee_email=email,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            status='pending',
            submitted_at=datetime.now()
        )
        leave_application.save()

        manager_id = 'U076MHB604A'  # replace with the actual manager's Slack ID
        slack_client.chat_postMessage(
            channel=manager_id,
            text=f"New leave application submitted by {real_name}:\n"
                 f"Type: {leave_type}\n"
                 f"Reason: {reason}\n"
                 f"From: {start_date} To: {end_date}",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*New leave application submitted by {real_name}:*\n"
                                f"*Type:* {leave_type}\n"
                                f"*Reason:* {reason}\n"
                                f"*From:* {start_date} To: {end_date}"
                    }
                },
                {
                    "type": "actions",
                    "block_id": f"leave_{leave_application.id}",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Approve"
                            },
                            "style": "primary",
                            "action_id": "approve_leave",
                            "value": str(leave_application.id)
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Reject"
                            },
                            "style": "danger",
                            "action_id": "reject_leave",
                            "value": str(leave_application.id)
                        }
                    ]
                }
            ]
        )

        slack_client.chat_postMessage(
            channel=user_id,
            text=f"Your leave application has been submitted:\n\n"
                 f"Type: {leave_type}\n"
                 f"Reason: {reason}\n"
                 f"From: {start_date} To: {end_date}\n\n"
                 f"You will be notified once it is reviewed."
        )

        return JsonResponse({"response_action": "clear"})
    except Exception as e:
        logger.error(f"Error saving leave application: {e}")
        return JsonResponse({"response_action": "errors", "errors": {"reason_block": "Failed to save application. Please try again."}})

def can_apply_leave(user_id, leave_type, start_date, end_date):
    current_year = timezone.now().year
    current_month = timezone.now().month

    # Define leave limits
    monthly_limit = 2

    # Calculate days used for the given leave type in the current month
    applications = LeaveApplication.objects.filter(
        slack_user_id=user_id,
        status='approved',
        leave_type=leave_type,
        start_date__year=current_year,
        start_date__month=current_month
    )

    days_used_this_month = sum((app.end_date - app.start_date).days + 1 for app in applications)

    # Calculate the number of days for the new leave application
    new_leave_days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days + 1

    if leave_type in ['sick', 'casual']:
        if days_used_this_month + new_leave_days > monthly_limit:
            slack_client.chat_postMessage(
                channel=user_id,
                text=f"You have reached the limit of {monthly_limit} {leave_type} leave days for this month."
            )
            return False
    return True

def open_modal(trigger_id):
    modal_view = {
        "type": "modal",
        "callback_id": "leave_application",
        "title": {"type": "plain_text", "text": "Leave Application"},
        "submit": {"type": "plain_text", "text": "Submit"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "leave_type_block",
                "label": {"type": "plain_text", "text": "Leave Type"},
                "element": {
                    "type": "static_select",
                    "action_id": "leave_type",
                    "placeholder": {"type": "plain_text", "text": "Select a leave type"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "Casual Leave"}, "value": "casual"},
                        {"text": {"type": "plain_text", "text": "Sick Leave"}, "value": "sick"},
                        {"text": {"type": "plain_text", "text": "Emergency Leave"}, "value": "emergency"}
                    ]
                }
            },
            {
                "type": "input",
                "block_id": "start_date_block",
                "label": {"type": "plain_text", "text": "Start Date"},
                "element": {"type": "datepicker", "action_id": "start_date"}
            },
            {
                "type": "input",
                "block_id": "end_date_block",
                "label": {"type": "plain_text", "text": "End Date"},
                "element": {"type": "datepicker", "action_id": "end_date"}
            },
            {
                "type": "input",
                "block_id": "reason_block",
                "label": {"type": "plain_text", "text": "Reason"},
                "element": {"type": "plain_text_input", "action_id": "reason", "multiline": True}
            }
        ]
    }
    try:
        slack_client.views_open(trigger_id=trigger_id, view=modal_view)
    except SlackApiError as e:
        logger.error(f"Slack API error (views_open): {e.response['error']}")

def get_slack_user_info(user_id):
    try:
        response = slack_client.users_info(user=user_id)
        return response['user']
    except SlackApiError as e:
        logger.error(f"Slack API error (users_info): {e.response['error']}")
        return {}
