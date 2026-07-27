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


class NoIndexHeader(MiddlewareMixin):
    """
    Tag every backend response `noindex` so admin.primefamilyhousing.com can never
    surface in search results.

    This host serves only the Django admin and the JSON API — there is nothing on it a
    search engine should ever hold. Django already ships `<meta robots NONE,NOARCHIVE>`
    on admin pages, but that only covers rendered admin HTML; API responses carry no
    such signal and JSON URLs are indexable. A response header covers every route and
    every content type at once.

    Deliberately a header and not a robots.txt `Disallow: /`. Disallow blocks crawling
    but not indexing — a URL discovered via an external link can still be listed, and
    once crawling is blocked Google can never fetch the page to see a noindex. noindex
    is the directive that actually removes a URL from the index, and it only works if
    the crawler is allowed to read it.

    Harmless to the public site: these headers ride only on responses served by Django.
    The Next.js frontend renders its own pages with its own headers, so the only place
    this surfaces there is on proxied /api/v1/ JSON, which should not be indexed either.
    """

    def process_response(self, request, response):
        response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return response
