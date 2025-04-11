from django.contrib import admin
from django import forms
from django.core.exceptions import ValidationError
from django.utils.html import mark_safe
from .models import (
    Quiz, Question, Choice, QuizAttempt, Answer, StudentAnalytics,
    Course, Category, Section, Lesson, Enrollment, LessonProgress, Review,
    PlacementTest, PlacementTestChoice, PlacementTestQuestion, PlacementTestAttempt
)

class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 4
    min_num = 2

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('text', 'quiz', 'marks', 'time_seconds', 'order')
    list_filter = ('quiz', 'marks')
    search_fields = ('text', 'quiz__title')
    inlines = [ChoiceInline]

class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1
    show_change_link = True

class QuizAdminForm(forms.ModelForm):
    bulk_questions = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 15, 'cols': 80}),
        required=False,
        help_text=mark_safe(
            """Add multiple questions at once. Use the following format:<br>
            Q: Question text here<br>
            A: Option 1 text [correct]<br>
            B: Option 2 text<br>
            C: Option 3 text<br>
            D: Option 4 text<br>
            MARKS: 2<br>
            TIME: 60<br>
            <br>
            Q: Next question text<br>
            A: Option 1 text<br>
            B: Option 2 text [correct]<br>
            ... and so on.<br>
            <br>
            Mark correct answers with [correct]. MARKS and TIME are optional."""
        )
    )
    
    class Meta:
        model = Quiz
        fields = '__all__'

@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    form = QuizAdminForm
    list_display = ('title', 'lesson', 'difficulty', 'passing_percentage', 'time_limit', 'total_marks')
    list_filter = ('difficulty', 'lesson__section__course')
    search_fields = ('title', 'lesson__title')
    inlines = [QuestionInline]
    
    fieldsets = (
        (None, {
            'fields': ('lesson', 'title', 'description', 'difficulty')
        }),
        ('Settings', {
            'fields': ('time_limit', 'passing_percentage', 'randomize_questions', 'randomize_choices', 'show_result_immediately')
        }),
        ('Security', {
            'fields': ('prevent_tab_switch',),
            'classes': ('collapse',)
        }),
        ('Bulk Add Questions', {
            'fields': ('bulk_questions',),
            'classes': ('wide',)
        })
    )
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['lesson'].widget.can_add_related = False
        return form
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        
        # Process bulk questions if provided
        bulk_questions = form.cleaned_data.get('bulk_questions')
        if bulk_questions:
            questions = []
            choices = []
            current_question = None
            question_order = Question.objects.filter(quiz=obj).count()
            
            lines = bulk_questions.strip().split('\n')
            marks = 1  # Default marks
            time_seconds = 60  # Default time
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if line.startswith('Q:'):
                    # Save previous question if exists
                    if current_question and len(choices) > 0:
                        current_question.save()
                        for choice in choices:
                            choice.question = current_question
                            choice.save()
                    
                    # Create new question
                    question_text = line[2:].strip()
                    question_order += 1
                    current_question = Question(
                        quiz=obj,
                        text=question_text,
                        marks=marks,
                        time_seconds=time_seconds,
                        order=question_order
                    )
                    choices = []
                    marks = 1  # Reset to default
                    time_seconds = 60  # Reset to default
                
                elif line.startswith(('A:', 'B:', 'C:', 'D:', 'E:', 'F:')):
                    if current_question:
                        choice_text = line[2:].strip()
                        is_correct = False
                        
                        if '[correct]' in choice_text:
                            is_correct = True
                            choice_text = choice_text.replace('[correct]', '').strip()
                        
                        choice = Choice(
                            question=current_question,  # This will be updated after question is saved
                            text=choice_text,
                            is_correct=is_correct
                        )
                        choices.append(choice)
                
                elif line.startswith('MARKS:'):
                    marks_str = line[6:].strip()
                    try:
                        marks = float(marks_str)
                    except ValueError:
                        marks = 1
                
                elif line.startswith('TIME:'):
                    time_str = line[5:].strip()
                    try:
                        time_seconds = int(time_str)
                    except ValueError:
                        time_seconds = 60
            
            # Save the last question
            if current_question and len(choices) > 0:
                current_question.save()
                for choice in choices:
                    choice.question = current_question
                    choice.save()

