from django.contrib import admin
from .models import LeaveRequest, Role

admin.site.register(LeaveRequest)
admin.site.register(Role)
