from django.db import models
from django.contrib.auth.models import User

class Role(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    is_manager = models.BooleanField(default=False)

class LeaveRequest(models.Model):
    employee = models.ForeignKey(User, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    leave_type = models.CharField(max_length=10, choices=[('Full', 'Full Day'), ('Half', 'Half Day')])
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=[('Pending', 'Pending'), ('Approved', 'Approved'), ('Rejected', 'Rejected')], default='Pending')
    manager = models.ForeignKey(User, related_name='leave_requests', on_delete=models.CASCADE, null=True, blank=True)
