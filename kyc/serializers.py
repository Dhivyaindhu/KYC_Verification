import os
import magic
from django.conf import settings
from rest_framework import serializers
from .models import KYCSubmission, KYCDocument
from users.serializers import UserSerializer


class KYCDocumentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = KYCDocument
        fields = ['id', 'doc_type', 'original_filename', 'file_size_mb', 'mime_type', 'uploaded_at', 'file_url']
        read_only_fields = ['id', 'uploaded_at', 'file_size_mb', 'mime_type', 'original_filename']

    def get_file_url(self, obj):
        request = self.context.get('request')
        if request and obj.file:
            return request.build_absolute_uri(obj.file.url)
        return None


class DocumentUploadSerializer(serializers.Serializer):
    """Validates file uploads: type, size, extension."""
    doc_type = serializers.ChoiceField(choices=KYCDocument.DocType.choices)
    file = serializers.FileField()

    def validate_file(self, file):
        allowed_extensions = getattr(settings, 'ALLOWED_DOCUMENT_EXTENSIONS', ['.pdf', '.jpg', '.jpeg', '.png'])
        max_size = getattr(settings, 'MAX_DOCUMENT_SIZE', 5 * 1024 * 1024)

        # Extension check
        ext = os.path.splitext(file.name)[1].lower()
        if ext not in allowed_extensions:
            raise serializers.ValidationError(
                f"Unsupported file type '{ext}'. Allowed: {', '.join(allowed_extensions)}"
            )

        # Size check
        if file.size > max_size:
            raise serializers.ValidationError(
                f"File size {round(file.size / 1024 / 1024, 2)}MB exceeds 5MB limit."
            )

        # MIME type check via python-magic
        try:
            file_content = file.read(2048)
            file.seek(0)
            mime = magic.from_buffer(file_content, mime=True)
            allowed_mimes = getattr(settings, 'ALLOWED_DOCUMENT_TYPES', ['application/pdf', 'image/jpeg', 'image/png'])
            if mime not in allowed_mimes:
                raise serializers.ValidationError(
                    f"Invalid MIME type '{mime}'. Allowed: PDF, JPEG, PNG."
                )
            file._detected_mime = mime
        except Exception as e:
            if 'Invalid MIME' in str(e):
                raise
            # If magic not available, fall back to extension-based check only
            ext_mime_map = {'.pdf': 'application/pdf', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png'}
            file._detected_mime = ext_mime_map.get(ext, 'application/octet-stream')

        return file


class KYCSubmissionListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    merchant_email = serializers.CharField(source='merchant.email', read_only=True)
    merchant_name = serializers.CharField(source='merchant.full_name', read_only=True)
    is_at_risk = serializers.BooleanField(read_only=True)
    hours_in_review = serializers.FloatField(read_only=True)
    document_count = serializers.SerializerMethodField()

    class Meta:
        model = KYCSubmission
        fields = [
            'id', 'merchant_email', 'merchant_name', 'status',
            'business_name', 'created_at', 'submitted_at',
            'is_at_risk', 'hours_in_review', 'document_count'
        ]

    def get_document_count(self, obj):
        return obj.documents.count()


class KYCSubmissionDetailSerializer(serializers.ModelSerializer):
    """Full serializer with nested documents."""
    merchant = UserSerializer(read_only=True)
    reviewer = UserSerializer(read_only=True)
    documents = KYCDocumentSerializer(many=True, read_only=True)
    is_at_risk = serializers.BooleanField(read_only=True)
    hours_in_review = serializers.FloatField(read_only=True)
    allowed_transitions = serializers.SerializerMethodField()

    class Meta:
        model = KYCSubmission
        fields = [
            'id', 'merchant', 'reviewer', 'status',
            'full_name', 'date_of_birth', 'pan_number', 'aadhaar_number',
            'business_name', 'business_type', 'gst_number', 'business_address',
            'bank_account_number', 'bank_ifsc_code', 'bank_name',
            'rejection_reason', 'more_info_notes',
            'created_at', 'updated_at', 'submitted_at', 'reviewed_at',
            'is_at_risk', 'hours_in_review', 'allowed_transitions', 'documents'
        ]
        read_only_fields = [
            'id', 'merchant', 'reviewer', 'status', 'created_at',
            'updated_at', 'submitted_at', 'reviewed_at',
            'is_at_risk', 'hours_in_review', 'allowed_transitions'
        ]

    def get_allowed_transitions(self, obj):
        return obj.VALID_TRANSITIONS.get(obj.status, [])


class KYCSubmissionWriteSerializer(serializers.ModelSerializer):
    """For creating/updating draft fields."""

    class Meta:
        model = KYCSubmission
        fields = [
            'full_name', 'date_of_birth', 'pan_number', 'aadhaar_number',
            'business_name', 'business_type', 'gst_number', 'business_address',
            'bank_account_number', 'bank_ifsc_code', 'bank_name',
        ]

    def validate_pan_number(self, value):
        if value and len(value) != 10:
            raise serializers.ValidationError("PAN must be 10 characters.")
        return value.upper()

    def validate_aadhaar_number(self, value):
        if value and (len(value) != 12 or not value.isdigit()):
            raise serializers.ValidationError("Aadhaar must be 12 digits.")
        return value

    def validate_bank_ifsc_code(self, value):
        if value and len(value) != 11:
            raise serializers.ValidationError("IFSC must be 11 characters.")
        return value.upper()


class ReviewActionSerializer(serializers.Serializer):
    """Reviewer takes action on a submission."""
    action = serializers.ChoiceField(choices=['approve', 'reject', 'request_info'])
    reason = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    def validate(self, data):
        action = data.get('action')
        if action == 'reject' and not data.get('reason'):
            raise serializers.ValidationError({'reason': 'Rejection reason is required.'})
        if action == 'request_info' and not data.get('notes'):
            raise serializers.ValidationError({'notes': 'Notes are required when requesting more info.'})
        return data
