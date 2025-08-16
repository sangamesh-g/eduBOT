from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.apps import apps
from .utils import get_profile_picture_path, get_message_file_path, delete_message_file
import uuid
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

class UserProfile(models.Model):
    """
    Base user profile model that provides a unique ID for all users
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='user_profile')
    unique_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    date_created = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.username}'s ID: {self.unique_id}"

class TeacherProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profile_picture = models.ImageField(upload_to=get_profile_picture_path, null=True, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    specialization = models.CharField(max_length=100, blank=True)
    experience = models.PositiveIntegerField(default=0)
    account_name = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=20, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    ifsc_code = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.user.username}'s Teacher Profile"
    
    @property
    def user_id(self):
        """Get the unique ID associated with this user"""
        profile, created = UserProfile.objects.get_or_create(user=self.user)
        return profile.unique_id

class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profile_picture = models.ImageField(upload_to=get_profile_picture_path, null=True, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    interests = models.CharField(max_length=200, blank=True)
    education_level = models.CharField(max_length=20, blank=True)
    programming_languages = models.CharField(max_length=200, blank=True, help_text="Comma-separated list of programming languages the student knows")
    github_username = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return f"{self.user.username}'s Student Profile"
        
    @property
    def analytics(self):
        """Get or create the student analytics record"""
        StudentAnalytics = apps.get_model('course', 'StudentAnalytics')
        analytics, created = StudentAnalytics.objects.get_or_create(student_profile=self)
        return analytics
    
    @property
    def user_id(self):
        """Get the unique ID associated with this user"""
        profile, created = UserProfile.objects.get_or_create(user=self.user)
        return profile.unique_id
    
    @property
    def skill_level(self):
        """Determine skill level based on assessment scores"""
        assessments = Assessment.objects.filter(student=self.user)
        if not assessments.exists():
            return "Not Assessed"
        
        # Calculate average score
        avg_score = assessments.aggregate(models.Avg('score'))['score__avg']
        
        if avg_score >= 80:
            return "Advanced"
        elif avg_score >= 60:
            return "Intermediate"
        else:
            return "Beginner"
    
    def get_recommended_courses(self, limit=3):
        """Get course recommendations based on skill level and interests"""
        Course = apps.get_model('course', 'Course')
        
        # Get student's skill level
        skill_level = self.skill_level
        
        # Base query
        query = Course.objects.filter(is_published=True)
        
        # Filter by skill level
        if skill_level == "Advanced":
            query = query.filter(level='hard')
        elif skill_level == "Intermediate":
            query = query.filter(level='medium')
        else:
            query = query.filter(level='basic')
        
        # Filter by interests if available
        if self.interests:
            interests = [i.strip().lower() for i in self.interests.split(',')]
            query = query.filter(
                models.Q(title__icontains=interests[0]) |
                models.Q(description__icontains=interests[0])
            )
        
        return query.order_by('?')[:limit]

class Assessment(models.Model):
    """Model to store student assessment results"""
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assessments')
    score = models.PositiveIntegerField(validators=[MinValueValidator(0), MaxValueValidator(100)])
    programming_language = models.CharField(max_length=50)
    date_taken = models.DateTimeField(auto_now_add=True)
    feedback = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-date_taken']
    
    def __str__(self):
        return f"{self.student.username}'s {self.programming_language} assessment"

# Legacy 1:1 messaging removed in favor of groupchat app

# Create signal handlers to generate user profiles automatically
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a UserProfile when a User is created"""
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save the UserProfile when a User is saved"""
    if not hasattr(instance, 'user_profile'):
        UserProfile.objects.create(user=instance)
    instance.user_profile.save()
