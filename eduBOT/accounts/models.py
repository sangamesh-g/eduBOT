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

class Conversation(models.Model):
    participants = models.ManyToManyField(User, related_name="conversations")
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Conversation {self.id}"
    
    def get_other_participant(self, user):
        """Get the other participant in a conversation"""
        return self.participants.exclude(id=user.id).first()
    
    def other_user(self, user):
        """Legacy method for compatibility"""
        other = self.participants.exclude(id=user.id).first()
        return other if other else None  # Ensure it returns None instead of an empty string or other non-user object

class Message(models.Model):
    MESSAGE_TYPES = (
        ('text', 'Text'),
        ('image', 'Image'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('document', 'Document'),
    )
    
    conversation = models.ForeignKey('Conversation', on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    content = models.TextField(blank=True)
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPES, default='text')
    file = models.FileField(upload_to=get_message_file_path, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    is_forwarded = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    deleted_by = models.ManyToManyField(User, related_name='deleted_messages', blank=True)
    
    def __str__(self):
        return f"Message {self.id} from {self.sender.username}"
    
    def delete_for_user(self, user):
        """Mark message as deleted for a user"""
        self.deleted_by.add(user)
        self.save()
    
    def forward(self, to_conversation, user):
        """Forward this message to another conversation"""
        forwarded = Message.objects.create(
            conversation=to_conversation,
            sender=user,
            content=self.content,
            message_type=self.message_type,
            is_forwarded=True
        )
        
        # If there's a file, copy it
        if self.file:
            forwarded.file = self.file
            forwarded.save()
            
        return forwarded

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
