from django.db import models
from django.utils import timezone

class LeaveApplication(models.Model):
    slack_user_id = models.CharField(max_length=100, default='')  # Add default value
    employee_name = models.CharField(max_length=100, default='')  # Add default value
    employee_email = models.EmailField(default='unknown@example.com')  # Add default value

    employment_type = models.CharField(
        max_length=20,
        choices=[('full_time', 'Full Time'), ('intern', 'Intern')],
        default='full_time'
    )
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(default=timezone.now)
    leave_type = models.CharField(
        max_length=10,
        choices=[('full', 'Full Day'), ('half', 'Half Day')],
        default='full'
    )
    reason = models.TextField(default='')
    status = models.CharField(
        max_length=10,
        choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')],
        default='pending'
    )
    manager_id = models.CharField(max_length=100, default='')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.employee_name} - {self.start_date} to {self.end_date}"
