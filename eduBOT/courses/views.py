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
    """Submit an answer for a quiz question"""
    attempt = get_object_or_404(QuizAttempt, id=attempt_id, student=request.user)
    data = json.loads(request.body)
    
    question_id = data.get('question_id')
    option_id = data.get('option_id')  # This will be 'A', 'B', 'C', or 'D'
    time_taken = data.get('time_taken')
    
    question = get_object_or_404(Question, id=question_id, quiz=attempt.quiz)
    
    # Create or update the answer
    answer, created = Answer.objects.get_or_create(
        attempt=attempt,
        question=question,
        defaults={
            'selected_option': option_id,
            'time_taken': time_taken
        }
    )
    
    if not created:
        answer.selected_option = option_id
        answer.time_taken = time_taken
        answer.save()
    
    # Return whether the answer is correct
    return JsonResponse({
        'success': True,
        'is_correct': answer.is_correct,
        'selected_option': answer.selected_option,
        'numeric_option': answer.selected_numeric_option
    })

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
    
    # Get all answers with questions
    answers = attempt.answers.select_related('question').all()
    
    # Organize data for display
    questions_data = []
    for answer in answers:
        correct_choice = answer.question.choices.filter(is_correct=True).first()
        questions_data.append({
            'question': answer.question,
            'selected_option': answer.selected_option,
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
    """View for listing available placement tests and previous attempts"""
    # Get all active placement tests
    tests = PlacementTest.objects.filter(is_active=True).select_related('category')
    
    # Get user's previous attempts
    previous_attempts = PlacementTestAttempt.objects.filter(
        student=request.user,
        completed=True
    ).select_related('test').order_by('-end_time')
    
    context = {
        'tests': tests,
        'previous_attempts': previous_attempts
    }
    
    return render(request, 'courses/placement_test_list.html', context)

@login_required
def start_placement_test(request, test_id):
    """View for starting a placement test"""
    test = get_object_or_404(PlacementTest, id=test_id, is_active=True)
    
    # Create a new attempt
    attempt = PlacementTestAttempt.objects.create(
        student=request.user,
        test=test
    )
    
    # Get all questions
    questions = test.questions.all().order_by('order')
    
    context = {
        'attempt': attempt,
        'test': test,
        'questions': questions,
        'time_limit': test.time_limit * 60  # Convert to seconds
    }
    return render(request, 'courses/take_placement_test.html', context)

@login_required
def submit_placement_test(request, attempt_id):
    """View for submitting a placement test"""
    attempt = get_object_or_404(PlacementTestAttempt, id=attempt_id, student=request.user)
    
    if request.method == 'POST':
        with transaction.atomic():
            # Record answers
            total_score = 0
            for question in attempt.test.questions.all():
                selected_choice = request.POST.get(f'question_{question.id}')
                if selected_choice:
                    # Convert to integer choice number (1-4)
                    selected_choice_num = int(selected_choice)
                    
                    # Create answer
                    answer = PlacementTestAnswer.objects.create(
                        attempt=attempt,
                        question=question,
                        choice_number=selected_choice_num
                    )
                    
                    # Check if selected choice is correct
                    if selected_choice_num == question.correct_choice:
                        total_score += question.marks
            
            # Update attempt
            attempt.score = total_score
            attempt.end_time = timezone.now()
            attempt.completed = True
            
            # Determine recommended level
            if total_score >= attempt.test.intermediate_cutoff:
                attempt.recommended_level = 'hard'
            elif total_score >= attempt.test.basic_cutoff:
                attempt.recommended_level = 'medium'
            else:
                attempt.recommended_level = 'basic'
            
            attempt.save()
            
            return redirect('placement_test_result', attempt_id=attempt.id)
    
    return redirect('start_placement_test', test_id=attempt.test.id)

@login_required
def placement_test_result(request, attempt_id):
    """View for showing placement test results"""
    attempt = get_object_or_404(PlacementTestAttempt, id=attempt_id, student=request.user)
    
    # Get all answers with questions
    answers = attempt.answers.select_related('question').all()
    
    # Prepare data for the template
    answer_data = []
    for answer in answers:
        question = answer.question
        choice_number = answer.choice_number
        
        # Get the text for the selected choice
        selected_text = getattr(question, f'choice_text_{choice_number}', '')
        
        # Check if the answer is correct
        is_correct = (choice_number == question.correct_choice)
        
        # Get the correct choice text
        correct_text = getattr(question, f'choice_text_{question.correct_choice}', '')
        
        answer_data.append({
            'question': question,
            'selected_choice': choice_number,
            'selected_text': selected_text,
            'is_correct': is_correct,
            'correct_text': correct_text
        })
    
    # Get relevant courses based on the recommended level
    relevant_courses = Course.objects.filter(
        category=attempt.test.category,
        level=attempt.recommended_level,
        is_published=True
    )
    
    context = {
        'attempt': attempt,
        'answers': answer_data,
        'relevant_courses': relevant_courses,
        'can_retake': True  # Allow retaking the test
    }
    return render(request, 'courses/placement_test_result.html', context)

@login_required
def course_recommendations(request, course_id, attempt_id):
    """View for showing course recommendations based on placement test results"""
    course = get_object_or_404(Course, id=course_id)
    attempt = get_object_or_404(PlacementTestAttempt, id=attempt_id, student=request.user)
    
    # Get recommended courses based on the placement test results
    recommended_courses = Course.objects.filter(
        category=course.category,
        level=attempt.recommended_level,
        is_published=True
    )
    
    context = {
        'attempt': attempt,
        'recommended_courses': recommended_courses,
        'current_course': course
    }
    
    return render(request, 'courses/course_recommendations.html', context)

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
                        # Create question with direct choice fields
                        question = PlacementTestQuestion.objects.create(
                            test=test,
                            text=row['question'],
                            marks=float(row.get('marks', 1.0)),
                            order=int(row.get('order', 0)),
                            choice_text_1=row.get('choice_1', ''),
                            choice_text_2=row.get('choice_2', ''),
                            choice_text_3=row.get('choice_3', ''),
                            choice_text_4=row.get('choice_4', ''),
                            correct_choice=int(row.get('correct_choice', 1))
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
                        # Create question with direct choice fields
                        question = PlacementTestQuestion.objects.create(
                            test=test,
                            text=row['question'],
                            marks=float(row.get('marks', 1.0)),
                            order=int(row.get('order', 0)),
                            choice_text_1=row.get('choice_1', ''),
                            choice_text_2=row.get('choice_2', ''),
                            choice_text_3=row.get('choice_3', ''),
                            choice_text_4=row.get('choice_4', ''),
                            correct_choice=int(row.get('correct_choice', 1))
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

@login_required
def enroll_course(request, course_id):
    """View for enrolling in a course with placement test requirement check"""
    course = get_object_or_404(Course, id=course_id)
    
    # Check if user is already enrolled
    if Enrollment.objects.filter(user=request.user, course=course).exists():
        messages.warning(request, "You are already enrolled in this course.")
        return redirect('course_detail', course_id=course.id)
    
    # Check if placement test is required for this course category
    required_test = PlacementTest.objects.filter(
        category=course.category,
        is_active=True
    ).first()
    
    if required_test:
        # Check if user has a valid placement test attempt
        latest_attempt = PlacementTestAttempt.objects.filter(
            student=request.user,
            test=required_test,
            completed=True
        ).order_by('-end_time').first()
        
        if not latest_attempt:
            messages.info(request, f"You need to take a placement test before enrolling in {course.category} courses.")
            return redirect('start_placement_test', test_id=required_test.id)
        
        # Check if the course level matches the recommended level
        if latest_attempt.recommended_level != course.level:
            recommended_courses = Course.objects.filter(
                category=course.category,
                level=latest_attempt.recommended_level,
                is_published=True
            )
            messages.warning(request, 
                f"Based on your placement test score, we recommend {latest_attempt.recommended_level} level courses. "
                "Please choose from the recommended courses below or retake the test.")
            return render(request, 'courses/course_recommendations.html', {
                'attempt': latest_attempt,
                'recommended_courses': recommended_courses,
                'current_course': course
            })
    
    # Create enrollment
    enrollment = Enrollment.objects.create(
        user=request.user,
        course=course
    )
    
    messages.success(request, f"Successfully enrolled in {course.title}! You can now start learning.")
    return redirect('dashboard')

@login_required
def course_detail(request, course_id):
    """View for displaying course details"""
    course = get_object_or_404(Course, id=course_id)
    
    # Check if user is enrolled or is the teacher
    is_enrolled = Enrollment.objects.filter(user=request.user, course=course).exists()
    is_teacher = request.user == course.teacher
    
    # Get placement test requirements
    required_test = None
    latest_attempt = None
    has_active_test = False
    has_completed_test = False
    is_recommended_level = True
    recommended_level = None
    test_attempt = None
    active_test = None
    
    if not is_enrolled and not is_teacher:
        # Find active placement test for this course category
        active_test = PlacementTest.objects.filter(
            category=course.category,
            is_active=True
        ).first()
        
        has_active_test = active_test is not None
        
        if has_active_test:
            # Check if user has completed this test
            test_attempt = PlacementTestAttempt.objects.filter(
                student=request.user,
                test=active_test,
                completed=True
            ).order_by('-end_time').first()
            
            has_completed_test = test_attempt is not None
            
            # If they completed the test, check if the course level matches their recommended level
            if has_completed_test:
                # Get recommended level from the test attempt
                recommended_level = test_attempt.recommended_level
                is_recommended_level = recommended_level == course.level.lower()
    
    # Get course progress for enrolled students
    progress = None
    first_lesson = None
    if is_enrolled:
        enrollment = Enrollment.objects.get(user=request.user, course=course)
        completed_lessons = LessonProgress.objects.filter(
            enrollment=enrollment,
            completed=True
        ).count()
        total_lessons = sum(section.lessons.count() for section in course.sections.all())
        if total_lessons > 0:
            progress = (completed_lessons / total_lessons) * 100
        
        # Get the first lesson for the continue learning button
        first_section = course.sections.order_by('order').first()
        if first_section:
            first_lesson = first_section.lessons.order_by('order').first()
    
    context = {
        'course': course,
        'is_enrolled': is_enrolled,
        'is_teacher': is_teacher,
        'progress': progress,
        'has_active_test': has_active_test,
        'has_completed_test': has_completed_test,
        'is_recommended_level': is_recommended_level,
        'recommended_level': recommended_level,
        'test_attempt': test_attempt,
        'active_test': active_test,
        'first_lesson': first_lesson
    }
    
    return render(request, 'courses/course_detail.html', context)

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
