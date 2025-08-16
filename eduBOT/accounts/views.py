from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.views.decorators.csrf import ensure_csrf_cookie
from django.apps import apps
import json

from .models import TeacherProfile, StudentProfile
from django.contrib.auth.models import User
from courses.models import PlacementTestAttempt
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
    """View for listing courses"""
    try:
        categories = Category.objects.all()
        level_choices = Course.LEVEL_CHOICES
        
        # Get search query
        search_query = request.GET.get('q', '')
        
        # Get category filter
        selected_category = request.GET.get('category', '')
        
        # Get level filter
        level_filter = request.GET.get('level', '')
        
        # Get sort by
        sort_by = request.GET.get('sort_by', '')
        
        # Build queryset
        courses = Course.objects.filter(is_published=True)
        
        # Apply search if provided
        if search_query:
            courses = courses.filter(
                Q(title__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(teacher__username__icontains=search_query)
            )
        
        # Apply category filter if provided
        if selected_category:
            courses = courses.filter(category__slug=selected_category)
        
        # Apply level filter if provided
        if level_filter:
            courses = courses.filter(level=level_filter)
        
        # Apply sorting if provided
        if sort_by == 'price_low':
            courses = courses.order_by('price')
        elif sort_by == 'price_high':
            courses = courses.order_by('-price')
        else:
            # Default sort by newest
            courses = courses.order_by('-created_at')
            
        # Get categories where user has completed placement tests
        placement_categories = []
        if request.user.is_authenticated:
            completed_attempts = PlacementTestAttempt.objects.filter(
                student=request.user,
                completed=True
            )
            placement_categories = [attempt.test.category for attempt in completed_attempts]
            
        # Pagination
        paginator = Paginator(courses, 9)  # 9 courses per page
        page = request.GET.get('page', 1)
        
        try:
            courses = paginator.page(page)
        except PageNotAnInteger:
            courses = paginator.page(1)
        except EmptyPage:
            courses = paginator.page(paginator.num_pages)
        
        context = {
            'courses': courses,
            'total_courses': paginator.count,
            'categories': categories,
            'level_choices': level_choices,
            'search_query': search_query,
            'selected_category': selected_category,
            'level_filter': level_filter,
            'sort_by': sort_by,
            'placement_categories': placement_categories
        }
            
        return render(request, 'accounts/courses.html', context)
        
    except Exception as e:
        return render(request, 'accounts/courses.html', {'courses': [], 'error': str(e)})

@login_required
def course_detail(request, course_id):
    """View for displaying course details"""
    # This function will now use the course_detail view from courses.views
    from courses.views import course_detail as courses_detail_view
    return courses_detail_view(request, course_id)

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

# Messaging views removed in favor of groupchat app
