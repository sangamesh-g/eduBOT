from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import TeacherProfile, StudentProfile
from courses.models import Course, Category

class UserRegisterForm(UserCreationForm):
    """Form for user registration"""
    email = forms.EmailField()
    first_name = forms.CharField(max_length=30)
    last_name = forms.CharField(max_length=30)
    
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('This email address is already in use.')
        return email


class UserUpdateForm(forms.ModelForm):
    """Form for updating user information"""
    email = forms.EmailField()
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        
        # Check if email exists for another user
        if User.objects.exclude(pk=self.instance.pk).filter(email=email).exists():
            raise forms.ValidationError('This email address is already in use.')
        
        return email


class TeacherProfileUpdateForm(forms.ModelForm):
    """Form for updating teacher profile information"""
    class Meta:
        model = TeacherProfile
        fields = [
            'bio', 'specialization', 'experience',
            'bank_name', 'account_name', 'account_number', 'ifsc_code'
        ]
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 4}),
        }


class StudentProfileUpdateForm(forms.ModelForm):
    """Form for updating student profile information"""
    class Meta:
        model = StudentProfile
        fields = [
            'bio', 'interests', 'education_level'
        ]
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 4}),
        }


class CourseForm(forms.ModelForm):
    """Form for creating and updating courses"""
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        empty_label="Select a category",
        required=True
    )
    
    class Meta:
        model = Course
        fields = [
            'title', 'slug', 'description', 'category', 'thumbnail',
            'level', 'duration', 'prerequisites', 'is_published'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
            'prerequisites': forms.Textarea(attrs={'rows': 3}),
            'level': forms.Select(choices=Course.LEVEL_CHOICES),
        }
        
    def clean_slug(self):
        slug = self.cleaned_data.get('slug')
        
        # Check if slug exists for another course
        if 'instance' in self.__dict__ and self.instance:
            if Course.objects.exclude(pk=self.instance.pk).filter(slug=slug).exists():
                raise forms.ValidationError('This slug is already in use. Please choose a different one.')
        else:
            if Course.objects.filter(slug=slug).exists():
                raise forms.ValidationError('This slug is already in use. Please choose a different one.')
        
        return slug