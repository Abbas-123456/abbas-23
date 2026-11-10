from .access import ROLE_COORDINATOR, ROLE_LECTURER, ROLE_REGISTRAR, has_role


def user_roles(request):
    user = request.user
    return {
        'is_academic_registrar': user.is_authenticated and has_role(user, ROLE_REGISTRAR),
        'is_lecturer': user.is_authenticated and has_role(user, ROLE_LECTURER),
        'is_faculty_coordinator': user.is_authenticated and has_role(user, ROLE_COORDINATOR),
    }
