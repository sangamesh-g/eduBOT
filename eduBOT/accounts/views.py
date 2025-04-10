from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Avg, Count
from django.utils import timezone
from django.core.paginator import Paginator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.apps import apps
import json

from .models import TeacherProfile, StudentProfile, User, Conversation, Message
from .forms import UserRegisterForm, UserUpdateForm, TeacherProfileUpdateForm, StudentProfileUpdateForm
from .utils import delete_old_profile_picture

# Import course-related models from course app
Course = apps.get_model('courses', 'Course')
Enrollment = apps.get_model('courses', 'Enrollment')
Category = apps.get_model('courses', 'Category')
Review = apps.get_model('courses', 'Review')
Lesson = apps.get_model('courses', 'Lesson')

def home(request):
    """View for the home page"""
    courses = Course.objects.filter(is_published=True).order_by('-created_at')[:6]
    categories = Category.objects.annotate(course_count=Count('courses')).order_by('-course_count')[:6]
    
    context = {
        'courses': courses,
        'categories': categories,
    }
    return render(request, 'accounts/home.html', context)

def about(request):
    """View for the about page"""
    return render(request, 'accounts/about.html')

@ensure_csrf_cookie
def register(request):
    """View for user registration"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                user_type = request.POST.get('user_type')
                
                try:
                    if user_type == 'teacher':
                        # Create teacher profile with specific fields
                        TeacherProfile.objects.create(
                            user=user,
                            specialization=request.POST.get('specialization', ''),
                            experience=int(request.POST.get('experience', 0)),
                            account_name=request.POST.get('account_name', ''),
                            account_number=request.POST.get('account_number', ''),
                            bank_name=request.POST.get('bank_name', ''),
                            ifsc_code=request.POST.get('ifsc_code', '')
                        )
                    else:
                        # Create student profile with specific fields
                        StudentProfile.objects.create(
                            user=user,
                            interests=request.POST.get('interests', ''),
                            education_level=request.POST.get('education_level', '')
                        )
                    
                    login(request, user)
                    messages.success(request, 'Your account has been created successfully!')
                    return redirect('dashboard')
                except Exception as e:
                    # If there's an error, rollback the transaction
                    transaction.set_rollback(True)
                    messages.error(request, f'Error creating profile: {str(e)}')
                    return redirect('register')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = UserRegisterForm()
    
    return render(request, 'accounts/register.html', {'form': form})

def user_login(request):
    """View for user login"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'accounts/login.html')

@login_required
def user_logout(request):
    """View for user logout"""
    logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('home')

@login_required
def dashboard(request):
    """View for user dashboard"""
    user = request.user
    
    if hasattr(user, 'teacherprofile'):
        # Teacher dashboard
        courses = Course.objects.filter(teacher=user)
        total_students = Enrollment.objects.filter(course__teacher=user).count()
        average_rating = Review.objects.filter(course__teacher=user).aggregate(Avg('rating'))['rating__avg'] or 0
        
        context = {
            'courses': courses,
            'total_students': total_students,
            'average_rating': round(average_rating, 1),
        }
        return render(request, 'accounts/dashboard.html', context)
    
    elif hasattr(user, 'studentprofile'):
        # Student dashboard
        enrollments = Enrollment.objects.filter(user=user)
        
        context = {
            'enrollments': enrollments,
        }
    return render(request, 'accounts/dashboard.html', context)
    
    # Handle case where user has no profile
    messages.error(request, 'No profile found. Please contact support.')
    return redirect('home')

@login_required
def profile(request):
    """View for user profile"""
    user = request.user
    context = {}
    
    if hasattr(user, 'teacherprofile'):
        # Teacher profile context
        teacher_profile = user.teacherprofile
        courses = Course.objects.filter(teacher=user)
        
        context.update({
            'is_teacher': True,
            'profile': teacher_profile,
            'courses': courses,
            'total_students': Enrollment.objects.filter(course__teacher=user).count(),
            'average_rating': Review.objects.filter(course__teacher=user).aggregate(Avg('rating'))['rating__avg'] or 0
        })
    
    elif hasattr(user, 'studentprofile'):
        # Student profile context
        student_profile = user.studentprofile
        enrollments = Enrollment.objects.filter(user=user)
        
        context.update({
            'is_teacher': False,
            'profile': student_profile,
            'enrollments': enrollments,
            'completed_courses': enrollments.filter(completed=True).count(),
            'in_progress_courses': enrollments.filter(completed=False).count()
        })
    
    return render(request, 'accounts/profile.html', context)

