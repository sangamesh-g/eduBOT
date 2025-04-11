from django.db import models
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Avg, Count
from django.utils.translation import gettext_lazy as _
import os
import pandas as pd
import uuid
import re

User = get_user_model()

class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

class Course(models.Model):
    LEVEL_CHOICES = (
        ('basic', 'Basic'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    )
    
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='courses')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='courses')
    thumbnail = models.ImageField(upload_to='course_thumbnails/', null=True, blank=True)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='basic')
    duration = models.PositiveIntegerField(help_text="Duration in minutes")
    prerequisites = models.TextField(blank=True)
    programming_languages = models.CharField(max_length=200, blank=True, help_text="Comma-separated list of programming languages covered in this course")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_published = models.BooleanField(default=False)
    
    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Ensure slug is created if not provided
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)
    
    @property
    def is_visible(self):
        """Check if course should be visible in catalog"""
        return self.is_published
    
    class Meta:
        ordering = ['-created_at']

class Section(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='sections')
    title = models.CharField(max_length=200)
    order = models.PositiveIntegerField()
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"

class Lesson(models.Model):
    CONTENT_TYPE_CHOICES = (
        ('video', 'Video'),
        ('text', 'Text'),
        ('quiz', 'Quiz'),
        ('assignment', 'Assignment'),
        ('programming', 'Programming Exercise'),
    )
    
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=200)
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES)
    content = models.TextField()
    video_url = models.TextField(
        blank=True, 
        help_text="Paste the embedded video code here (iframe). Example: &lt;iframe src='...'&gt;&lt;/iframe&gt;"
    )
    order = models.PositiveIntegerField()
    duration = models.PositiveIntegerField(help_text="Duration in minutes", default=0)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"{self.section.course.title} - {self.section.title} - {self.title}"
    
    def get_video_embed(self):
        """Returns the video embed code if it's a valid iframe, otherwise returns None"""
        if self.content_type == 'video' and self.video_url:
            # Basic security check for iframe
            if re.match(r'^\s*<iframe[^>]*src=["\']https?://[^"\']+["\'][^>]*>\s*</iframe>\s*$', self.video_url, re.I):
                return self.video_url
        return None

    def clean(self):
        if self.content_type == 'video' and self.video_url:
            if not self.get_video_embed():
                raise ValidationError({
                    'video_url': 'Invalid iframe code. Please enter a valid embedded video code.'
                })

class Enrollment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    date_enrolled = models.DateTimeField(auto_now_add=True)
    progress = models.PositiveIntegerField(default=0)
    last_accessed = models.DateTimeField(auto_now=True)
    completed = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('user', 'course')
    
    def __str__(self):
        return f"{self.user.username} enrolled in {self.course.title}"

class LessonProgress(models.Model):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='lesson_progress')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE)
    completed = models.BooleanField(default=False)
    last_accessed = models.DateTimeField(auto_now=True)
    time_spent = models.PositiveIntegerField(default=0, help_text="Time spent in minutes")
    
    class Meta:
        unique_together = ('enrollment', 'lesson')
    
    def __str__(self):
        return f"{self.enrollment.user.username}'s progress in {self.lesson.title}"

class Review(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveIntegerField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'course')
    
    def __str__(self):
        return f"{self.user.username}'s review of {self.course.title}"

class QuizDifficulty(models.TextChoices):
    EASY = 'easy', 'Easy'
    MEDIUM = 'medium', 'Medium'
    HARD = 'hard', 'Hard'

