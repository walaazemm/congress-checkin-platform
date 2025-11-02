from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from participants import views as participant_views
#from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Authentication URLs
    path('accounts/login/', auth_views.LoginView.as_view(template_name='participants/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='checkin'), name='logout'),
    path('', include('participants.urls')),  # ← This includes your app's URLs
    #path('mark-present/<int:participant_id>/', views.mark_present, name='mark_present'),

    
    # App URLs
    path('', participant_views.checkin_view, name='checkin'),
    path('scan/', participant_views.scan_qr, name='scan_qr'),
    path('toggle-payment/<int:participant_id>/', participant_views.toggle_payment, name='toggle_payment'),
    path('toggle-meal/<int:participant_id>/<str:meal>/', participant_views.toggle_meal, name='toggle_meal'),
]