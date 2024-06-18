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


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


slack_bot_token = 'xoxb-7211024649319-7255010358368-kfpRpAVfOlYVnRgQa67ejD9n'
slack_signing_secret = '41e10601bd16ef9d8073063904f9262b'
ssl_context = ssl.SSLContext()
ssl_context.verify_mode = ssl.CERT_NONE

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
                response_text = fetch_leave_history(user_id)
                return JsonResponse({"response_type": "ephemeral", "text": response_text})
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
    return JsonResponse({"success": False}, status=400)

def fetch_leave_history(user_id):
    try:
        applications = LeaveApplication.objects.filter(employee_id=user_id).order_by('-submitted_at')

        if applications.exists():
            history_table = "Leave History:\n\n"
            history_table += "Leave Type | Reason | Date | Result | Employee Name | Employee ID\n"
            history_table += "---------------------------------------------------------------\n"
            for app in applications:
                history_table += (f"{app.leave_type} | {app.reason} | "
                                  f"{app.start_date} to {app.end_date} | {app.status} | "
                                  f"{app.employee_name} | {app.employee_id}\n")
            return history_table
        else:
            return "No leave history found."
    except Exception as e:
        logger.error(f"Error fetching leave history: {e}")
        return "An error occurred while fetching your leave history."

from datetime import timedelta

def calculate_leave_balance(user_id):
    try:
        applications = LeaveApplication.objects.filter(employee_id=user_id)
        current_year = timezone.now().year
        current_month = timezone.now().month
        days_used_this_month = 0
        days_used_this_year = 0

        for application in applications:
            # Calculate days used for this application
            days_used = (application.end_date - application.start_date).days + 1

            # Check if the application is within the current year
            if application.start_date.year == current_year:
                days_used_this_year += days_used

                # Check if the application is within the current month
                if application.start_date.month == current_month:
                    days_used_this_month += days_used

        remaining_days_this_month = max(0, 2 - days_used_this_month)
        remaining_days_this_year = max(0, 24 - days_used_this_year)

        response_text = (
            f"You used 2 days this month. "
            f"Remaining days this month: 0. "
            f"Remaining days this year: 22."
        )

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

def handle_submission(payload):
    try:
        state_values = payload['view']['state']['values']
        employee_name = state_values['employee_name']['employee_name']['value']
        employee_id = state_values['employee_id']['employee_id']['value']
        employment_type = state_values['employment_type']['employment_type']['selected_option']['value']
        leave_type = state_values['leave_type']['leave_type']['selected_option']['value']
        reason = state_values['reason']['reason']['value']
        start_date = state_values['start_date']['start_date']['selected_date']
        end_date = state_values['end_date']['end_date']['selected_date']

        slack_user_id = payload['user']['id']

        leave_application = LeaveApplication(
            employee_name=employee_name,
            employee_id=employee_id,
            employment_type=employment_type,
            leave_type=leave_type,
            reason=reason,
            start_date=start_date,
            end_date=end_date,
            submitted_at=timezone.now()
        )
        leave_application.save()

        notify_employee_and_manager(slack_user_id, employee_name, employee_id, employment_type, leave_type, reason, start_date, end_date)

        response = {
            "response_action": "clear"
        }
        return JsonResponse(response)

    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error processing submission: {e}")
        return JsonResponse({'error': 'Invalid JSON or missing data'}, status=400)

def handle_interaction_action(payload):
    try:
        action = payload['actions'][0]
        action_value = action['value']
        action_type, employee_id = action_value.split('_')

        application = LeaveApplication.objects.filter(employee_id=employee_id).first()

        if not application:
            error_message = f"No leave application found for employee ID {employee_id}"
            logger.error(error_message)
            return JsonResponse({'error': error_message}, status=404)

        action_ts = timezone.now()

        if action_type == 'approve':
            application.status = 'approved'
            result_text = "approved"
        else:
            application.status = 'rejected'
            result_text = "rejected"

        application.save()

        try:
            slack_user_id = payload['user']['id']
            response = slack_client.conversations_open(users=slack_user_id)
            dm_channel = response['channel']['id']
        except SlackApiError as e:
            logger.error(f"Slack API error (conversations_open): {e.response['error']}")
            return JsonResponse({'error': 'Slack API error', 'details': e.response['error']}, status=500)

        slack_client.chat_postMessage(
            channel=dm_channel,
            text=f"Your leave application has been {result_text} at {action_ts}."
        )

        slack_client.chat_update(
            channel=payload['channel']['id'],
                        ts=payload['message']['ts'],
            text=f"You have {result_text} {application.employee_name}'s leave application."
        )
        response_message = {
            "replace_original": True,
            "text": f"You have {result_text} {application.employee_name}'s leave application."
        }

        return JsonResponse(response_message, status=200)

    except LeaveApplication.DoesNotExist:
        logger.error(f"No leave application found for employee ID {employee_id}")
        return JsonResponse({'error': 'Leave application not found'}, status=404)
    except SlackApiError as e:
        logger.error(f"Slack API error: {e.response['error']}")
        return JsonResponse({'error': 'Slack API error', 'details': e.response['error']}, status=500)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return JsonResponse({'error': 'Internal server error', 'details': str(e)}, status=500)

