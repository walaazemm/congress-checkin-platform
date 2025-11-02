from django.urls import path
from . import views

urlpatterns = [
    path('', views.checkin_view, name='checkin'),
    path('scan/', views.scan_qr, name='scan_qr'),
    path('toggle-payment/<int:participant_id>/', views.toggle_payment, name='toggle_payment'),
    path('toggle-meal/<int:participant_id>/<str:meal>/', views.toggle_meal, name='toggle_meal'),
    path('dashboard/', views.dashboard, name='dashboard'),  # ← ADD THIS LINE
    path('mark-present/<int:participant_id>/', views.mark_present, name='mark_present'),
    path('participant/<int:participant_id>/', views.participant_detail_view, name='participant_detail'),
    path('api/stats/', views.dashboard_stats, name='dashboard_stats'),
    path('search/', views.search_participant, name='search_participant'),
    path('api/ai-report/', views.ai_report, name='ai_report'),
    path('export/', views.export_participants, name='export_participants'),
    path('toggle-presence/<int:participant_id>/', views.toggle_presence, name='toggle_presence'),
    path('admin-panel/', views.admin_panel, name='admin_panel'),
    path('admin-panel/create-user/', views.create_admin_user, name='create_admin_user'),
    path('admin-panel/edit-role/<int:user_id>/', views.edit_admin_role, name='edit_admin_role'),
    path('admin-panel/delete-user/<int:user_id>/', views.delete_admin_user, name='delete_admin_user'),
    path('admin-panel/reset-password/<int:user_id>/', views.reset_admin_password, name='reset_admin_password'),
    path('participants/', views.participants_list, name='participants_list'),
    path('participant/<int:participant_id>/edit/', views.edit_participant, name='edit_participant'),
    path('participants/add/', views.add_participant, name='add_participant'),
    path('participant/<int:participant_id>/delete/', views.delete_participant, name='delete_participant'),
    path('participants/bulk-delete/', views.bulk_delete_participants, name='bulk_delete_participants'),
    path('import-real/', views.import_real_participants, name='import_real_participants'),
    path('participants/delete-all/', views.delete_all_participants, name='delete_all_participants'),
]