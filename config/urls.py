from django.urls import path, include
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('api/auth/', include('users.urls')),
    path('api/kyc/', include('kyc.urls')),
    path('api/notifications/', include('notifications.urls')),
    path('', TemplateView.as_view(template_name='index.html')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
