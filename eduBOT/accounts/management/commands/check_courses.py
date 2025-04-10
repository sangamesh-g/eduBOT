from django.core.management.base import BaseCommand
from accounts.models import Course

class Command(BaseCommand):
    help = 'Check course visibility and status'

    def handle(self, *args, **options):
        courses = Course.objects.all()
        self.stdout.write(f"Total courses: {courses.count()}")
        
        for course in courses:
            self.stdout.write(f"\nCourse: {course.title}")
            self.stdout.write(f"Published: {course.is_published}")
            self.stdout.write(f"Teacher: {course.teacher.username}")
            self.stdout.write(f"Sections: {course.sections.count()}") 