class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    readonly_fields = ('question', 'selected_choice', 'time_taken', 'is_correct')
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False

@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ('student', 'quiz', 'start_time', 'end_time', 'score', 'percentage_score', 'passed', 'tab_switches')
    list_filter = ('passed', 'quiz__lesson__section__course', 'start_time')
    search_fields = ('student__username', 'student__email', 'quiz__title')
    readonly_fields = ('student', 'quiz', 'start_time', 'end_time', 'score', 'passed', 'ip_address', 'user_agent', 'tab_switches', 'session_id', 'percentage_score', 'time_taken')
    inlines = [AnswerInline]
    
    def has_add_permission(self, request):
        return False
        
    def has_change_permission(self, request, obj=None):
        return False

@admin.register(StudentAnalytics)
class StudentAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('student_profile', 'total_quizzes_taken', 'total_quizzes_passed', 'average_score', 'total_time_spent')
    list_filter = ('total_quizzes_passed', 'average_score')
    search_fields = ('student_profile__user__username', 'student_profile__user__email')
    readonly_fields = ('total_quizzes_taken', 'total_quizzes_passed', 'average_score', 'total_time_spent')
    
    def has_add_permission(self, request):
        return False

class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1
    show_change_link = True

class SectionInline(admin.TabularInline):
    model = Section
    extra = 1
    show_change_link = True

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'teacher', 'category', 'level', 'duration', 'is_published')
    list_filter = ('level', 'category', 'is_published')
    search_fields = ('title', 'description', 'teacher__username')
    inlines = [SectionInline]
    prepopulated_fields = {'slug': ('title',)}

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'order')
    list_filter = ('course',)
    search_fields = ('title', 'course__title')
    inlines = [LessonInline]

@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('title', 'section', 'content_type', 'order', 'duration')
    list_filter = ('content_type', 'section__course')
    search_fields = ('title', 'content', 'section__title', 'section__course__title')

@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'date_enrolled', 'progress', 'completed')
    list_filter = ('completed', 'course')
    search_fields = ('user__username', 'user__email', 'course__title')

@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ('enrollment', 'lesson', 'completed', 'last_accessed', 'time_spent')
    list_filter = ('completed', 'lesson__section__course')
    search_fields = ('enrollment__user__username', 'lesson__title')

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'rating', 'created_at')
    list_filter = ('rating', 'course')
    search_fields = ('user__username', 'course__title', 'comment')

class PlacementTestQuestionInline(admin.TabularInline):
    model = PlacementTestQuestion
    extra = 1
    fields = ('text', 'marks', 'order', 'choice_text_1', 'choice_text_2', 'choice_text_3', 'choice_text_4', 'correct_choice')

class PlacementTestAdminForm(forms.ModelForm):
    bulk_questions = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 15, 'cols': 80}),
        required=False,
        help_text=mark_safe(
            """Add multiple questions at once. Use the following format:<br>
            Q: Question text here<br>
            A: Option 1 text [correct]<br>
            B: Option 2 text<br>
            C: Option 3 text<br>
            D: Option 4 text<br>
            MARKS: 1<br>
            <br>
            Q: Next question text<br>
            A: Option 1 text<br>
            B: Option 2 text [correct]<br>
            ... and so on.<br>
            <br>
            Mark correct answers with [correct]. MARKS is optional."""
        )
    )
    
    class Meta:
        model = PlacementTest
        fields = '__all__'

