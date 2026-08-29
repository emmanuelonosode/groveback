"""Brand sanitisation for syndicated listing feeds.

Every listing in the catalogue arrives from an upstream feed that carries the
originating operator's brand, contact details, domains and CDN URLs. None of
that may reach a serializer, a template, a sitemap or the search index: it
leaks who the data came from, and it sends visitors (and Googlebot) to a
competitor.

Ingest is the only place this can be enforced cheaply, so every writer —
`sync_from_supabase`, `sync_invitationhomes`, the JSON importers — routes
its text and its JSON blobs through here before anything is saved.

Two rules matter beyond simple string replacement:

* Replacements are **deterministic**. An earlier version picked a phone number
  with `random.choice`, so the same home rendered a different contact number on
  every sync and two paragraphs of one description could disagree. Contact
  details are a NAP signal — they have exactly one correct value.
* Image URLs are **re-pointed at our own proxy**, not merely rewritten as text.
  `/media/properties/<slug>/<file>` is served by `proxy_property_image`, which
  fetches the origin bytes once and caches them to disk, so the public HTML
  never names a third-party host.
"""

import re

# Canonical NAP. Must stay identical to `grovefront/lib/business.ts` — Google
# cross-checks these across the site and conflicting values suppress local
# rankings.
BRAND_NAME = "Prime Family Housing"
BRAND_NAME_COMPACT = "PrimeFamilyHousing"
BRAND_DOMAIN = "primefamilyhousing.com"
BRAND_EMAIL = "housing@primefamilyhousing.com"
BRAND_PHONE = "(757) 792-4480"

# Where branded image URLs live. Kept relative so the serializer can resolve it
# against whichever host is serving (`_resolve_image_url`), and so the value in
# the database is not tied to an environment.
MEDIA_PREFIX = "/media/properties"

_UPSTREAM_HOSTS = r"(?:images\.|www\.|assets\.)?invitationhomes\.com"

# Order matters: emails and URLs are consumed before the bare brand name, so a
# domain never decays into "Prime Family Housing.com".
_EMAIL_RE = re.compile(r"[\w.+-]+@" + _UPSTREAM_HOSTS, re.I)
_IMG_URL_RE = re.compile(
    r"https?://images\.invitationhomes\.com/(?:web/[^/]+/)?([^\s\"'<>]+)", re.I
)
_SITE_URL_RE = re.compile(r"https?://" + _UPSTREAM_HOSTS + r"[^\s\"'<>]*", re.I)
_DOMAIN_RE = re.compile(_UPSTREAM_HOSTS, re.I)
_BRAND_SPACED_RE = re.compile(r"\bInvitation\s+Homes?\b", re.I)
_BRAND_COMPACT_RE = re.compile(r"\bInvitationHomes?\b", re.I)
# Any remaining standalone mention, e.g. "Invitation's" or a truncated line.
_BRAND_BARE_RE = re.compile(r"\bInvitation\s*Homes?\b", re.I)
# `\b` cannot anchor a number that opens with "(" — both sides of that
# position are non-word characters, so the boundary never matches and
# "(813) 257-0126" slipped through untouched. Digit lookarounds instead.
_PHONE_RE = re.compile(r"(?<!\d)(?:\(\d{3}\)[\s.-]*|\d{3}[-.\s])\d{3}[-.\s]\d{4}(?!\d)")


def brand_image_url(url):
    """Rewrite an upstream CDN image URL to our own proxied media path.

    `https://images.invitationhomes.com/web/w_1500,h_1000,c_limit,q_auto/<slug>/<file>`
    becomes `/media/properties/<slug>/<file>`. The transform-parameter segment
    (`web/w_1500,...`) is dropped: `proxy_property_image` re-adds the canonical
    one when it fetches the origin, so thumbnails and full-size variants of the
    same file collapse onto a single cached asset.

    Values that are already branded, already relative, or from another host are
    returned untouched — an upstream format change must never blank an image.
    """
    if not url:
        return url
    val = str(url).strip()
    # Cloudinary-style prefix left behind by an older importer.
    if val.startswith("image/upload/http"):
        val = val[len("image/upload/"):]
    if val.startswith(MEDIA_PREFIX) or BRAND_DOMAIN in val:
        return val

    match = _IMG_URL_RE.match(val)
    if not match:
        return val
    path = match.group(1).split("?")[0].strip("/")
    if not path:
        return val
    return f"{MEDIA_PREFIX}/{path}"


def sanitize_text(value):
    """Strip every upstream brand signal from a string.

    Recurses through dicts and lists so a whole JSON blob (floor plans, fees,
    schools, office details) can be passed in as-is. Non-string scalars are
    returned unchanged.
    """
    if isinstance(value, dict):
        return {k: sanitize_text(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_text(v) for v in value]
    if not isinstance(value, str) or not value:
        return value

    text = value
    # Image URLs first — they are the only upstream URL we keep (re-pointed at
    # our proxy) rather than rewrite to the marketing domain.
    text = _IMG_URL_RE.sub(lambda m: brand_image_url(m.group(0)), text)
    text = _EMAIL_RE.sub(BRAND_EMAIL, text)
    text = _SITE_URL_RE.sub(f"https://{BRAND_DOMAIN}", text)
    text = _DOMAIN_RE.sub(BRAND_DOMAIN, text)
    text = _BRAND_SPACED_RE.sub(BRAND_NAME, text)
    text = _BRAND_COMPACT_RE.sub(BRAND_NAME_COMPACT, text)
    text = _BRAND_BARE_RE.sub(BRAND_NAME, text)
    text = _PHONE_RE.sub(BRAND_PHONE, text)
    return text


def is_clean(value):
    """True when no upstream brand signal survives anywhere in `value`.

    Used by the sync commands as a post-write assertion and by
    `audit_brand_leaks` — cheaper and far harder to fool than eyeballing a diff.
    """
    if isinstance(value, dict):
        return all(is_clean(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return all(is_clean(v) for v in value)
    if not isinstance(value, str):
        return True
    return not _BRAND_BARE_RE.search(value) and not _DOMAIN_RE.search(value)


# ── Slugs ────────────────────────────────────────────────────────────────────
#
# Upstream slugs look like `10-summer-breeze-ct-30014-2911` — street, ZIP, then
# the originating operator's internal listing ID. Publishing those puts a
# competitor's primary key in our canonical URLs, reads as scraped data, and
# buries the city (the term people actually search) behind the house number.
#
# Ours is `<city>-<state>-<address>`: locality first, no foreign identifier.

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


def _slug_part(value):
    return _SLUG_STRIP_RE.sub("-", str(value or "").lower()).strip("-")


def build_property_slug(city, state, address, existing=None, pk=None):
    """Build our canonical `<city>-<state>-<address>` slug.

    `existing` is an optional callable taking a candidate slug and returning
    True if it is already taken; a numeric suffix is appended until it is free.
    Passing `pk` lets a property keep its own slug on re-sync instead of
    endlessly incrementing against itself.

    Falls back to whatever parts are present — a listing missing a city still
    gets a usable slug rather than an empty one.
    """
    base = "-".join(p for p in (_slug_part(city), _slug_part(state), _slug_part(address)) if p)
    if not base:
        return None
    base = base[:240].strip("-")
    if existing is None:
        return base

    candidate, counter = base, 2
    while existing(candidate, pk):
        candidate = f"{base}-{counter}"
        counter += 1
        if counter > 999:  # pathological duplicate address data; give up cleanly
            return None
    return candidate
