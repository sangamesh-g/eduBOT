from django.contrib import admin
from .models import Group, GroupMembership, GroupJoinRequest, GroupMessage


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "teacher", "members_count", "created_at")
    search_fields = ("name", "teacher__username", "teacher__email")


@admin.register(GroupMembership)
class GroupMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "group", "role", "joined_at")
    list_filter = ("role", "group")
    search_fields = ("user__username", "group__name")


@admin.register(GroupJoinRequest)
class GroupJoinRequestAdmin(admin.ModelAdmin):
    list_display = ("group", "student", "status", "created_at", "processed_at")
    list_filter = ("status", "group")
    search_fields = ("student__username", "group__name")


@admin.register(GroupMessage)
class GroupMessageAdmin(admin.ModelAdmin):
    list_display = ("group", "sender", "message_type", "created_at")
    list_filter = ("message_type", "group")
    search_fields = ("content",)

