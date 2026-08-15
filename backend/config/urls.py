"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, re_path

from generation import views

# The trailing slash is optional on every API route, and that is not cosmetic: Next normalises
# `/api/generate/` to `/api/generate` before it matches a rewrite, and Django's APPEND_SLASH
# cannot redirect a POST without dropping its body. Accepting both ends that argument.
urlpatterns = [
    path('admin/', admin.site.urls),
    re_path(r'^api/options/?$', views.options),
    re_path(r'^api/generate/?$', views.generate),
    re_path(r'^api/jobs/(?P<job_id>[0-9a-f-]{36})/?$', views.job_status),
]

# The frontend loads generated cards straight from here in development. The Next app proxies
# /api and /media to this process (frontend/next.config.ts), so there is no CORS setup to keep
# in sync and no second origin.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
