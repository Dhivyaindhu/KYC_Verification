from django.db import models
from users.models import User


class NotificationEvent(models.Model):
    """
    Immutable audit log for every KYC state change.
    Acts as the event sourcing trail for the system.
    """

    class EventType(models.TextChoices):
        CREATED = 'created', 'Submission Created'
        SUBMITTED = 'submitted', 'Submitted for Review'
        PICKED_UP = 'picked_up', 'Picked Up for Review'
        APPROVED = 'approve', 'Approved'
        REJECTED = 'reject', 'Rejected'
        REQUEST_INFO = 'request_info', 'More Info Requested'
        DOCUMENT_UPLOADED = 'document_uploaded', 'Document Uploaded'
        COMMENT = 'comment', 'Comment Added'

    submission = models.ForeignKey(
        'kyc.KYCSubmission',
        on_delete=models.CASCADE,
        related_name='events'
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='kyc_events'
    )
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    old_status = models.CharField(max_length=30, blank=True)
    new_status = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.created_at:%Y-%m-%d %H:%M}] KYC#{self.submission_id} {self.event_type} by {self.actor}"
