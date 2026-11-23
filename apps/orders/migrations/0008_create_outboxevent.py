from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0007_orderitem_course'),
        ('courses', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='OutboxEvent',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False, auto_created=True, verbose_name='ID')),
                ('event_type', models.CharField(max_length=30, choices=[
                    ('PDF_RECEIPT', 'PDF Receipt'),
                    ('COURSE_ENROLLMENT', 'Course Enrollment'),
                    ('PAYMENT_EMAIL', 'Payment Email'),
                ])),
                ('course', models.ForeignKey(null=True, blank=True, on_delete=models.SET_NULL, to='courses.course')),
                ('payload', models.JSONField(default=dict, blank=True)),
                ('idempotency_key', models.CharField(max_length=255)),
                ('status', models.CharField(max_length=15, choices=[
                    ('PENDING', 'Pending'),
                    ('PROCESSING', 'Processing'),
                    ('SUCCESS', 'Success'),
                    ('FAILED', 'Failed'),
                ], default='PENDING')),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('available_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('processing_at', models.DateTimeField(null=True, blank=True)),
                ('locked_until', models.DateTimeField(null=True, blank=True)),
                ('last_error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('processed_at', models.DateTimeField(null=True, blank=True)),
                ('order', models.ForeignKey(on_delete=models.CASCADE, related_name='outbox_events', to='orders.order')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['status', 'available_at'], name='idx_outbox_status_available'),
                    models.Index(fields=['locked_until'], name='idx_outbox_locked_until'),
                ],
                'constraints': [
                    models.UniqueConstraint(fields=['idempotency_key'], name='uniq_outbox_idempotency_key'),
                ],
            },
        ),
    ]
