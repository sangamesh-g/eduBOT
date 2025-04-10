from django.contrib import admin
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

@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
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
        })
    )
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['lesson'].widget.can_add_related = False
        return form

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

class PlacementTestChoiceInline(admin.TabularInline):
    model = PlacementTestChoice
    extra = 4
    min_num = 4
    max_num = 4

class PlacementTestQuestionInline(admin.TabularInline):
    model = PlacementTestQuestion
    extra = 1
    inlines = [PlacementTestChoiceInline]

@admin.register(PlacementTest)
class PlacementTestAdmin(admin.ModelAdmin):
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
        })
    )

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
    inlines = [PlacementTestChoiceInline]

@admin.register(PlacementTestChoice)
class PlacementTestChoiceAdmin(admin.ModelAdmin):
    list_display = ('text', 'question', 'is_correct', 'order')
    list_filter = ('question__test', 'is_correct')
    search_fields = ('text', 'question__text')
