from django.urls import path
from .views import SubmissionAuditLogView, AllEventsView

urlpatterns = [
    path('submission/<int:submission_id>/', SubmissionAuditLogView.as_view(), name='submission-audit'),
    path('all/', AllEventsView.as_view(), name='all-events'),
]