class Quiz(models.Model):
    """Quiz associated with a lesson"""
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, related_name='quiz')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    time_limit = models.PositiveIntegerField(help_text="Time limit in minutes", default=10)
    passing_percentage = models.PositiveIntegerField(
        default=75,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Minimum percentage required to pass"
    )
    difficulty = models.CharField(
        max_length=20, 
        choices=QuizDifficulty.choices,
        default=QuizDifficulty.MEDIUM
    )
    prevent_tab_switch = models.BooleanField(default=True, help_text="Prevent tab switching during quiz")
    randomize_questions = models.BooleanField(default=True)
    randomize_choices = models.BooleanField(default=True)
    show_result_immediately = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Quiz for {self.lesson.title}"
    
    @property
    def total_marks(self):
        return sum(question.marks for question in self.questions.all())
    
    @property
    def passing_score(self):
        return (self.passing_percentage / 100) * self.total_marks
    
    def import_questions_from_excel(self, excel_file):
        """Import questions from Excel file"""
        try:
            df = pd.read_excel(excel_file)
            required_columns = ['question', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_answer', 'time', 'marks']
            
            if not all(col in df.columns for col in required_columns):
                missing = [col for col in required_columns if col not in df.columns]
                raise ValueError(f"Missing required columns: {', '.join(missing)}")
            
            # Process each row
            for _, row in df.iterrows():
                # Create question
                question = Question.objects.create(
                    quiz=self,
                    text=row['question'],
                    time_seconds=int(row['time']),
                    marks=float(row['marks'])
                )
                
                # Create choices
                choices = [
                    Choice(question=question, text=row['option_a'], is_correct=(row['correct_answer'].lower() == 'a')),
                    Choice(question=question, text=row['option_b'], is_correct=(row['correct_answer'].lower() == 'b')),
                    Choice(question=question, text=row['option_c'], is_correct=(row['correct_answer'].lower() == 'c')),
                    Choice(question=question, text=row['option_d'], is_correct=(row['correct_answer'].lower() == 'd'))
                ]
                Choice.objects.bulk_create(choices)
                
            return True, f"Successfully imported {len(df)} questions"
        except Exception as e:
            return False, f"Error importing questions: {str(e)}"

class Question(models.Model):
    """Question for a quiz"""
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField()
    image = models.ImageField(upload_to='quiz_questions/', blank=True, null=True)
    time_seconds = models.PositiveIntegerField(default=60, help_text="Time in seconds to answer")
    marks = models.FloatField(default=1.0)
    explanation = models.TextField(blank=True, help_text="Explanation for the correct answer")
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"Question {self.order}: {self.text[:50]}..."

class Choice(models.Model):
    """Answer choice for a question"""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)
    
    def __str__(self):
        return self.text[:50]

class QuizAttempt(models.Model):
    """Record of a student's attempt at a quiz"""
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quiz_attempts')
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)
    passed = models.BooleanField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    tab_switches = models.PositiveIntegerField(default=0)
    # Generate a unique session ID to track the attempt
    session_id = models.UUIDField(default=uuid.uuid4, editable=False)
    
    def __str__(self):
        return f"Attempt by {self.student.username} on {self.quiz.title}"
    
    @property
    def time_taken(self):
        if not self.end_time:
            return None
        return (self.end_time - self.start_time).total_seconds() / 60
    
    @property
    def percentage_score(self):
        if self.score is None or self.quiz.total_marks == 0:
            return 0
        return (self.score / self.quiz.total_marks) * 100
    
    def calculate_score(self):
        """Calculate the score based on submitted answers"""
        score = 0
        for answer in self.answers.all():
            if answer.selected_choice and answer.selected_choice.is_correct:
                score += answer.question.marks
        
        self.score = score
        self.passed = self.percentage_score >= self.quiz.passing_percentage
        self.end_time = timezone.now()
        self.save()
        return self.score

class Answer(models.Model):
    """Student's answer to a question"""
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_choice = models.ForeignKey(Choice, on_delete=models.CASCADE, null=True, blank=True)
    time_taken = models.PositiveIntegerField(help_text="Time taken in seconds", null=True, blank=True)
    
    class Meta:
        unique_together = ('attempt', 'question')
    
    def __str__(self):
        return f"Answer for {self.question}"
    
    @property
    def is_correct(self):
        if not self.selected_choice:
            return False
        return self.selected_choice.is_correct

class StudentAnalytics(models.Model):
    """Analytics data for student performance"""
    student_profile = models.OneToOneField('accounts.StudentProfile', on_delete=models.CASCADE, related_name='analytics')
    total_quizzes_taken = models.PositiveIntegerField(default=0)
    total_quizzes_passed = models.PositiveIntegerField(default=0)
    average_score = models.FloatField(default=0)
    total_time_spent = models.PositiveIntegerField(default=0, help_text="Total time spent on quizzes in minutes")
    
    def __str__(self):
        return f"Analytics for {self.student_profile.user.username}"
    
    def update_statistics(self):
        """Update the analytics based on all quiz attempts"""
        attempts = QuizAttempt.objects.filter(student=self.student_profile.user, end_time__isnull=False)
        
        self.total_quizzes_taken = attempts.count()
        self.total_quizzes_passed = attempts.filter(passed=True).count()
        
        if self.total_quizzes_taken > 0:
            self.average_score = attempts.aggregate(Avg('score'))['score__avg'] or 0
            
            # Calculate total time spent
            total_seconds = 0
            for attempt in attempts:
                if attempt.time_taken:
                    total_seconds += attempt.time_taken * 60
            
            self.total_time_spent = total_seconds // 60
        
        self.save()

