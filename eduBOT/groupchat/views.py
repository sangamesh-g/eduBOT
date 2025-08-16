from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.db.models import Q
from django.contrib.auth import get_user_model

from .models import Group, GroupMembership, GroupJoinRequest, GroupMessage


def _user_is_group_teacher(user, group: Group) -> bool:
    return group.teacher_id == user.id


def _ensure_teacher_membership(group: Group):
    """Ensure the teacher is present as a membership with role=teacher."""
    GroupMembership.objects.get_or_create(group=group, user=group.teacher, defaults={"role": "teacher"})


@login_required
def list_groups(request):
    """Show groups user belongs to and groups they can request to join."""
    my_memberships = GroupMembership.objects.filter(user=request.user).select_related("group")
    my_groups = [m.group for m in my_memberships]
    owned_groups = Group.objects.filter(teacher=request.user)
    # Ensure owned groups appear in "My Groups" for teachers as well
    my_groups_ids = {g.id for g in my_groups}
    for og in owned_groups:
        if og.id not in my_groups_ids:
            my_groups.append(og)
            my_groups_ids.add(og.id)
    discover_groups = Group.objects.exclude(id__in=my_groups_ids)

    context = {
        "my_groups": my_groups,
        "owned_groups": owned_groups,
        "discover_groups": discover_groups,
    }
    return render(request, "groupchat/groups.html", context)


@login_required
def create_group(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        if not name:
            messages.error(request, "Group name is required.")
            return redirect("groupchat:groups")
        group = Group.objects.create(name=name, description=description, teacher=request.user)
        _ensure_teacher_membership(group)
        messages.success(request, "Group created.")
        return redirect("groupchat:group_detail", group_id=group.id)
    return HttpResponseForbidden()


@login_required
def group_detail(request, group_id: int):
    group = get_object_or_404(Group, id=group_id)
    # Access allowed if teacher or a member
    is_member = GroupMembership.objects.filter(group=group, user=request.user).exists()
    if not (is_member or _user_is_group_teacher(request.user, group)):
        messages.error(request, "You do not have access to this group.")
        return redirect("groupchat:groups")

    _ensure_teacher_membership(group)
    messages_qs = group.messages.select_related("sender").all()
    join_requests = []
    memberships = group.memberships.select_related("user").all()
    if _user_is_group_teacher(request.user, group):
        join_requests = group.join_requests.filter(status=GroupJoinRequest.PENDING)

    context = {
        "group": group,
        "messages": messages_qs,
        "memberships": memberships,
        "join_requests": join_requests,
    }
    return render(request, "groupchat/group_detail.html", context)


@login_required
def send_group_message(request, group_id: int):
    group = get_object_or_404(Group, id=group_id)
    if not GroupMembership.objects.filter(group=group, user=request.user).exists():
        return JsonResponse({"success": False, "error": "Not a group member"})

    if request.method == "POST":
        content = request.POST.get("content", "").strip()
        attachment = request.FILES.get("attachment")
        if not content and not attachment:
            return JsonResponse({"success": False, "error": "Empty message"})

        message_type = GroupMessage.detect_type_for_upload(attachment)
        msg = GroupMessage.objects.create(
            group=group,
            sender=request.user,
            content=content,
            message_type=message_type,
            attachment=attachment,
        )

        # Format created_at with local time display
        return JsonResponse({
            "success": True,
            "message": {
                "id": msg.id,
                "content": msg.content,
                "message_type": msg.message_type,
                "attachment_url": msg.attachment.url if msg.attachment else None,
                "created_at": msg.created_at.astimezone().strftime('%d-%m-%Y %I:%M %p'),
                "sender": request.user.username,
            }
        })
    return JsonResponse({"success": False, "error": "Invalid method"})


@login_required
def request_join_group(request, group_id: int):
    group = get_object_or_404(Group, id=group_id)
    if _user_is_group_teacher(request.user, group):
        messages.info(request, "Teachers are already in their groups.")
        return redirect("groupchat:group_detail", group_id=group.id)

    # Already a member?
    if GroupMembership.objects.filter(group=group, user=request.user).exists():
        messages.info(request, "You are already a member of this group.")
        return redirect("groupchat:group_detail", group_id=group.id)

    GroupJoinRequest.objects.get_or_create(group=group, student=request.user)
    messages.success(request, "Join request sent.")
    return redirect("groupchat:groups")


@login_required
def handle_join_request(request, request_id: int, action: str):
    join_request = get_object_or_404(GroupJoinRequest, id=request_id)
    if not _user_is_group_teacher(request.user, join_request.group):
        return HttpResponseForbidden()

    if action not in {"approve", "reject"}:
        return HttpResponseForbidden()

    if action == "approve":
        GroupMembership.objects.get_or_create(
            group=join_request.group,
            user=join_request.student,
            defaults={"role": "student"},
        )
        join_request.status = GroupJoinRequest.APPROVED
    else:
        join_request.status = GroupJoinRequest.REJECTED
    join_request.processed_at = join_request.processed_at or join_request.created_at
    join_request.save()
    messages.success(request, f"Request {join_request.status}.")
    return redirect("groupchat:group_detail", group_id=join_request.group.id)


@login_required
def add_student_to_group(request, group_id: int):
    """Teacher can add a student by username."""
    group = get_object_or_404(Group, id=group_id)
    if not _user_is_group_teacher(request.user, group):
        return HttpResponseForbidden()

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        if not username:
            messages.error(request, "Username required")
            return redirect("groupchat:group_detail", group_id=group.id)

        User = get_user_model()
        try:
            student = User.objects.get(username=username, studentprofile__isnull=False)
        except User.DoesNotExist:
            messages.error(request, "Student user not found")
            return redirect("groupchat:group_detail", group_id=group.id)

        GroupMembership.objects.get_or_create(group=group, user=student, defaults={"role": "student"})
        messages.success(request, "Student added")
        return redirect("groupchat:group_detail", group_id=group.id)
    return HttpResponseForbidden()


@login_required
def search_students(request, group_id: int):
    """Typeahead search for real student users not already in group."""
    group = get_object_or_404(Group, id=group_id)
    if not _user_is_group_teacher(request.user, group):
        return JsonResponse({"results": []})

    query = request.GET.get("q", "").strip()
    User = get_user_model()
    qs = User.objects.filter(studentprofile__isnull=False)
    if query:
        qs = qs.filter(Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query))
    # Exclude existing members
    qs = qs.exclude(group_memberships__group=group)
    results = [
        {
            "username": u.username,
            "full_name": (u.get_full_name() or u.username),
            "email": u.email,
        }
        for u in qs.order_by('username')[:10]
    ]
    return JsonResponse({"results": results})