@login_required
def update_account(request):
    """View to update user account information"""
    if request.method == 'POST':
        form = UserUpdateForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your account has been updated successfully!')
            return redirect('profile')
        else:
            messages.error(request, 'Please correct the errors below.')
    
    return redirect('profile')

@login_required
def update_profile(request):
    """View to update user profile"""
    if request.method == 'POST':
        if hasattr(request.user, 'teacherprofile'):
            form = TeacherProfileUpdateForm(
                request.POST,
                request.FILES,
                instance=request.user.teacherprofile
            )
        elif hasattr(request.user, 'studentprofile'):
            form = StudentProfileUpdateForm(
                request.POST,
                request.FILES,
                instance=request.user.studentprofile
            )
        else:
            messages.error(request, 'Profile not found.')
            return redirect('profile')
        
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile has been updated successfully!')
        else:
            messages.error(request, 'Please correct the errors below.')
    
    return redirect('profile')

@login_required
def change_password(request):
    """View to change user password"""
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Your password has been updated successfully!')
        else:
            messages.error(request, 'Please correct the errors below.')
    
    return redirect('profile')

@login_required
def upload_profile_picture(request):
    """View to upload profile picture via AJAX"""
    if request.method == 'POST' and request.FILES.get('profile_picture'):
        user = request.user
        
        # Get the appropriate profile based on user type
        if hasattr(user, 'teacherprofile'):
            profile = user.teacherprofile
        elif hasattr(user, 'studentprofile'):
            profile = user.studentprofile
        else:
            return JsonResponse({'success': False, 'error': 'Profile not found'})
        
        try:
            # Delete old profile picture if it exists
            delete_old_profile_picture(profile)
            
            # Save new profile picture
            profile.profile_picture = request.FILES['profile_picture']
            profile.save()
            
            # Return the new image URL with a timestamp to prevent caching
            from django.utils.timezone import now
            timestamp = int(now().timestamp())
            
            return JsonResponse({
                'success': True,
                'image_url': f"{profile.profile_picture.url}?t={timestamp}"
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@login_required
def courses(request):
    """View for course catalog"""
    try:
        # Get all courses first
        courses = Course.objects.all().select_related('teacher', 'category')
        
        # Get filters
        categories = Category.objects.all()
        selected_category = request.GET.get('category')
        search_query = request.GET.get('q')
        level_filter = request.GET.get('level')
        sort_by = request.GET.get('sort_by', 'newest')
        
        # Apply filters only if they are provided
        if selected_category:
            courses = courses.filter(category__slug=selected_category)
        
        if search_query:
            courses = courses.filter(title__icontains=search_query)
        
        if level_filter:
            courses = courses.filter(level=level_filter)
        
        # Apply sorting
        if sort_by == 'rating':
            courses = courses.annotate(avg_rating=Avg('reviews__rating')).order_by('-avg_rating')
        else:  # Default: newest
            courses = courses.order_by('-created_at')
        
        # Debug information
        print(f"Total courses before pagination: {courses.count()}")
        
        # Pagination
        paginator = Paginator(courses, 9)  # 9 courses per page
        page_number = request.GET.get('page', 1)
        courses = paginator.get_page(page_number)
        
        context = {
            'courses': courses,
            'categories': categories,
            'selected_category': selected_category,
            'search_query': search_query,
            'level_filter': level_filter,
            'sort_by': sort_by,
            'level_choices': Course.LEVEL_CHOICES,
            'total_courses': courses.paginator.count if hasattr(courses, 'paginator') else len(courses),
        }
        
        return render(request, 'accounts/courses.html', context)
        
    except Exception as e:
        messages.error(request, f"Error loading courses: {str(e)}")
        return render(request, 'accounts/courses.html', {'courses': [], 'error': str(e)})

@login_required
def course_detail(request, course_id):
    """View for course details"""
    try:
        course = get_object_or_404(Course, id=course_id, is_published=True)
        is_enrolled = Enrollment.objects.filter(user=request.user, course=course).exists()
        is_teacher = request.user == course.teacher
        reviews = Review.objects.filter(course=course).select_related('user')
        
        # Calculate course stats
        total_students = course.enrollments.count()
        average_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0
        
        # Check if user has already reviewed this course
        user_review = None
        if not is_teacher:
            user_review = Review.objects.filter(user=request.user, course=course).first()
        
        # Prefetch related data to optimize queries
        course.sections.prefetch_related('lessons')
        
        # Get next lesson for enrolled students
        next_lesson = None
        if is_enrolled:
            # Get the first incomplete lesson
            enrollment = Enrollment.objects.get(user=request.user, course=course)
            incomplete_lessons = Lesson.objects.filter(
                section__course=course,
                lessonprogress__enrollment=enrollment,
                lessonprogress__completed=False
            ).order_by('section__order', 'order')
            
            if incomplete_lessons.exists():
                next_lesson = incomplete_lessons.first()
            else:
                # If all lessons are complete, get the first lesson
                first_section = course.sections.order_by('order').first()
                if first_section:
                    next_lesson = first_section.lessons.order_by('order').first()
        
        context = {
            'course': course,
            'is_enrolled': is_enrolled,
            'is_teacher': is_teacher,
            'total_students': total_students,
            'average_rating': round(average_rating, 1),
            'reviews': reviews,
            'user_review': user_review,
            'next_lesson': next_lesson,
        }
        
        return render(request, 'accounts/course_detail.html', context)
        
    except Exception as e:
        messages.error(request, f"Error loading course: {str(e)}")
        return redirect('courses')

@login_required
def enroll_course(request, course_id):
    """View to enroll in a course"""
    course = get_object_or_404(Course, id=course_id, is_published=True)
    
    # Check if already enrolled
    if Enrollment.objects.filter(user=request.user, course=course).exists():
        messages.info(request, 'You are already enrolled in this course.')
    else:
        Enrollment.objects.create(user=request.user, course=course)
        messages.success(request, f'You have successfully enrolled in {course.title}!')
    
    return redirect('course_detail', course_id=course.id)

@login_required
def create_course(request):
    """View to create a new course"""
    if not request.user.userprofile.is_teacher:
        messages.error(request, 'Only teachers can create courses.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = CourseForm(request.POST, request.FILES)
        if form.is_valid():
            course = form.save(commit=False)
            course.teacher = request.user
            course.save()
            messages.success(request, 'Your course has been created successfully!')
            return redirect('course_detail', course_id=course.id)
    else:
        form = CourseForm()
    
    context = {'form': form}
    return render(request, 'accounts/create_course.html', context)

@login_required
def edit_course(request, course_id):
    """View to edit a course"""
    course = get_object_or_404(Course, id=course_id, teacher=request.user)
    
    if request.method == 'POST':
        form = CourseForm(request.POST, request.FILES, instance=course)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your course has been updated successfully!')
            return redirect('course_detail', course_id=course.id)
    else:
        form = CourseForm(instance=course)
    
    context = {'form': form, 'course': course}
    return render(request, 'accounts/edit_course.html', context)

@login_required
def submit_review(request, course_id):
    """View to submit a course review"""
    course = get_object_or_404(Course, id=course_id)
    
    # Verify user is enrolled and not the teacher
    if not Enrollment.objects.filter(user=request.user, course=course).exists() or request.user == course.teacher:
        messages.error(request, 'You cannot review this course.')
        return redirect('course_detail', course_id=course.id)
    
    if request.method == 'POST':
        rating = request.POST.get('rating')
        comment = request.POST.get('comment', '')
        
        # Validate rating
        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                raise ValueError
        except (ValueError, TypeError):
            messages.error(request, 'Please provide a valid rating between 1 and 5.')
            return redirect('course_detail', course_id=course.id)
        
        # Create or update review
        review, created = Review.objects.update_or_create(
            user=request.user,
            course=course,
            defaults={'rating': rating, 'comment': comment}
        )
        
        if created:
            messages.success(request, 'Your review has been submitted successfully!')
        else:
            messages.success(request, 'Your review has been updated successfully!')
    
    return redirect('course_detail', course_id=course.id)

# Messaging views
@login_required
def user_messages(request):
    conversations = Conversation.objects.filter(participants=request.user).order_by('-updated_at')
    active_conversation = None
    conversation_messages = []
    
    if 'conversation' in request.GET:
        conversation_id = request.GET.get('conversation')
        active_conversation = get_object_or_404(Conversation, id=conversation_id)
        if request.user in active_conversation.participants.all():
            conversation_messages = active_conversation.messages.exclude(
                deleted_by=request.user
            ).order_by('created_at')
    
    context = {
        'conversations': conversations,
        'active_conversation': active_conversation,
        'conversation_messages': conversation_messages
    }
    
    return render(request, 'accounts/messages.html', context)

@login_required
def new_conversation(request):
    """View to start a new conversation"""
    if request.method == 'POST':
        recipient_id = request.POST.get('recipient')
        message_content = request.POST.get('message')
        
        try:
            recipient = User.objects.get(id=recipient_id)
            
            # Check if conversation already exists
            conversations = request.user.conversations.all()
            for conv in conversations:
                participants = conv.participants.all()
                if participants.count() == 2 and recipient in participants:
                    conversation = conv
                    break
            else:
                # Create new conversation
                conversation = Conversation.objects.create()
                conversation.participants.add(request.user, recipient)
            
            # Create message
            if message_content:
                Message.objects.create(
                    conversation=conversation,
                    sender=request.user,
                    content=message_content
                )
            
            return redirect('messages')
        except User.DoesNotExist:
            messages.error(request, 'Invalid recipient selected.')
    
    return redirect('messages')

@login_required
def send_message(request, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id)
    if request.user not in conversation.participants.all():
        return JsonResponse({'success': False, 'error': 'Not authorized'})
    
    if request.method == 'POST':
        content = request.POST.get('content', '')
        file = request.FILES.get('file')
        
        if not content and not file:
            return JsonResponse({'success': False, 'error': 'Message cannot be empty'})
        
        message_type = 'text'
        if file:
            # Determine message type based on file
            content_type = file.content_type.split('/')[0]
            if content_type == 'image':
                message_type = 'image'
            elif content_type == 'video':
                message_type = 'video'
            elif content_type == 'audio':
                message_type = 'audio'
            else:
                message_type = 'document'
        
            message = Message.objects.create(
                conversation=conversation,
                sender=request.user,
                content=content,
                message_type=message_type,
                file=file
            )
            
        # Mark all previous messages as read
        conversation.messages.filter(sender=conversation.other_user(request.user)).update(is_read=True)
            
        return JsonResponse({
            'success': True,
            'message': {
                'id': message.id,
                'content': message.content,
                'message_type': message.message_type,
                'file_url': message.file.url if message.file else None,
                'created_at': message.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'sender': request.user.username
            }
        })
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def forward_message(request, message_id):
    message = get_object_or_404(Message, id=message_id)
    if request.user not in message.conversation.participants.all():
        return JsonResponse({'success': False, 'error': 'Not authorized'})
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            conversation_id = data.get('conversation_id')
            to_conversation = get_object_or_404(Conversation, id=conversation_id)
            
            if request.user not in to_conversation.participants.all():
                return JsonResponse({'success': False, 'error': 'Not authorized'})
            
            # Forward the message
            forwarded_message = message.forward(to_conversation, request.user)
            
            return JsonResponse({
                'success': True,
                'message': {
                    'id': forwarded_message.id,
                    'content': forwarded_message.content,
                    'message_type': forwarded_message.message_type,
                    'file_url': forwarded_message.file.url if forwarded_message.file else None,
                    'created_at': forwarded_message.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'sender': request.user.username
                }
            })
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def delete_message(request, message_id):
    message = get_object_or_404(Message, id=message_id)
    if request.user not in message.conversation.participants.all():
        return JsonResponse({'success': False, 'error': 'Not authorized'})
    
    if request.method == 'POST':
        message.delete_for_user(request.user)
        return JsonResponse({'success': True})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def check_new_messages(request, conversation_id):
    """AJAX view to check for new messages"""
    conversation = get_object_or_404(Conversation, id=conversation_id)
    if request.user not in conversation.participants.all():
        return JsonResponse({'success': False, 'error': 'Not authorized'})
    
    last_message_id = request.GET.get('last_message_id')
    if not last_message_id:
        return JsonResponse({'success': False, 'error': 'No last message ID provided'})
    
    # Get new messages
    new_messages = conversation.messages.filter(
        id__gt=last_message_id
    ).exclude(
        deleted_by=request.user
    ).order_by('created_at')
    
    # Mark messages as read if they're from the other user
    new_messages.filter(sender=conversation.get_other_participant(request.user)).update(is_read=True)
    
    messages_data = [{
        'id': message.id,
        'content': message.content,
        'message_type': message.message_type,
        'file_url': message.file.url if message.file else None,
        'created_at': message.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'sender': message.sender.username,
        'is_read': message.is_read,
        'is_forwarded': message.is_forwarded
    } for message in new_messages]
    
    return JsonResponse({
        'success': True,
        'messages': messages_data
    })

@login_required
def typing_status(request, conversation_id):
    """AJAX view to update typing status"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    conversation = get_object_or_404(Conversation, id=conversation_id)
    if request.user not in conversation.participants.all():
        return JsonResponse({'success': False, 'error': 'Not authorized'})
    
    try:
        data = json.loads(request.body)
        is_typing = data.get('is_typing', False)
        
        # Update the conversation's typing status
        # This could be stored in cache or a separate model if needed
        # For now, we'll just return success
        return JsonResponse({'success': True})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
