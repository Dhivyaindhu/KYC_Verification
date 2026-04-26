from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers
from .models import NotificationEvent
from kyc.permissions import IsReviewer


class NotificationEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source='actor.full_name', read_only=True)
    actor_email = serializers.CharField(source='actor.email', read_only=True)

    class Meta:
        model = NotificationEvent
        fields = ['id', 'submission', 'actor_name', 'actor_email', 'event_type',
                  'old_status', 'new_status', 'notes', 'created_at']


class SubmissionAuditLogView(generics.ListAPIView):
    """Audit trail for a specific submission."""
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationEventSerializer

    def get_queryset(self):
        submission_id = self.kwargs['submission_id']
        user = self.request.user
        qs = NotificationEvent.objects.filter(submission_id=submission_id)
        if user.is_merchant:
            qs = qs.filter(submission__merchant=user)
        return qs


class AllEventsView(generics.ListAPIView):
    """Reviewer-only: all events across all submissions."""
    permission_classes = [IsAuthenticated, IsReviewer]
    serializer_class = NotificationEventSerializer
    queryset = NotificationEvent.objects.all().select_related('actor', 'submission')
