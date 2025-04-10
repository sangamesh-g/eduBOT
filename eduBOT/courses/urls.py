from django.urls import path
from . import views

urlpatterns = [
    # Lesson view with quiz functionality
    path('lesson/<int:lesson_id>/', views.lesson_view, name='lesson_view'),
    
    # Quiz URLs
    path('quiz/start/<int:quiz_id>/', views.start_quiz, name='start_quiz'),
    path('quiz/attempt/<int:attempt_id>/', views.take_quiz, name='take_quiz'),
    path('quiz/submit-answer/<int:attempt_id>/', views.submit_answer, name='submit_answer'),
    path('quiz/submit/<int:attempt_id>/', views.submit_quiz, name='submit_quiz'),
    path('quiz/results/<int:attempt_id>/', views.quiz_results, name='quiz_results'),
    path('quiz/import/<int:quiz_id>/', views.import_quiz_questions, name='import_questions'),
    
    # Analytics
    path('analytics/', views.student_analytics, name='student_analytics'),
    
    # Placement test URLs
    path('placement-tests/', views.placement_test_list, name='placement_test_list'),
    path('placement-tests/<int:test_id>/start/', views.start_placement_test, name='start_placement_test'),
    path('placement-tests/attempt/<int:attempt_id>/submit/', views.submit_placement_test, name='submit_placement_test'),
    path('placement-tests/result/<int:attempt_id>/', views.placement_test_result, name='placement_test_result'),
    path('placement-tests/upload/', views.upload_placement_test, name='upload_placement_test'),
] 