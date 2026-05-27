from django.utils.deprecation import MiddlewareMixin


class DisableCSRFForAPI(MiddlewareMixin):
    """
    Skip CSRF checks for all /api/ requests.
    The admin and any browser-rendered forms still go through normal CSRF protection.
    JWT authentication handles API security — CSRF is not needed for stateless token auth.
    """

    def process_request(self, request):
        if request.path_info.startswith("/api/"):
            # Mark this request as already CSRF-verified so the middleware passes it through
            setattr(request, "_dont_enforce_csrf_checks", True)
