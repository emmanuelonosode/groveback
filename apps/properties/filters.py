import re
import difflib
import django_filters
from django.core.cache import cache
from django.db.models import Q, Case, When, Value, IntegerField
from .models import Property


class PropertyFilter(django_filters.FilterSet):
    min_price = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="price", lookup_expr="lte")
    beds = django_filters.NumberFilter(field_name="bedrooms", lookup_expr="gte")
    baths = django_filters.NumberFilter(field_name="bathrooms", lookup_expr="gte")
    min_sqft = django_filters.NumberFilter(field_name="sqft", lookup_expr="gte")
    max_sqft = django_filters.NumberFilter(field_name="sqft", lookup_expr="lte")
    pets = django_filters.BooleanFilter(method="filter_pets")
    q = django_filters.CharFilter(method="search_filter")
    sort = django_filters.CharFilter(method="sort_filter")

    class Meta:
        model = Property
        fields = {
            "type": ["exact"],
            "listing_type": ["exact"],
            "status": ["exact"],
            "condition": ["exact"],
            "city": ["exact", "icontains", "iexact"],
            "state": ["exact", "icontains", "iexact"],
            "zip_code": ["exact"],
            "is_featured": ["exact"],
            "is_published": ["exact"],
            "agent": ["exact"],
            "garage": ["exact", "gte"],
            "year_built": ["gte", "lte"],
        }

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

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        if data is not None:
            # Create a mutable copy of the QueryDict/dict
            data = data.copy()
            q_val = data.get("q", "")
            
            if q_val:
                original_q = q_val

                # 0. Fuzzy city replacement in the query string
                words = q_val.split()
                replaced_words = []
                for word in words:
                    word_clean = word.strip(",.-")
                    fuzzy_city = self._get_fuzzy_city_static(word_clean)
                    if fuzzy_city:
                        replaced_words.append(fuzzy_city)
                    else:
                        replaced_words.append(word)
                q_val = " ".join(replaced_words)
                
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

                # 3b. Pets ("pet friendly", "pet-friendly", "dog", "cat")
                if re.search(r'\b(?:pet|pets|dog|dogs|cat|cats)\b', q_val, re.IGNORECASE):
                    if not data.get("pets"):
                        data["pets"] = "true"
                    q_val = re.sub(r'\b(?:pet|pets|dog|dogs|cat|cats|friendly)\b', ' ', q_val, flags=re.IGNORECASE)

                # 4. Route property-type keywords into the type filter
                _TYPE_KEYWORDS = {
                    "condo": "condo", "condominium": "condo",
                    "townhouse": "townhouse", "townhome": "townhouse",
                    # NOTE: keep "apartment" → residential until real apartment inventory
                    # exists, so on-site search returns homes instead of an empty page.
                    # Flip to "apartment" once type=apartment listings are live.
                    "apartment": "residential", "apartments": "residential", "house": "residential",
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

                # 6. Parse state names and abbreviations
                for state_name, state_abbr in self._STATE_ABBR.items():
                    if re.search(rf'\b{state_name}\b', q_val, re.IGNORECASE):
                        if not data.get("state"):
                            data["state"] = state_abbr
                        q_val = re.sub(rf'\b{state_name}\b', '', q_val, flags=re.IGNORECASE)
                
                # Also check for explicit 2-letter state abbreviations
                for state_abbr in self._STATE_ABBR.values():
                    # Match exact 2-letter word that is a state abbreviation
                    if re.search(rf'\b{state_abbr}\b', q_val, re.IGNORECASE):
                        if not data.get("state"):
                            data["state"] = state_abbr
                        q_val = re.sub(rf'\b{state_abbr}\b', '', q_val, flags=re.IGNORECASE)

                # 7. Cleanup remaining stop words (keep "for" and "in" — they're structural)
                q_val = re.sub(r'\b(?:with|a|an)\b', ' ', q_val, flags=re.IGNORECASE)
                q_val = re.sub(r'\s+', ' ', q_val).strip()

                # 8. Fuzzy city matching ONLY if the query consists of a single word remaining
                remaining_words = q_val.split()
                if len(remaining_words) == 1:
                    word_clean = remaining_words[0].strip(",.-")
                    fuzzy_city = self._get_fuzzy_city_static(word_clean)
                    if fuzzy_city:
                        if not data.get("city__iexact"):
                            data["city__iexact"] = fuzzy_city
                        q_val = ""

                if q_val != original_q:
                    if q_val:
                        data["q"] = q_val
                    else:
                        data.pop("q", None)

        super().__init__(data, queryset, request=request, prefix=prefix)


    def filter_pets(self, queryset, name, value):
        """Pet-friendly toggle — matches against amenity names (no schema field exists)."""
        if value:
            return queryset.filter(
                Q(amenities__name__icontains="pet")
                | Q(amenities__name__icontains="dog")
                | Q(amenities__name__icontains="cat")
            ).distinct()
        return queryset

    @staticmethod
    def _known_cities():
        """Distinct published-property cities, cached 5 min — used for fuzzy typo matching."""
        cities = cache.get("property_known_cities")
        if cities is None:
            cities = list(
                Property.objects.filter(is_published=True)
                .exclude(city="")
                .values_list("city", flat=True)
                .distinct()
            )
            cache.set("property_known_cities", cities, 300)
        return cities

    @classmethod
    def _get_fuzzy_city_static(cls, term):
        if len(term) < 4:
            return None
        known = cls._known_cities()
        matches = difflib.get_close_matches(term.title(), known, n=1, cutoff=0.8)
        return matches[0] if matches else None

    def search_filter(self, queryset, name, value):
        keywords = [k.strip(",.-") for k in value.strip().split() if k.strip(",.-")]
        if not keywords:
            return queryset
            
        # 1. Try strict matching (ALL keywords must match - AND query)
        q_and = Q()
        for kw in keywords:
            kw_q = (
                Q(title__icontains=kw)
                | Q(address__icontains=kw)
                | Q(city__icontains=kw)
                | Q(neighborhood__icontains=kw)
                | Q(state__icontains=kw)
                | Q(zip_code__icontains=kw)
                | Q(description__icontains=kw)
                | Q(amenities__name__icontains=kw)
            )
            q_and &= kw_q
            
        and_qs = queryset.filter(q_and).distinct()
        if and_qs.exists():
            return and_qs

        # 2. Relaxed matching (ANY keyword matches - OR query)
        q_or = Q()
        for kw in keywords:
            kw_q = (
                Q(title__icontains=kw)
                | Q(address__icontains=kw)
                | Q(city__icontains=kw)
                | Q(neighborhood__icontains=kw)
                | Q(state__icontains=kw)
                | Q(zip_code__icontains=kw)
                | Q(description__icontains=kw)
                | Q(amenities__name__icontains=kw)
            )
            q_or |= kw_q
            
        return queryset.filter(q_or).distinct()

    lat_min = django_filters.NumberFilter(field_name="latitude", lookup_expr="gte")
    lat_max = django_filters.NumberFilter(field_name="latitude", lookup_expr="lte")
    lng_min = django_filters.NumberFilter(field_name="longitude", lookup_expr="gte")
    lng_max = django_filters.NumberFilter(field_name="longitude", lookup_expr="lte")

    def sort_filter(self, queryset, name, value):
        # Explicit user-chosen sorts always win.
        explicit = {
            "price_asc":  ["price"],
            "price_desc": ["-price"],
            "newest":     ["-created_at"],
            "oldest":     ["created_at"],
            "beds_asc":   ["bedrooms"],
            "beds_desc":  ["-bedrooms"],
            "sqft_desc":  ["-sqft"],
        }
        if value in explicit:
            return queryset.order_by(*explicit[value])

        # No explicit sort (default / "diverse"). If the user is searching by text,
        # rank by relevance instead of the diverse interleave — they want matches
        # for their term first, not a spread across every city.
        q_term = ""
        if self.request and hasattr(self.request, "query_params"):
            q_term = (self.request.query_params.get("q") or "").strip()
            
        if q_term:
            keywords = [k.strip(",.-") for k in q_term.split() if k.strip(",.-")]
            if not keywords:
                return queryset.order_by("-is_featured", "-created_at")

            # Calculate relevance score based on keyword matches
            score_annotation = Value(0, output_field=IntegerField())
            for kw in keywords:
                score_annotation += Case(
                    When(city__iexact=kw, then=Value(10)),
                    When(title__icontains=kw, then=Value(5)),
                    When(neighborhood__icontains=kw, then=Value(4)),
                    When(city__icontains=kw, then=Value(3)),
                    When(description__icontains=kw, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                )

            queryset = queryset.annotate(_relevance_score=score_annotation)
            return queryset.order_by("-_relevance_score", "-is_featured", "price")

        # No text query → globally diverse interleave (default browse page).
        return queryset.order_by("-is_featured", "-created_at")
