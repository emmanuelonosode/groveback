from rest_framework.permissions import BasePermission
from .models import Role


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == Role.ADMIN)


class IsManagerOrAbove(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and request.user.role in (Role.ADMIN, Role.MANAGER)
        )


class IsAgentOrAbove(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and request.user.role in (Role.ADMIN, Role.MANAGER, Role.AGENT)
        )


class IsAccountantOrAbove(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and request.user.role in (Role.ADMIN, Role.MANAGER, Role.ACCOUNTANT)
        )


class IsStaff(BasePermission):
    """Admin, Manager, Agent, or Accountant — anyone except CLIENT."""
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and request.user.role != Role.CLIENT
        )
