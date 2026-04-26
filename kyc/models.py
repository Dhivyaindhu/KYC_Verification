import os
from django.db import models
from django.utils import timezone
from django.conf import settings
from users.models import User


class KYCSubmission(models.Model):
    """Core KYC submission with strict state machine enforcement."""

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SUBMITTED = 'submitted', 'Submitted'
        UNDER_REVIEW = 'under_review', 'Under Review'
        MORE_INFO_REQUESTED = 'more_info_requested', 'More Info Requested'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    # Valid state transitions map
    VALID_TRANSITIONS = {
        Status.DRAFT: [Status.SUBMITTED],
        Status.SUBMITTED: [Status.UNDER_REVIEW],
        Status.UNDER_REVIEW: [Status.APPROVED, Status.REJECTED, Status.MORE_INFO_REQUESTED],
        Status.MORE_INFO_REQUESTED: [Status.SUBMITTED],
        Status.APPROVED: [],   # Terminal state
        Status.REJECTED: [],   # Terminal state
    }

    merchant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='kyc_submissions')
    reviewer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_submissions'
    )

    # Personal Info
    full_name = models.CharField(max_length=255, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    pan_number = models.CharField(max_length=10, blank=True)
    aadhaar_number = models.CharField(max_length=12, blank=True)

    # Business Info
    business_name = models.CharField(max_length=255, blank=True)
    business_type = models.CharField(max_length=100, blank=True)
    gst_number = models.CharField(max_length=15, blank=True)
    business_address = models.TextField(blank=True)

    # Bank Info
    bank_account_number = models.CharField(max_length=20, blank=True)
    bank_ifsc_code = models.CharField(max_length=11, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)

    # Status tracking
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.DRAFT)
    rejection_reason = models.TextField(blank=True)
    more_info_notes = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"KYC#{self.id} - {self.merchant.email} [{self.status}]"

    def can_transition_to(self, new_status):
        """Check if transition from current status to new_status is valid."""
        allowed = self.VALID_TRANSITIONS.get(self.status, [])
        return new_status in allowed

    def transition_to(self, new_status, reviewer=None, reason='', notes=''):
        """
        Central state machine method. Enforces all valid transitions.
        Raises ValueError for invalid transitions.
        """
        if not self.can_transition_to(new_status):
            raise ValueError(
                f"Invalid transition: '{self.status}' → '{new_status}'. "
                f"Allowed: {self.VALID_TRANSITIONS.get(self.status, [])}"
            )

        old_status = self.status
        self.status = new_status

        if new_status == self.Status.SUBMITTED:
            self.submitted_at = timezone.now()
        elif new_status == self.Status.UNDER_REVIEW:
            self.reviewer = reviewer
        elif new_status in [self.Status.APPROVED, self.Status.REJECTED, self.Status.MORE_INFO_REQUESTED]:
            self.reviewed_at = timezone.now()

        if new_status == self.Status.REJECTED:
            self.rejection_reason = reason
        if new_status == self.Status.MORE_INFO_REQUESTED:
            self.more_info_notes = notes

        self.save()
        return old_status

    @property
    def is_at_risk(self):
        """Flag submissions under review longer than SLA threshold."""
        if self.status != self.Status.UNDER_REVIEW:
            return False
        sla_hours = getattr(settings, 'KYC_SLA_HOURS', 24)
        return (timezone.now() - self.submitted_at).total_seconds() > sla_hours * 3600

    @property
    def hours_in_review(self):
        """Hours since submission."""
        if not self.submitted_at:
            return 0
        return round((timezone.now() - self.submitted_at).total_seconds() / 3600, 1)


def document_upload_path(instance, filename):
    """Organize uploads by merchant/submission."""
    ext = os.path.splitext(filename)[1].lower()
    return f"kyc/{instance.submission.merchant.id}/{instance.submission.id}/{instance.doc_type}{ext}"


class KYCDocument(models.Model):
    """Uploaded documents for a KYC submission."""

    class DocType(models.TextChoices):
        PAN = 'pan', 'PAN Card'
        AADHAAR = 'aadhaar', 'Aadhaar Card'
        BANK_STATEMENT = 'bank_statement', 'Bank Statement'
        BUSINESS_PROOF = 'business_proof', 'Business Proof'

    submission = models.ForeignKey(KYCSubmission, on_delete=models.CASCADE, related_name='documents')
    doc_type = models.CharField(max_length=30, choices=DocType.choices)
    file = models.FileField(upload_to=document_upload_path)
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField()  # bytes
    mime_type = models.CharField(max_length=100)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['submission', 'doc_type']  # One doc per type per submission

    def __str__(self):
        return f"{self.doc_type} for KYC#{self.submission.id}"

    @property
    def file_size_mb(self):
        return round(self.file_size / (1024 * 1024), 2)
