from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid

User = get_user_model()


def group_message_file_path(instance, filename):
    """Return a unique upload path for message attachments within a group."""
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    unique_name = f"{uuid.uuid4().hex}{('.' + ext) if ext else ''}"
    now = timezone.now()
    return f"group_messages/{instance.group.id}/{now.strftime('%Y-%m')}/{unique_name}"


class Group(models.Model):
    """A chat group owned by a teacher. Students can join by approval."""
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name="owned_groups")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name}"

    @property
    def members_count(self) -> int:
        return self.memberships.count()


class GroupMembership(models.Model):
    """Membership relation with role control."""
    ROLE_CHOICES = (
        ("teacher", "Teacher"),
        ("student", "Student"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="group_memberships")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="student")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "group")
        ordering = ["-joined_at"]

    def __str__(self) -> str:
        return f"{self.user.username} in {self.group.name} ({self.role})"

    @property
    def is_teacher(self) -> bool:
        return self.role == "teacher"


class GroupJoinRequest(models.Model):
    """Student requests to join a group. Approved by the group's teacher."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STATUS_CHOICES = (
        (PENDING, "Pending"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
    )

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="join_requests")
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="group_join_requests")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    message = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("group", "student")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.student.username} -> {self.group.name} ({self.status})"


class GroupMessage(models.Model):
    """A message inside a group. Supports text and attachments."""
    MESSAGE_TYPES = (
        ("text", "Text"),
        ("image", "Image"),
        ("video", "Video"),
        ("audio", "Audio"),
        ("file", "File"),
    )

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="group_messages")
    content = models.TextField(blank=True)
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPES, default="text")
    attachment = models.FileField(upload_to=group_message_file_path, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.sender.username}: {self.content[:30]}"

    @staticmethod
    def detect_type_for_upload(uploaded_file) -> str:
        if not uploaded_file:
            return "text"
        main = uploaded_file.content_type.split("/")[0]
        if main in {"image", "video", "audio"}:
            return main
        return "file"


# Create your models here.
