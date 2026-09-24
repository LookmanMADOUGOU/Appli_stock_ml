from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from stockapp import views as stock_views
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', stock_views.home, name='home'),
    path('info/', stock_views.info, name='info'),
    path('login/', auth_views.LoginView.as_view(template_name='stockapp/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),
    path('dashboard/', include('stockapp.urls')),
    path('api/', include('stockapp.api.urls')),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('service-worker.js', stock_views.service_worker, name='service-worker'),
    path('manifest.json', stock_views.pwa_manifest, name='manifest'),
    path('offline/', stock_views.offline_view, name='offline'),
]
