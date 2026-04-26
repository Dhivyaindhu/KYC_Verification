from rest_framework.permissions import BasePermission


class IsMerchant(BasePermission):
    """Only merchant role users."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_merchant


class IsReviewer(BasePermission):
    """Only reviewer role users."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_reviewer


class IsMerchantOwnerOrReviewer(BasePermission):
    """Merchant can access only their own data; reviewers can access all."""
    def has_object_permission(self, request, view, obj):
        if request.user.is_reviewer:
            return True
        # For KYCDocument, check parent submission
        if hasattr(obj, 'submission'):
            return obj.submission.merchant == request.user
        return obj.merchant == request.user
