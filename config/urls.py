from django.urls import path, include
from django.http import HttpResponse
from django.conf import settings
from django.conf.urls.static import static
import os

def serve_frontend(request):
    with open(os.path.join(settings.BASE_DIR, 'templates', 'index.html'), 'r') as f:
        content = f.read()
    return HttpResponse(content, content_type='text/html')

urlpatterns = [
    path('api/auth/', include('users.urls')),
    path('api/kyc/', include('kyc.urls')),
    path('api/notifications/', include('notifications.urls')),
    path('', serve_frontend),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
