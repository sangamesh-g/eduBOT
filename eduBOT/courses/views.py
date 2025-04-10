from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils import timezone
from django.db import transaction
from django.contrib import messages
from django.urls import reverse
from django.core.exceptions import PermissionDenied
import json
import random

from .models import (
    Course, Lesson, Enrollment, LessonProgress,
    Quiz, Question, Choice, QuizAttempt, Answer, StudentAnalytics,
    PlacementTest, PlacementTestAttempt, PlacementTestAnswer, PlacementTestChoice, PlacementTestQuestion
)

@login_required
def lesson_view(request, lesson_id):
    """View for displaying lesson content, including quizzes"""
    lesson = get_object_or_404(Lesson, id=lesson_id)
    course = lesson.section.course
    
    # Check if user is enrolled or is the teacher
    is_enrolled = Enrollment.objects.filter(user=request.user, course=course).exists()
    is_teacher = request.user == course.teacher
    
    if not (is_enrolled or is_teacher):
        messages.error(request, "You need to be enrolled in this course to view this lesson.")
        return redirect('course_detail', course_id=course.id)
    
    # Get quiz if exists
    quiz = None
    try:
        quiz = lesson.quiz
    except Quiz.DoesNotExist:
        pass
    
    # Get previous attempts if the user is a student
    attempts = []
    if is_enrolled and quiz:
        attempts = QuizAttempt.objects.filter(
            student=request.user,
            quiz=quiz,
            end_time__isnull=False
        ).order_by('-start_time')
    
    # Get lesson progress for enrolled students
    lesson_progress = None
    next_lesson = None
    if is_enrolled:
        enrollment = Enrollment.objects.get(user=request.user, course=course)
        lesson_progress, created = LessonProgress.objects.get_or_create(
            enrollment=enrollment,
            lesson=lesson
        )
        
        # Get next lesson if exists
        next_lesson = get_next_lesson(lesson)
    
    context = {
        'lesson': lesson,
        'course': course,
        'quiz': quiz,
        'attempts': attempts,
        'is_enrolled': is_enrolled,
        'is_teacher': is_teacher,
        'lesson_progress': lesson_progress,
        'next_lesson': next_lesson,
    }
    
    return render(request, 'course/lesson_view.html', context)