@login_required
def get_new_messages(request, group_id: int):
    """Poll for new messages after a given message ID."""
    group = get_object_or_404(Group, id=group_id)
    if not GroupMembership.objects.filter(group=group, user=request.user).exists() and not _user_is_group_teacher(request.user, group):
        return JsonResponse({"success": False, "error": "Not a group member"})

    try:
        last_id = int(request.GET.get("last_id", 0))
    except (TypeError, ValueError):
        last_id = 0

    new_messages = group.messages.filter(id__gt=last_id).select_related('sender')
    data = [
        {
            "id": m.id,
            "content": m.content,
            "message_type": m.message_type,
            "attachment_url": (m.attachment.url if m.attachment else None),
            "created_at": m.created_at.astimezone().strftime('%d-%m-%Y %I:%M %p'),
            "sender": m.sender.username,
        }
        for m in new_messages
    ]
    return JsonResponse({"success": True, "messages": data})


@login_required
def participants(request, group_id: int):
    """Return participants JSON for a group."""
    group = get_object_or_404(Group, id=group_id)
    if not GroupMembership.objects.filter(group=group, user=request.user).exists() and not _user_is_group_teacher(request.user, group):
        return JsonResponse({"participants": []})
    data = [
        {
            "username": m.user.username,
            "full_name": (m.user.get_full_name() or m.user.username),
            "role": m.role,
            "is_self": m.user_id == request.user.id,
        }
        for m in group.memberships.select_related('user').order_by('role', 'user__username')
    ]
    return JsonResponse({"participants": data})


@login_required
def remove_member(request, group_id: int, username: str):
    group = get_object_or_404(Group, id=group_id)
    if not _user_is_group_teacher(request.user, group):
        return HttpResponseForbidden()
    if request.method != 'POST':
        return HttpResponseForbidden()
    # Do not allow removing the teacher
    try:
        membership = GroupMembership.objects.get(group=group, user__username=username)
        if membership.user_id == group.teacher_id:
            messages.error(request, "Cannot remove the teacher.")
        else:
            membership.delete()
            messages.success(request, f"Removed {username} from the group.")
    except GroupMembership.DoesNotExist:
        messages.error(request, "Member not found.")
    return redirect('groupchat:group_detail', group_id=group.id)


@login_required
def leave_group(request, group_id: int):
    group = get_object_or_404(Group, id=group_id)
    if request.method != 'POST':
        return HttpResponseForbidden()
    # Teacher cannot leave their own group
    if _user_is_group_teacher(request.user, group):
        messages.error(request, "Teacher cannot leave their own group.")
        return redirect('groupchat:group_detail', group_id=group.id)
    GroupMembership.objects.filter(group=group, user=request.user).delete()
    messages.success(request, "You left the group.")
    return redirect('groupchat:groups')

