# Generated by Django 5.0.3 on 2024-06-08 17:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0002_rename_user_leaverequest_employee_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='LeaveApplication',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('employee_name', models.CharField(max_length=100)),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('leave_type', models.CharField(choices=[('full', 'Full Day'), ('half', 'Half Day')], max_length=10)),
                ('reason', models.TextField()),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=10)),
                ('manager_id', models.CharField(max_length=100)),
                ('employee_id', models.CharField(max_length=100)),
            ],
        ),
        migrations.RemoveField(
            model_name='role',
            name='user',
        ),
        migrations.DeleteModel(
            name='LeaveRequest',
        ),
        migrations.DeleteModel(
            name='Role',
        ),
    ]