@login_required
def start_quiz(request, quiz_id):
    """View for starting a quiz"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    lesson = quiz.lesson
    course = lesson.section.course
    
    # Check if user is enrolled
    enrollment = get_object_or_404(Enrollment, user=request.user, course=course)
    
    # Check if there's an active attempt
    active_attempt = QuizAttempt.objects.filter(
        student=request.user,
        quiz=quiz,
        end_time__isnull=True
    ).first()
    
    if active_attempt:
        # Continue existing attempt
        return redirect('take_quiz', attempt_id=active_attempt.id)
    
    # Create a new attempt
    attempt = QuizAttempt.objects.create(
        student=request.user,
        quiz=quiz,
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )
    
    # Get questions and randomize if needed
    questions = list(quiz.questions.all())
    if quiz.randomize_questions:
        random.shuffle(questions)
    
    # Pre-create answer objects for all questions
    answers = []
    for question in questions:
        answers.append(Answer(
            attempt=attempt,
            question=question
        ))
    
    Answer.objects.bulk_create(answers)
    
    return redirect('take_quiz', attempt_id=attempt.id)

@login_required
@ensure_csrf_cookie
def take_quiz(request, attempt_id):
    """View for taking a quiz"""
    attempt = get_object_or_404(QuizAttempt, id=attempt_id)
    
    # Security check - only the student who started the attempt can take it
    if attempt.student != request.user:
        return HttpResponseForbidden("You don't have permission to access this quiz attempt.")
    
    # Check if attempt is already completed
    if attempt.end_time:
        return redirect('quiz_results', attempt_id=attempt.id)
    
    quiz = attempt.quiz
    
    # Get all questions for this attempt
    questions_with_answers = []
    for answer in attempt.answers.select_related('question').all():
        question = answer.question
        choices = list(question.choices.all())
        
        # Randomize choices if needed
        if quiz.randomize_choices:
            random.shuffle(choices)
        
        questions_with_answers.append({
            'question': question,
            'choices': choices,
            'answer': answer,
        })
    
    context = {
        'attempt': attempt,
        'quiz': quiz,
        'questions_with_answers': questions_with_answers,
        'remaining_time': quiz.time_limit * 60,  # Convert to seconds
        'prevent_tab_switch': quiz.prevent_tab_switch,
    }
    
    return render(request, 'course/take_quiz.html', context)

@login_required
def submit_answer(request, attempt_id):
    """AJAX view for submitting an individual answer"""
    if request.method != 'POST' or not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    attempt = get_object_or_404(QuizAttempt, id=attempt_id)
    
    # Security check
    if attempt.student != request.user or attempt.end_time:
        return JsonResponse({'success': False, 'error': 'Unauthorized access'})
    
    # Get data from request
    try:
        data = json.loads(request.body)
        question_id = data.get('question_id')
        choice_id = data.get('choice_id')
        time_taken = data.get('time_taken')
        
        question = get_object_or_404(Question, id=question_id)
        choice = get_object_or_404(Choice, id=choice_id) if choice_id else None
        
        # Make sure question belongs to the quiz
        if question.quiz != attempt.quiz:
            return JsonResponse({'success': False, 'error': 'Question does not belong to this quiz'})
        
        # Update or create the answer
        answer, created = Answer.objects.update_or_create(
            attempt=attempt,
            question=question,
            defaults={
                'selected_choice': choice,
                'time_taken': time_taken
            }
        )
        
        response_data = {
            'success': True,
            'answer_id': answer.id,
        }
        
        # If show immediate results is enabled, return correctness
        if attempt.quiz.show_result_immediately:
            response_data['is_correct'] = answer.is_correct
            
            if answer.is_correct:
                response_data['feedback'] = "Correct!"
            else:
                correct_choice = question.choices.filter(is_correct=True).first()
                response_data['feedback'] = f"Incorrect. The correct answer is: {correct_choice.text}"
                if question.explanation:
                    response_data['explanation'] = question.explanation
        
        return JsonResponse(response_data)
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def submit_quiz(request, attempt_id):
    """View for submitting the entire quiz"""
    attempt = get_object_or_404(QuizAttempt, id=attempt_id)
    
    # Security check
    if attempt.student != request.user:
        return HttpResponseForbidden("You don't have permission to submit this quiz.")
    
    # Check if already completed
    if attempt.end_time:
        return redirect('quiz_results', attempt_id=attempt.id)
    
    # Calculate score
    with transaction.atomic():
        score = attempt.calculate_score()
        
        # Update the lesson progress
        lesson = attempt.quiz.lesson
        course = lesson.section.course
        enrollment = Enrollment.objects.get(user=request.user, course=course)
        
        lesson_progress, created = LessonProgress.objects.get_or_create(
            enrollment=enrollment,
            lesson=lesson
        )
        
        # Mark lesson as completed if quiz passed
        if attempt.passed:
            lesson_progress.completed = True
            lesson_progress.completed_date = timezone.now()
            lesson_progress.save()
            
            # Update student analytics
            try:
                analytics = StudentAnalytics.objects.get(student_profile=request.user.studentprofile)
            except StudentAnalytics.DoesNotExist:
                analytics = StudentAnalytics.objects.create(student_profile=request.user.studentprofile)
            
            analytics.update_statistics()
    
    return redirect('quiz_results', attempt_id=attempt.id)

@login_required
def record_tab_switch(request, attempt_id):
    """AJAX view to record tab switches"""
    if request.method != 'POST' or not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    attempt = get_object_or_404(QuizAttempt, id=attempt_id)
    
    # Security check
    if attempt.student != request.user or attempt.end_time:
        return JsonResponse({'success': False, 'error': 'Unauthorized access'})
    
    # Increment tab switch counter
    attempt.tab_switches += 1
    attempt.save(update_fields=['tab_switches'])
    
    return JsonResponse({
        'success': True,
        'tab_switches': attempt.tab_switches
    })

@login_required
def quiz_results(request, attempt_id):
    """View for displaying quiz results"""
    attempt = get_object_or_404(QuizAttempt, id=attempt_id)
    
    # Security check - only the student who took the quiz or the course teacher can see results
    course = attempt.quiz.lesson.section.course
    is_teacher = request.user == course.teacher
    
    if attempt.student != request.user and not is_teacher:
        return HttpResponseForbidden("You don't have permission to view these results.")
    
    # Get all answers with questions and selected choices
    answers = attempt.answers.select_related('question', 'selected_choice').all()
    
    # Organize data for display
    questions_data = []
    for answer in answers:
        correct_choice = answer.question.choices.filter(is_correct=True).first()
        questions_data.append({
            'question': answer.question,
            'selected_choice': answer.selected_choice,
            'correct_choice': correct_choice,
            'is_correct': answer.is_correct,
            'time_taken': answer.time_taken,
        })
    
    # Get next lesson if exists
    next_lesson = None
    if attempt.passed:
        next_lesson = get_next_lesson(attempt.quiz.lesson)
    
    context = {
        'attempt': attempt,
        'quiz': attempt.quiz,
        'questions_data': questions_data,
        'next_lesson': next_lesson,
        'is_teacher': is_teacher,
    }
    
    return render(request, 'course/quiz_results.html', context)

@login_required
def student_analytics(request):
    """View for displaying student analytics"""
    # Only accessible by students
    if not hasattr(request.user, 'studentprofile'):
        raise PermissionDenied
    
    # Get or create analytics record
    analytics, created = StudentAnalytics.objects.get_or_create(student_profile=request.user.studentprofile)
    
    # Update statistics if needed
    if created:
        analytics.update_statistics()
    
    # Get recent quiz attempts
    recent_attempts = QuizAttempt.objects.filter(
        student=request.user,
        end_time__isnull=False
    ).select_related('quiz__lesson__section__course').order_by('-end_time')[:10]
    
    context = {
        'analytics': analytics,
        'recent_attempts': recent_attempts,
    }
    
    return render(request, 'course/student_analytics.html', context)

@login_required
def import_quiz_questions(request, quiz_id):
    """View for importing quiz questions from Excel"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    course = quiz.lesson.section.course
    
    # Only the course teacher can import questions
    if request.user != course.teacher:
        return HttpResponseForbidden("You don't have permission to import questions for this quiz.")
    
    if request.method == 'POST' and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']
        
        success, message = quiz.import_questions_from_excel(excel_file)
        
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
        
        return redirect('lesson_view', lesson_id=quiz.lesson.id)
    
    return render(request, 'course/import_questions.html', {'quiz': quiz})