@admin.register(PlacementTest)
class PlacementTestAdmin(admin.ModelAdmin):
    form = PlacementTestAdminForm
    list_display = ('title', 'category', 'time_limit', 'basic_cutoff', 'intermediate_cutoff', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('title', 'description')
    inlines = [PlacementTestQuestionInline]
    
    fieldsets = (
        (None, {
            'fields': ('title', 'description', 'category', 'is_active')
        }),
        ('Settings', {
            'fields': ('time_limit', 'basic_cutoff', 'intermediate_cutoff')
        }),
        ('Bulk Add Questions', {
            'fields': ('bulk_questions',),
            'classes': ('wide',)
        })
    )
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        
        # Process bulk questions if provided
        bulk_questions = form.cleaned_data.get('bulk_questions')
        if bulk_questions:
            question_order = PlacementTestQuestion.objects.filter(test=obj).count()
            
            lines = bulk_questions.strip().split('\n')
            marks = 1  # Default marks
            
            current_question = None
            choices = []
            correct_choice = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if line.startswith('Q:'):
                    # Save previous question if exists
                    if current_question and len(choices) > 0:
                        current_question.choice_text_1 = choices[0]['text'] if len(choices) > 0 else ""
                        current_question.choice_text_2 = choices[1]['text'] if len(choices) > 1 else ""
                        current_question.choice_text_3 = choices[2]['text'] if len(choices) > 2 else ""
                        current_question.choice_text_4 = choices[3]['text'] if len(choices) > 3 else ""
                        current_question.correct_choice = correct_choice
                        current_question.save()
                    
                    # Create new question
                    question_text = line[2:].strip()
                    question_order += 1
                    current_question = PlacementTestQuestion(
                        test=obj,
                        text=question_text,
                        marks=marks,
                        order=question_order
                    )
                    choices = []
                    correct_choice = None
                    marks = 1  # Reset to default
                
                elif line.startswith(('A:', 'B:', 'C:', 'D:')):
                    if current_question:
                        choice_text = line[2:].strip()
                        is_correct = False
                        
                        if '[correct]' in choice_text:
                            is_correct = True
                            choice_text = choice_text.replace('[correct]', '').strip()
                        
                        choice_index = ord(line[0]) - ord('A') + 1  # A=1, B=2, C=3, D=4
                        
                        choices.append({
                            'text': choice_text,
                            'is_correct': is_correct
                        })
                        
                        if is_correct:
                            correct_choice = choice_index
                
                elif line.startswith('MARKS:'):
                    marks_str = line[6:].strip()
                    try:
                        marks = float(marks_str)
                    except ValueError:
                        marks = 1
            
            # Save the last question
            if current_question and len(choices) > 0:
                current_question.choice_text_1 = choices[0]['text'] if len(choices) > 0 else ""
                current_question.choice_text_2 = choices[1]['text'] if len(choices) > 1 else ""
                current_question.choice_text_3 = choices[2]['text'] if len(choices) > 2 else ""
                current_question.choice_text_4 = choices[3]['text'] if len(choices) > 3 else ""
                current_question.correct_choice = correct_choice
                current_question.save()

@admin.register(PlacementTestAttempt)
class PlacementTestAttemptAdmin(admin.ModelAdmin):
    list_display = ('student', 'test', 'score', 'recommended_level', 'completed', 'start_time', 'end_time')
    list_filter = ('test', 'completed', 'recommended_level')
    search_fields = ('student__username', 'test__title')
    readonly_fields = ('start_time', 'end_time', 'score', 'recommended_level')

@admin.register(PlacementTestQuestion)
class PlacementTestQuestionAdmin(admin.ModelAdmin):
    list_display = ('text', 'test', 'marks', 'order')
    list_filter = ('test',)
    search_fields = ('text', 'test__title')
    fields = ('test', 'text', 'marks', 'order', 'choice_text_1', 'choice_text_2', 'choice_text_3', 'choice_text_4', 'correct_choice')
