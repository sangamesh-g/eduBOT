import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
from django.db.models import Avg, Count
from .models import Course, Student, Enrollment, Review, LessonProgress

class CourseRecommender:
    """
    AI-powered course recommendation engine that uses collaborative filtering
    and content-based filtering to provide personalized suggestions.
    """
    
    def __init__(self):
        self.vectorizer = TfidfVectorizer(stop_words='english')
        self.course_vectors = None
        self.courses = None
        self.user_vectors = {}
        self.similarity_matrix = None
    
    def fit(self):
        """Load and fit the model with current course data"""
        # Get all active courses
        self.courses = Course.objects.filter(is_published=True)
        
        if not self.courses.exists():
            return False
        
        # Create content features
        course_texts = []
        for course in self.courses:
            # Combine relevant text fields for content-based analysis
            text = f"{course.title} {course.description} {course.prerequisites} {course.category.name}"
            text = text.lower()
            course_texts.append(text)
        
        # Generate TF-IDF vectors for course content
        try:
            self.course_vectors = self.vectorizer.fit_transform(course_texts)
            # Calculate similarity matrix between courses
            self.similarity_matrix = cosine_similarity(self.course_vectors)
            return True
        except Exception as e:
            print(f"Error fitting recommendation model: {e}")
            return False
    
    def _get_user_vector(self, student):
        """Generate a user vector based on their interests and past enrollments"""
        if student.id in self.user_vectors:
            return self.user_vectors[student.id]
        
        # Get student enrollments and calculate progress-weighted ratings
        enrollments = Enrollment.objects.filter(user=student.user)
        
        if not enrollments.exists():
            # If no enrollments, use student interests
            if student.interests:
                interests_vector = self.vectorizer.transform([student.interests.lower()])
                self.user_vectors[student.id] = interests_vector
                return interests_vector
            return None
        
        # Build weighted course preference vector
        user_prefs = {}
        for enrollment in enrollments:
            course_id = enrollment.course.id
            # Calculate an implicit rating based on progress, completion, and reviews
            progress_weight = enrollment.progress / 100.0
            completion_bonus = 0.5 if enrollment.completed else 0
            
            # Check if user has reviewed the course
            try:
                review = Review.objects.get(user=student.user, course=enrollment.course)
                rating = review.rating / 5.0  # Normalize to 0-1
            except Review.DoesNotExist:
                rating = 0.5  # Default neutral rating
            
            # Combine factors for weighted preference
            user_prefs[course_id] = (progress_weight + completion_bonus + rating) / 3.0
        
        return user_prefs
    
    def _get_similar_courses(self, course_id, n=5):
        """Find most similar courses to a given course"""
        course_idx = None
        for i, course in enumerate(self.courses):
            if course.id == course_id:
                course_idx = i
                break
        
        if course_idx is None:
            return []
        
        # Get similarity scores for this course against all others
        similarity_scores = list(enumerate(self.similarity_matrix[course_idx]))
        # Sort by similarity, exclude the course itself
        similarity_scores = sorted(
            [s for s in similarity_scores if s[0] != course_idx],
            key=lambda x: x[1], 
            reverse=True
        )
        
        # Return top N similar courses
        similar_courses = []
        for idx, score in similarity_scores[:n]:
            similar_courses.append((self.courses[idx], score))
        
        return similar_courses
    
    def recommend_for_student(self, student, n=5):
        """Generate personalized recommendations for a student"""
        if not self.courses or not self.similarity_matrix:
            if not self.fit():
                return []
        
        # Get student's existing enrollments to exclude from recommendations
        enrolled_course_ids = set(
            Enrollment.objects.filter(user=student.user).values_list('course_id', flat=True)
        )
        
        # Approach 1: Content-based filtering based on student interests
        recommended_courses = []
        
        if student.interests:
            # Convert interests to vector
            interests_vector = self.vectorizer.transform([student.interests.lower()])
            
            # Calculate similarity with all courses
            similarity_scores = cosine_similarity(interests_vector, self.course_vectors).flatten()
            
            # Sort courses by similarity
            course_scores = list(zip(self.courses, similarity_scores))
            course_scores = sorted(course_scores, key=lambda x: x[1], reverse=True)
            
            # Filter out already enrolled courses
            recommended_courses = [
                (course, score) for course, score in course_scores 
                if course.id not in enrolled_course_ids
            ][:n]
        
        # Approach 2: Collaborative filtering based on similar users
        if not recommended_courses and enrolled_course_ids:
            # Find students with similar enrollment patterns
            similar_students = Student.objects.filter(
                user__enrollments__course_id__in=enrolled_course_ids
            ).annotate(
                common_courses=Count('user__enrollments__course_id', 
                                    filter=models.Q(user__enrollments__course_id__in=enrolled_course_ids))
            ).filter(
                common_courses__gt=0
            ).exclude(
                user=student.user
            ).order_by('-common_courses')[:10]
            
            # Get courses these similar students are enrolled in
            potential_courses = {}
            for similar_student in similar_students:
                sim_enrollments = Enrollment.objects.filter(
                    user=similar_student.user
                ).exclude(
                    course_id__in=enrolled_course_ids
                )
                
                for enrollment in sim_enrollments:
                    if enrollment.course_id in potential_courses:
                        potential_courses[enrollment.course_id][0] += 1
                    else:
                        # Store as (count, course object)
                        potential_courses[enrollment.course_id] = [1, enrollment.course]
            
            # Get top N recommended courses
            course_list = sorted(
                [(count, course) for course_id, (count, course) in potential_courses.items()],
                key=lambda x: x[0], 
                reverse=True
            )[:n]
            
            recommended_courses = [(course, count/10) for count, course in course_list]
        
        # Approach 3: Fallback to popular courses if no recommendations
        if not recommended_courses:
            popular_courses = Course.objects.filter(
                is_published=True
            ).exclude(
                id__in=enrolled_course_ids
            ).annotate(
                student_count=Count('enrollments')
            ).order_by('-student_count')[:n]
            
            recommended_courses = [(course, 0.5) for course in popular_courses]
        
        return recommended_courses
    
    def get_personalized_recommendations(self, student, n=5):
        """Public method to get recommendations with metadata"""
        recommendations = self.recommend_for_student(student, n)
        
        results = []
        for course, score in recommendations:
            # Get additional metadata for the course
            course_data = {
                'course': course,
                'relevance_score': score,
                'student_count': Enrollment.objects.filter(course=course).count(),
                'avg_rating': Review.objects.filter(course=course).aggregate(Avg('rating'))['rating__avg'] or 0,
                'match_reason': self._get_match_reason(student, course, score)
            }
            results.append(course_data)
        
        return results
    
    def _get_match_reason(self, student, course, score):
        """Generate a human-readable explanation for why this course was recommended"""
        if score > 0.8:
            return "Perfectly matches your interests"
        elif score > 0.6:
            return "Highly relevant to your learning goals"
        elif score > 0.4:
            return "Popular among students like you"
        elif score > 0.2:
            return "Complements your current courses"
        else:
            return "Trending in this category"


# Singleton instance for use across the application
recommender = CourseRecommender() 