@login_required
def placement_test_list(request):
    """View for listing available placement tests"""
    tests = PlacementTest.objects.filter(is_active=True)
    context = {
        'tests': tests
    }
    return render(request, 'courses/placement_test_list.html', context)

@login_required
def start_placement_test(request, test_id):
    """View for starting a placement test"""
    test = get_object_or_404(PlacementTest, id=test_id, is_active=True)
    
    # Check if user has already completed this test
    existing_attempt = PlacementTestAttempt.objects.filter(
        student=request.user,
        test=test,
        completed=True
    ).first()
    
    if existing_attempt:
        messages.info(request, f"You have already completed this test. Your recommended level is {existing_attempt.recommended_level}.")
        return redirect('placement_test_result', attempt_id=existing_attempt.id)
    
    # Create new attempt
    attempt = PlacementTestAttempt.objects.create(
        student=request.user,
        test=test
    )
    
    context = {
        'test': test,
        'attempt': attempt,
        'questions': test.questions.all().prefetch_related('choices')
    }
    return render(request, 'courses/placement_test.html', context)

@login_required
def submit_placement_test(request, attempt_id):
    """View for submitting placement test answers"""
    attempt = get_object_or_404(PlacementTestAttempt, id=attempt_id, student=request.user, completed=False)
    
    if request.method == 'POST':
        with transaction.atomic():
            # Save all answers
            for question in attempt.test.questions.all():
                choice_id = request.POST.get(f'question_{question.id}')
                if choice_id:
                    choice = get_object_or_404(PlacementTestChoice, id=choice_id, question=question)
                    PlacementTestAnswer.objects.create(
                        attempt=attempt,
                        question=question,
                        choice=choice
                    )
            
            # Calculate score and recommended level
            recommended_level = attempt.calculate_score()
            attempt.end_time = timezone.now()
            attempt.save()
            
            messages.success(request, f"Test completed! Your recommended level is {recommended_level}.")
            return redirect('placement_test_result', attempt_id=attempt.id)
    
    return redirect('placement_test_list')

