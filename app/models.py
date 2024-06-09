from django.db import models

class LeaveApplication(models.Model):
    employee_name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    leave_type = models.CharField(max_length=10, choices=[('full', 'Full Day'), ('half', 'Half Day')])
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending')
    manager_id = models.CharField(max_length=100)
    employee_id = models.CharField(max_length=100)
