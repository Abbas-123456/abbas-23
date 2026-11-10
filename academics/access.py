from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


ROLE_REGISTRAR = 'Academic Registrar'
ROLE_LECTURER = 'Lecturer'
ROLE_COORDINATOR = 'Faculty Coordinator'


def has_role(user, role):
    return user.is_superuser or user.groups.filter(name=role).exists()


def role_required(role):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not has_role(request.user, role):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


registrar_required = role_required(ROLE_REGISTRAR)
lecturer_required = role_required(ROLE_LECTURER)
coordinator_required = role_required(ROLE_COORDINATOR)