@login_required
def placement_test_result(request, attempt_id):
    """View for displaying placement test results"""
    attempt = get_object_or_404(PlacementTestAttempt, id=attempt_id, student=request.user)
    
    # Get recommended courses
    recommended_courses = Course.objects.filter(
        category=attempt.test.category,
        level=attempt.recommended_level,
        is_published=True
    )
    
    context = {
        'attempt': attempt,
        'recommended_courses': recommended_courses
    }
    return render(request, 'courses/placement_test_result.html', context)

@login_required
def upload_placement_test(request):
    """View for uploading placement test via CSV/Excel"""
    if not request.user.is_staff:
        raise PermissionDenied
    
    if request.method == 'POST' and request.FILES.get('test_file'):
        file = request.FILES['test_file']
        category_id = request.POST.get('category')
        category = get_object_or_404(Category, id=category_id)
        
        try:
            if file.name.endswith('.csv'):
                # Handle CSV file
                import csv
                reader = csv.DictReader(file)
                with transaction.atomic():
                    test = PlacementTest.objects.create(
                        title=request.POST.get('title'),
                        description=request.POST.get('description'),
                        category=category,
                        time_limit=int(request.POST.get('time_limit', 30)),
                        basic_cutoff=int(request.POST.get('basic_cutoff', 7)),
                        intermediate_cutoff=int(request.POST.get('intermediate_cutoff', 15))
                    )
                    
                    for row in reader:
                        question = PlacementTestQuestion.objects.create(
                            test=test,
                            text=row['question'],
                            marks=float(row.get('marks', 1.0)),
                            order=int(row.get('order', 0))
                        )
                        
                        # Add choices
                        for i in range(1, 5):  # Assuming 4 choices
                            choice_text = row.get(f'choice_{i}')
                            if choice_text:
                                PlacementTestChoice.objects.create(
                                    question=question,
                                    text=choice_text,
                                    is_correct=(row.get('correct_choice') == str(i)),
                                    order=i
                                )
            
            elif file.name.endswith(('.xls', '.xlsx')):
                # Handle Excel file
                import pandas as pd
                df = pd.read_excel(file)
                with transaction.atomic():
                    test = PlacementTest.objects.create(
                        title=request.POST.get('title'),
                        description=request.POST.get('description'),
                        category=category,
                        time_limit=int(request.POST.get('time_limit', 30)),
                        basic_cutoff=int(request.POST.get('basic_cutoff', 7)),
                        intermediate_cutoff=int(request.POST.get('intermediate_cutoff', 15))
                    )
                    
                    for _, row in df.iterrows():
                        question = PlacementTestQuestion.objects.create(
                            test=test,
                            text=row['question'],
                            marks=float(row.get('marks', 1.0)),
                            order=int(row.get('order', 0))
                        )
                        
                        # Add choices
                        for i in range(1, 5):  # Assuming 4 choices
                            choice_text = row.get(f'choice_{i}')
                            if choice_text:
                                PlacementTestChoice.objects.create(
                                    question=question,
                                    text=choice_text,
                                    is_correct=(row.get('correct_choice') == str(i)),
                                    order=i
                                )
            
            messages.success(request, 'Placement test uploaded successfully!')
            return redirect('placement_test_list')
            
        except Exception as e:
            messages.error(request, f'Error uploading test: {str(e)}')
    
    categories = Category.objects.all()
    context = {
        'categories': categories
    }
    return render(request, 'courses/upload_placement_test.html', context)

# Utility functions
def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def get_next_lesson(current_lesson):
    """Get the next lesson in sequence"""
    section = current_lesson.section
    
    # Try to get next lesson in the same section
    next_in_section = Lesson.objects.filter(
        section=section,
        order__gt=current_lesson.order
    ).order_by('order').first()
    
    if next_in_section:
        return next_in_section
    
    # Try to get first lesson in the next section
    course = section.course
    next_section = section.course.sections.filter(order__gt=section.order).order_by('order').first()
    
    if next_section:
        return next_section.lessons.order_by('order').first()
    
    return None
