from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    # Main pages
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Authentication
    path('register/', views.register, name='register'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    
    # Password reset
    path('password-reset/', 
         auth_views.PasswordResetView.as_view(template_name='accounts/password_reset.html'), 
         name='password_reset'),
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(template_name='accounts/password_reset_done.html'), 
         name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(template_name='accounts/password_reset_confirm.html'), 
         name='password_reset_confirm'),
    path('password-reset-complete/', 
         auth_views.PasswordResetCompleteView.as_view(template_name='accounts/password_reset_complete.html'), 
         name='password_reset_complete'),
    
    # Profile
    path('profile/', views.profile, name='profile'),
    path('profile/update-account/', views.update_account, name='update_account'),
    path('profile/update-profile/', views.update_profile, name='update_profile'),
    path('profile/change-password/', views.change_password, name='change_password'),
    path('profile/upload-picture/', views.upload_profile_picture, name='upload_profile_picture'),
    
    # Courses
    path('courses/', views.courses, name='courses'),
    path('courses/create/', views.create_course, name='create_course'),
    path('courses/<int:course_id>/', views.course_detail, name='course_detail'),
    path('courses/<int:course_id>/edit/', views.edit_course, name='edit_course'),
    path('courses/<int:course_id>/enroll/', views.enroll_course, name='enroll_course'),
    path('courses/<int:course_id>/review/', views.submit_review, name='submit_review'),
    
    # Messages
    path('messages/', views.user_messages, name='messages'),
    path('messages/new/', views.new_conversation, name='new_conversation'),
    path('messages/send/<int:conversation_id>/', views.send_message, name='send_message'),
    path('messages/forward/<int:message_id>/', views.forward_message, name='forward_message'),
    path('messages/delete/<int:message_id>/', views.delete_message, name='delete_message'),
    path('messages/check_new/<int:conversation_id>/', views.check_new_messages, name='check_new_messages'),
    path('messages/typing/<int:conversation_id>/', views.typing_status, name='typing_status'),
]
