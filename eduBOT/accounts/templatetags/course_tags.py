from django import template
from itertools import chain

register = template.Library()

@register.filter
def join_sections_lessons(sections):
    """
    Joins all lessons from all sections into a single list.
    This is useful for displaying all lessons in a course regardless of section.
    
    Usage:
    {% for lesson in course.sections.all|join_sections_lessons %}
       {{ lesson.title }}
    {% endfor %}
    """
    if not sections:
        return []
    
    # Extract all lessons from all sections
    all_lessons = []
    for section in sections:
        lessons = section.lessons.all()
        all_lessons.extend(lessons)
    
    return all_lessons 