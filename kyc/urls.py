from django.urls import path
from .views import (
    MerchantSubmissionListCreateView,
    MerchantSubmissionDetailView,
    MerchantSubmitView,
    DocumentUploadView,
    ReviewerQueueView,
    ReviewerAllSubmissionsView,
    ReviewerSubmissionDetailView,
    ReviewerPickupView,
    ReviewerActionView,
    ReviewerDashboardStatsView,
)

urlpatterns = [
    # Merchant
    path('submissions/', MerchantSubmissionListCreateView.as_view(), name='submission-list-create'),
    path('submissions/<int:pk>/', MerchantSubmissionDetailView.as_view(), name='submission-detail'),
    path('submissions/<int:pk>/submit/', MerchantSubmitView.as_view(), name='submission-submit'),
    path('submissions/<int:pk>/documents/', DocumentUploadView.as_view(), name='document-upload'),

    # Reviewer
    path('reviewer/queue/', ReviewerQueueView.as_view(), name='reviewer-queue'),
    path('reviewer/submissions/', ReviewerAllSubmissionsView.as_view(), name='reviewer-submissions'),
    path('reviewer/submissions/<int:pk>/', ReviewerSubmissionDetailView.as_view(), name='reviewer-submission-detail'),
    path('reviewer/submissions/<int:pk>/pickup/', ReviewerPickupView.as_view(), name='reviewer-pickup'),
    path('reviewer/submissions/<int:pk>/action/', ReviewerActionView.as_view(), name='reviewer-action'),
    path('reviewer/stats/', ReviewerDashboardStatsView.as_view(), name='reviewer-stats'),
]