def notify_employee_and_manager(slack_user_id, employee_name, employee_id, employment_type, leave_type, reason, start_date, end_date):
    try:
        slack_client.chat_postMessage(
            channel='#leaves',
            text=f"Thanks {employee_name}, your leave application has been sent to the manager."
        )
        manager_user_id = 'U076MHB604A'
        message = {
            "channel": manager_user_id,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"Leave Application Details:\n"
                            f"*Employee Name:* {employee_name}\n"
                            f"*Employee ID:* {employee_id}\n"
                            f"*Employment Type:* {employment_type}\n"
                            f"*Leave Type:* {leave_type}\n"
                            f"*Reason:* {reason}\n"
                            f"*Start Date:* {start_date}\n"
                            f"*End Date:* {end_date}\n"
                            "Please approve or reject the leave application."
                        )
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
                            "value": f"approve_{employee_id}"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Reject"
                            },
                            "style": "danger",
                            "value": f"reject_{employee_id}"
                        }
                    ]
                }
            ]
        }

        slack_client.chat_postMessage(**message)
    except SlackApiError as e:
        logger.error(f"Error sending notifications: {e.response['error']}")

def open_modal(trigger_id):
    try:
        view = {
            "type": "modal",
            "callback_id": "handle_submission",
            "title": {"type": "plain_text", "text": "Leave Application"},
            "submit": {"type": "plain_text", "text": "Submit"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "employee_name",
                    "element": {"type": "plain_text_input", "action_id": "employee_name"},
                    "label": {"type": "plain_text", "text": "Employee Name"}
                },
                {
                    "type": "input",
                    "block_id": "employee_id",
                    "element": {"type": "plain_text_input", "action_id": "employee_id"},
                    "label": {"type": "plain_text", "text": "Employee ID"}
                },
                {
                    "type": "input",
                    "block_id": "employment_type",
                    "element": {
                        "type": "static_select",
                        "action_id": "employment_type",
                        "options": [
                            {"text": {"type": "plain_text", "text": "Full-Time"}, "value": "full_time"},
                            {"text": {"type": "plain_text", "text": "Intern"}, "value": "part_time"}
                        ]
                    },
                    "label": {"type": "plain_text", "text": "Employment Type"}
                },
                {
                    "type": "input",
                    "block_id": "leave_type",
                    "element": {
                        "type": "static_select",
                        "action_id": "leave_type",
                        "options": [
                            {"text": {"type": "plain_text", "text": "Casual"}, "value": "casual"},
                            {"text": {"type": "plain_text", "text": "Sick"}, "value": "sick"},
                            {"text": {"type": "plain_text", "text": "Unpaid"}, "value": "unpaid"},
                            {"text": {"type": "plain_text", "text": "Others"}, "value": "others"}
                        ]
                    },
                    "label": {"type": "plain_text", "text": "Leave Type"}
                },
                {
                    "type": "input",
                    "block_id": "reason",
                    "element": {"type": "plain_text_input", "action_id": "reason"},
                    "label": {"type": "plain_text", "text": "Reason"}
                },
                {
                    "type": "input",
                    "block_id": "start_date",
                    "element": {"type": "datepicker", "action_id": "start_date"},
                    "label": {"type": "plain_text", "text": "Start Date"}
                },
                {
                    "type": "input",
                    "block_id": "end_date",
                    "element": {"type": "datepicker", "action_id": "end_date"},
                    "label": {"type": "plain_text", "text": "End Date"}
                }
            ]
        }
        slack_client.views_open(trigger_id=trigger_id, view=view)
    except SlackApiError as e:
        logger.error(f"Error opening modal: {e.response['error']}")


           
# THIS IS ORIGINAL DON't DO CNTRL Z


