from django.urls import path
from . import views

app_name = "groupchat"

urlpatterns = [
    path("", views.list_groups, name="groups"),
    path("create/", views.create_group, name="create_group"),
    path("<int:group_id>/", views.group_detail, name="group_detail"),
    path("<int:group_id>/send/", views.send_group_message, name="send_group_message"),
    path("<int:group_id>/poll/", views.get_new_messages, name="get_new_messages"),
    path("<int:group_id>/request-join/", views.request_join_group, name="request_join_group"),
    path("join-request/<int:request_id>/<str:action>/", views.handle_join_request, name="handle_join_request"),
    path("<int:group_id>/add-student/", views.add_student_to_group, name="add_student_to_group"),
    path("<int:group_id>/search-students/", views.search_students, name="search_students"),
    path("<int:group_id>/participants/", views.participants, name="participants"),
    path("<int:group_id>/remove/<str:username>/", views.remove_member, name="remove_member"),
    path("<int:group_id>/leave/", views.leave_group, name="leave_group"),
]


