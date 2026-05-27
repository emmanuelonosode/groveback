import re
import django_filters
from django.db.models import Q
from .models import Property


class PropertyFilter(django_filters.FilterSet):
    min_price = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="price", lookup_expr="lte")
    beds = django_filters.NumberFilter(field_name="bedrooms", lookup_expr="gte")
    baths = django_filters.NumberFilter(field_name="bathrooms", lookup_expr="gte")
    min_sqft = django_filters.NumberFilter(field_name="sqft", lookup_expr="gte")
    max_sqft = django_filters.NumberFilter(field_name="sqft", lookup_expr="lte")
    q = django_filters.CharFilter(method="search_filter")
    sort = django_filters.CharFilter(method="sort_filter")

    class Meta:
        model = Property
        fields = {
            "type": ["exact"],
            "listing_type": ["exact"],
            "status": ["exact"],
            "condition": ["exact"],
            "city": ["exact", "icontains"],
            "state": ["exact", "icontains"],
            "zip_code": ["exact"],
            "is_featured": ["exact"],
            "is_published": ["exact"],
            "agent": ["exact"],
            "garage": ["exact", "gte"],
            "year_built": ["gte", "lte"],
        }

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        if data is not None:
            # Create a mutable copy of the QueryDict/dict
            data = data.copy()
            q_val = data.get("q", "")
            
            if q_val:
                original_q = q_val
                
                # 1. Parse Bedrooms (e.g. "2 bed", "3 bedrooms", "1 bd")
                bed_match = re.search(r'(\d+)\s*(?:bed|beds|bedroom|bedrooms|bd|bds)\b', q_val, re.IGNORECASE)
                if bed_match and not data.get("beds"):
                    data["beds"] = bed_match.group(1)
                    q_val = q_val[:bed_match.start()] + q_val[bed_match.end():]
                
                # 2. Parse Price ("under 2000", "< 1500", "max 2000", "cheap")
                price_match = re.search(r'(?:under|<|max)\s*\$?\s*(\d{3,})', q_val, re.IGNORECASE)
                if price_match and not data.get("max_price"):
                    data["max_price"] = price_match.group(1)
                    q_val = q_val[:price_match.start()] + q_val[price_match.end():]
                
                if re.search(r'\b(?:cheap|affordable)\b', q_val, re.IGNORECASE):
                    if not data.get("sort"):
                        data["sort"] = "price_asc"
                    q_val = re.sub(r'\b(?:cheap|affordable)\b', '', q_val, flags=re.IGNORECASE)

                # 3. Parse Garage/Parking ("garage", "parking")
                if re.search(r'\b(?:garage|parking)\b', q_val, re.IGNORECASE) and not data.get("garage__gte"):
                    data["garage__gte"] = "1"
                    q_val = re.sub(r'\b(?:garage|parking)\b', '', q_val, flags=re.IGNORECASE)
                
                # 4. Route property-type keywords into the type filter
                _TYPE_KEYWORDS = {
                    "condo": "condo", "condominium": "condo",
                    "townhouse": "townhouse", "townhome": "townhouse",
                    "apartment": "residential", "house": "residential",
                    "commercial": "commercial", "land": "land",
                }
                for kw, ptype in _TYPE_KEYWORDS.items():
                    if re.search(rf'\b{kw}\b', q_val, re.IGNORECASE):
                        if not data.get("type"):
                            data["type"] = ptype
                        q_val = re.sub(rf'\b{kw}\b', '', q_val, flags=re.IGNORECASE)

                # 5. Route listing-type keywords into the listing_type filter
                if re.search(r'\bfor\s+rent\b|\brental\b|\brent\b', q_val, re.IGNORECASE):
                    if not data.get("listing_type"):
                        data["listing_type"] = "for-rent"
                    q_val = re.sub(r'\bfor\s+rent\b|\brental\b|\brent\b', '', q_val, flags=re.IGNORECASE)
                elif re.search(r'\bfor\s+sale\b|\bto\s+buy\b', q_val, re.IGNORECASE):
                    if not data.get("listing_type"):
                        data["listing_type"] = "for-sale"
                    q_val = re.sub(r'\bfor\s+sale\b|\bto\s+buy\b', '', q_val, flags=re.IGNORECASE)

                # 6. Cleanup remaining stop words (keep "for" and "in" — they're structural)
                q_val = re.sub(r'\b(?:with|a|an)\b', ' ', q_val, flags=re.IGNORECASE)
                q_val = re.sub(r'\s+', ' ', q_val).strip()

                if q_val != original_q:
                    if q_val:
                        data["q"] = q_val
                    else:
                        data.pop("q", None)

        super().__init__(data, queryset, request=request, prefix=prefix)

    # Maps lowercase full state names to 2-letter abbreviations
    _STATE_ABBR = {
        "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
        "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
        "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
        "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
        "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
        "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
        "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
        "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
        "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
        "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
        "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
        "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
        "wisconsin": "WI", "wyoming": "WY",
    }

    def search_filter(self, queryset, name, value):
        q_obj = (
            Q(title__icontains=value)
            | Q(address__icontains=value)
            | Q(city__icontains=value)
            | Q(neighborhood__icontains=value)
            | Q(state__icontains=value)
            | Q(zip_code__icontains=value)
            | Q(description__icontains=value)
            | Q(amenities__name__icontains=value)
        )

        # "Atlanta, GA" or "Atlanta, Georgia" — comma-separated
        if ',' in value:
            parts = [p.strip() for p in value.split(',', 1)]
            if len(parts) == 2:
                city_part, state_part = parts[0], parts[1]
                q_obj |= (Q(city__icontains=city_part) & Q(state__icontains=state_part))
                q_obj |= (Q(address__icontains=city_part) & Q(city__icontains=state_part))
                # Also resolve full state name after the comma ("Atlanta, Georgia")
                state_abbr = self._STATE_ABBR.get(state_part.lower())
                if state_abbr:
                    q_obj |= (Q(city__icontains=city_part) & Q(state__iexact=state_abbr))
        else:
            words = value.strip().split()

            # "Atlanta GA" — city + 2-letter abbreviation, no comma
            if len(words) >= 2:
                last = words[-1]
                if re.match(r'^[A-Za-z]{2}$', last):
                    city_part = " ".join(words[:-1])
                    state_part = last.upper()
                    q_obj |= (Q(city__icontains=city_part) & Q(state__iexact=state_part))

            # "Atlanta Georgia" — city + full state name (1 or 2 word state)
            for n in (2, 1):
                if len(words) >= n:
                    state_guess = " ".join(words[-n:]).lower()
                    abbr = self._STATE_ABBR.get(state_guess)
                    if abbr:
                        city_guess = " ".join(words[:-n])
                        q_obj |= (Q(city__icontains=city_guess) & Q(state__iexact=abbr))
                        break

            # "Georgia" alone — full state name with no city
            state_abbr = self._STATE_ABBR.get(value.strip().lower())
            if state_abbr:
                q_obj |= Q(state__iexact=state_abbr)

        return queryset.filter(q_obj).distinct()

    lat_min = django_filters.NumberFilter(field_name="latitude", lookup_expr="gte")
    lat_max = django_filters.NumberFilter(field_name="latitude", lookup_expr="lte")
    lng_min = django_filters.NumberFilter(field_name="longitude", lookup_expr="gte")
    lng_max = django_filters.NumberFilter(field_name="longitude", lookup_expr="lte")

    def sort_filter(self, queryset, name, value):
        sort_map = {
            "price_asc":  ["price"],
            "price_desc": ["-price"],
            "newest":     ["-created_at"],
            "oldest":     ["created_at"],
            "beds_asc":   ["bedrooms"],
            "beds_desc":  ["-bedrooms"],
            "sqft_desc":  ["-sqft"],
            # Diverse: interleaves properties across cities and bedroom counts
            # so no single estate/suburb dominates the default browse page.
            "diverse":    ["city", "state", "-bedrooms", "price"],
        }
        order = sort_map.get(value, ["-created_at"])
        return queryset.order_by(*order)
