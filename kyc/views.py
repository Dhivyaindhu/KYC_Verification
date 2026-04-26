from django.db import transaction
from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser

from .models import KYCSubmission, KYCDocument
from .serializers import (
    KYCSubmissionListSerializer,
    KYCSubmissionDetailSerializer,
    KYCSubmissionWriteSerializer,
    DocumentUploadSerializer,
    ReviewActionSerializer,
)
from .permissions import IsMerchant, IsReviewer, IsMerchantOwnerOrReviewer
from notifications.models import NotificationEvent


def log_event(submission, actor, event_type, old_status=None, new_status=None, notes=''):
    """Helper to create audit trail entries."""
    NotificationEvent.objects.create(
        submission=submission,
        actor=actor,
        event_type=event_type,
        old_status=old_status or '',
        new_status=new_status or '',
        notes=notes
    )


# ─── Merchant Views ────────────────────────────────────────────────────────────

class MerchantSubmissionListCreateView(generics.ListCreateAPIView):
    """Merchant: list own submissions or create a new draft."""
    permission_classes = [IsAuthenticated, IsMerchant]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return KYCSubmissionWriteSerializer
        return KYCSubmissionListSerializer

    def get_queryset(self):
        return KYCSubmission.objects.filter(merchant=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        submission = serializer.save(merchant=self.request.user)
        log_event(submission, self.request.user, 'created', new_status='draft')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        # Return detail view
        instance = KYCSubmission.objects.filter(merchant=request.user).latest('created_at')
        return Response(
            KYCSubmissionDetailSerializer(instance, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )


class MerchantSubmissionDetailView(generics.RetrieveUpdateAPIView):
    """Merchant: view/update their draft submission."""
    permission_classes = [IsAuthenticated, IsMerchant, IsMerchantOwnerOrReviewer]
    serializer_class = KYCSubmissionDetailSerializer

    def get_queryset(self):
        return KYCSubmission.objects.filter(merchant=self.request.user)

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return KYCSubmissionWriteSerializer
        return KYCSubmissionDetailSerializer

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status not in [KYCSubmission.Status.DRAFT, KYCSubmission.Status.MORE_INFO_REQUESTED]:
            return Response(
                {'detail': 'Can only edit submissions in draft or more_info_requested state.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().update(request, *args, **kwargs)


class MerchantSubmitView(APIView):
    """Merchant: submit their draft for review."""
    permission_classes = [IsAuthenticated, IsMerchant]

    def post(self, request, pk):
        try:
            submission = KYCSubmission.objects.get(pk=pk, merchant=request.user)
        except KYCSubmission.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            with transaction.atomic():
                old_status = submission.transition_to(KYCSubmission.Status.SUBMITTED)
                log_event(submission, request.user, 'submitted', old_status=old_status, new_status='submitted')
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            KYCSubmissionDetailSerializer(submission, context={'request': request}).data
        )


class DocumentUploadView(APIView):
    """Merchant: upload a document for their submission."""
    permission_classes = [IsAuthenticated, IsMerchant]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        try:
            submission = KYCSubmission.objects.get(pk=pk, merchant=request.user)
        except KYCSubmission.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        if submission.status not in [KYCSubmission.Status.DRAFT, KYCSubmission.Status.MORE_INFO_REQUESTED]:
            return Response(
                {'detail': 'Documents can only be uploaded for draft or more_info_requested submissions.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = DocumentUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        file = serializer.validated_data['file']
        doc_type = serializer.validated_data['doc_type']
        mime = getattr(file, '_detected_mime', 'application/octet-stream')

        # Replace existing document of same type if any
        KYCDocument.objects.filter(submission=submission, doc_type=doc_type).delete()

        doc = KYCDocument.objects.create(
            submission=submission,
            doc_type=doc_type,
            file=file,
            original_filename=file.name,
            file_size=file.size,
            mime_type=mime,
        )

        log_event(submission, request.user, 'document_uploaded', notes=f"Uploaded {doc_type}")

        from .serializers import KYCDocumentSerializer
        return Response(
            KYCDocumentSerializer(doc, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )

    def delete(self, request, pk):
        """Delete a document by doc_type query param."""
        try:
            submission = KYCSubmission.objects.get(pk=pk, merchant=request.user)
        except KYCSubmission.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        doc_type = request.query_params.get('doc_type')
        if not doc_type:
            return Response({'detail': 'doc_type is required.'}, status=status.HTTP_400_BAD_REQUEST)

        deleted, _ = KYCDocument.objects.filter(submission=submission, doc_type=doc_type).delete()
        if not deleted:
            return Response({'detail': 'Document not found.'}, status=status.HTTP_404_NOT_FOUND)

        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Reviewer Views ────────────────────────────────────────────────────────────

class ReviewerQueueView(generics.ListAPIView):
    """
    Reviewer: paginated queue of submitted/under_review submissions.
    Ordered oldest-first (FIFO). SLA-at-risk items are flagged.
    """
    permission_classes = [IsAuthenticated, IsReviewer]
    serializer_class = KYCSubmissionListSerializer

    def get_queryset(self):
        qs = KYCSubmission.objects.filter(
            status__in=[KYCSubmission.Status.SUBMITTED, KYCSubmission.Status.UNDER_REVIEW]
        ).order_by('submitted_at')

        # Optional status filter
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        return qs


class ReviewerAllSubmissionsView(generics.ListAPIView):
    """Reviewer: view all submissions (any status) with optional filters."""
    permission_classes = [IsAuthenticated, IsReviewer]
    serializer_class = KYCSubmissionListSerializer

    def get_queryset(self):
        qs = KYCSubmission.objects.all().order_by('-updated_at')
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


class ReviewerSubmissionDetailView(generics.RetrieveAPIView):
    """Reviewer: full detail view of any submission."""
    permission_classes = [IsAuthenticated, IsReviewer]
    serializer_class = KYCSubmissionDetailSerializer
    queryset = KYCSubmission.objects.all()


class ReviewerPickupView(APIView):
    """Reviewer: picks up a submitted case → moves to under_review."""
    permission_classes = [IsAuthenticated, IsReviewer]

    def post(self, request, pk):
        try:
            submission = KYCSubmission.objects.get(pk=pk)
        except KYCSubmission.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            with transaction.atomic():
                old_status = submission.transition_to(
                    KYCSubmission.Status.UNDER_REVIEW,
                    reviewer=request.user
                )
                log_event(
                    submission, request.user, 'picked_up',
                    old_status=old_status, new_status='under_review'
                )
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            KYCSubmissionDetailSerializer(submission, context={'request': request}).data
        )


class ReviewerActionView(APIView):
    """Reviewer: approve / reject / request_info on a submission."""
    permission_classes = [IsAuthenticated, IsReviewer]

    ACTION_STATUS_MAP = {
        'approve': KYCSubmission.Status.APPROVED,
        'reject': KYCSubmission.Status.REJECTED,
        'request_info': KYCSubmission.Status.MORE_INFO_REQUESTED,
    }

    def post(self, request, pk):
        try:
            submission = KYCSubmission.objects.get(pk=pk)
        except KYCSubmission.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = ReviewActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        action = serializer.validated_data['action']
        reason = serializer.validated_data.get('reason', '')
        notes = serializer.validated_data.get('notes', '')
        new_status = self.ACTION_STATUS_MAP[action]

        try:
            with transaction.atomic():
                old_status = submission.transition_to(
                    new_status,
                    reviewer=request.user,
                    reason=reason,
                    notes=notes,
                )
                log_event(
                    submission, request.user, action,
                    old_status=old_status, new_status=new_status,
                    notes=reason or notes
                )
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            KYCSubmissionDetailSerializer(submission, context={'request': request}).data
        )


class ReviewerDashboardStatsView(APIView):
    """Reviewer: aggregate dashboard metrics."""
    permission_classes = [IsAuthenticated, IsReviewer]

    def get(self, request):
        from django.utils import timezone
        from datetime import timedelta

        all_subs = KYCSubmission.objects.all()
        at_risk = [s for s in all_subs.filter(status=KYCSubmission.Status.UNDER_REVIEW) if s.is_at_risk]

        stats = {
            'total': all_subs.count(),
            'draft': all_subs.filter(status=KYCSubmission.Status.DRAFT).count(),
            'submitted': all_subs.filter(status=KYCSubmission.Status.SUBMITTED).count(),
            'under_review': all_subs.filter(status=KYCSubmission.Status.UNDER_REVIEW).count(),
            'more_info_requested': all_subs.filter(status=KYCSubmission.Status.MORE_INFO_REQUESTED).count(),
            'approved': all_subs.filter(status=KYCSubmission.Status.APPROVED).count(),
            'rejected': all_subs.filter(status=KYCSubmission.Status.REJECTED).count(),
            'at_risk': len(at_risk),
        }
        return Response(stats)