class PlacementTest(models.Model):
    """Model for placement tests that determine course level"""
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='placement_tests')
    time_limit = models.PositiveIntegerField(help_text="Time limit in minutes", default=30)
    passing_percentage = models.PositiveIntegerField(
        default=60,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Minimum percentage required to pass"
    )
    basic_cutoff = models.PositiveIntegerField(
        default=7,
        help_text="Score below which basic course is recommended"
    )
    intermediate_cutoff = models.PositiveIntegerField(
        default=15,
        help_text="Score below which intermediate course is recommended"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.title

class PlacementTestQuestion(models.Model):
    """Questions for placement tests"""
    test = models.ForeignKey(PlacementTest, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField()
    image = models.ImageField(blank=True, null=True, upload_to='placement_test_questions/')
    marks = models.FloatField(default=1.0)
    explanation = models.TextField(blank=True, help_text='Explanation for the correct answer')
    order = models.PositiveIntegerField(default=0)
    
    # New fields to store choices directly
    choice_text_1 = models.TextField(blank=True, null=True)
    choice_text_2 = models.TextField(blank=True, null=True)
    choice_text_3 = models.TextField(blank=True, null=True) 
    choice_text_4 = models.TextField(blank=True, null=True)
    correct_choice = models.IntegerField(choices=[(1, '1'), (2, '2'), (3, '3'), (4, '4')], null=True, blank=True)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return self.text
        
    @property
    def choices(self):
        """Return choices in a format compatible with existing code"""
        choices = []
        
        # Check if we are using the old or new choice system
        old_choices = PlacementTestChoice.objects.filter(question=self)
        if old_choices.exists():
            return old_choices
            
        # Use new choice fields
        if self.choice_text_1:
            choices.append({
                'id': 1,
                'text': self.choice_text_1,
                'is_correct': self.correct_choice == 1,
                'order': 1
            })
        if self.choice_text_2:
            choices.append({
                'id': 2,
                'text': self.choice_text_2,
                'is_correct': self.correct_choice == 2,
                'order': 2
            })
        if self.choice_text_3:
            choices.append({
                'id': 3,
                'text': self.choice_text_3,
                'is_correct': self.correct_choice == 3,
                'order': 3
            })
        if self.choice_text_4:
            choices.append({
                'id': 4,
                'text': self.choice_text_4,
                'is_correct': self.correct_choice == 4,
                'order': 4
            })
        
        # Convert to objects that mimic PlacementTestChoice objects
        choice_objects = []
        for choice in choices:
            obj = type('PlacementTestChoiceProxy', (), {})()
            obj.id = choice['id']
            obj.text = choice['text']
            obj.is_correct = choice['is_correct']
            obj.order = choice['order']
            choice_objects.append(obj)
            
        return choice_objects

# Keep for data migration purposes but mark as deprecated
class PlacementTestChoice(models.Model):
    """Choices for placement test questions (DEPRECATED)"""
    question = models.ForeignKey(PlacementTestQuestion, on_delete=models.CASCADE, related_name='old_choices')
    text = models.TextField()
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return self.text

class PlacementTestAttempt(models.Model):
    """Student's attempt at a placement test"""
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='placement_test_attempts')
    test = models.ForeignKey(PlacementTest, on_delete=models.CASCADE, related_name='attempts')
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(blank=True, null=True)
    score = models.FloatField(blank=True, null=True)
    recommended_level = models.CharField(max_length=20, choices=Course.LEVEL_CHOICES, blank=True)
    completed = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.student.username}'s attempt at {self.test.title}"
    
    def calculate_score(self):
        """Calculate the score and determine recommended level"""
        answers = self.answers.filter(choice__is_correct=True)
        total_marks = sum(answer.question.marks for answer in answers)
        
        self.score = total_marks
        if total_marks < self.test.basic_cutoff:
            self.recommended_level = 'basic'
        elif total_marks < self.test.intermediate_cutoff:
            self.recommended_level = 'medium'
        else:
            self.recommended_level = 'hard'
        
        self.completed = True
        self.save()
        return self.recommended_level

class PlacementTestAnswer(models.Model):
    """Student's answer to a placement test question"""
    attempt = models.ForeignKey(PlacementTestAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(PlacementTestQuestion, on_delete=models.CASCADE)
    choice_number = models.IntegerField(choices=[(1, '1'), (2, '2'), (3, '3'), (4, '4')], default=1)
    
    class Meta:
        unique_together = ('attempt', 'question')
    
    def __str__(self):
        return f"Answer for {self.question.text[:50]}"
