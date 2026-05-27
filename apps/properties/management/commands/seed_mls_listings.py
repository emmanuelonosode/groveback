from decimal import Decimal

import cloudinary.uploader
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role
from apps.properties.models import AmenityCategory, Property, PropertyAmenity, PropertyImage

User = get_user_model()

# ── Amenity categories (8-category schema) ────────────────────────────────────
AMENITY_CATEGORIES = [
    {"name": "Interior Features",    "icon": "home",        "order": 0},
    {"name": "Kitchen & Appliances", "icon": "utensils",    "order": 1},
    {"name": "Outdoor & Grounds",    "icon": "tree",        "order": 2},
    {"name": "Utilities & Climate",  "icon": "thermometer", "order": 3},
    {"name": "Parking & Storage",    "icon": "car",         "order": 4},
    {"name": "Security & Access",    "icon": "shield",      "order": 5},
    {"name": "Community & Building", "icon": "building-2",  "order": 6},
    {"name": "Pet Policy",           "icon": "paw-print",   "order": 7},
]

# ── 10 OneKey MLS listings (NY) ───────────────────────────────────────────────
# Source: onekeymls.com  |  Scraped: 2026-05-05
# Schema corrections applied:
#   - Titles rewritten (removed "| OneKey® MLS" scraper artifact)
#   - Addresses completed (street type restored from source URLs)
#   - prop_006 type corrected: residential → commercial
#   - prop_007 city corrected: Central Valley → Woodbury; lot_size + sqft added
#   - garage counts corrected from descriptions
#   - stories corrected from descriptions
#   - neighborhood set from descriptions, not city name
LISTINGS = [
    # ── 1 — 345 Quincy St Unit A, Brooklyn (Bedford-Stuyvesant) ───────────────
    {
        "id": "mls_001",
        "data": {
            "title": "5BR Gut-Renovated Townhouse with Loft & Private Backyard — Bed-Stuy, Brooklyn",
            "description": (
                "Experience the perfect blend of modern design and structural integrity at 345A Quincy Street, "
                "a thoughtfully renovated property in the heart of Bedford-Stuyvesant. Enhanced from the ground up, "
                "this residence delivers both long-term durability and elevated everyday living. "
                "The home's foundation has been reinforced with a 24-foot steel I-beam supported by dual steel columns, "
                "providing stability while allowing seamless, expansive living spaces. "
                "The parlor floor has been fully gut-renovated — raised ceilings, recessed lighting, an 8-foot island "
                "chef's kitchen with marble countertops, and a glass wall/door system opening to a curated backyard "
                "with concrete, gravel, synthetic grass, and a custom fire pit. "
                "Upstairs, the primary suite features dual-tone paint, recessed lighting, and a restored decorative "
                "fireplace with exposed historic stone. The top floor has been transformed into a loft-style "
                "one-bedroom apartment with exposed brick, reclaimed wood, and a private 16' x 12' roof deck. "
                "Fully finished basement with separate entrance. Steps from the A and G trains, Herbert Von King Park, "
                "and the best of Bed-Stuy dining and shopping."
            ),
            "type":         "residential",
            "listing_type": "for-sale",
            "status":       "available",
            "condition":    "excellent",
            "price":        Decimal("2499000.00"),
            "price_label":  "",
            "bedrooms":     5,
            "bathrooms":    Decimal("4.0"),
            "sqft":         0,
            "lot_size":     None,
            "year_built":   1899,
            "garage":       0,
            "stories":      3,
            "address":      "345 Quincy St Unit A",
            "city":         "Brooklyn",
            "state":        "NY",
            "zip_code":     "11216",
            "neighborhood": "Bedford-Stuyvesant",
            "cross_street": "",
            "latitude":     Decimal("40.687592"),
            "longitude":    Decimal("-73.946746"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":       False,
            "homepage_featured": False,
        },
        "images": [
            {"url": "https://brokerdata-b.b-cdn.net/mlsgrid/onekey/property/M00000489-994340/9a16cf7e-2410-4552-af6a-929b3585750e.webp?width=1200&height=630&quality=90&aspect_ratio=1200%3A630&sharpen=true",
             "caption": "345 Quincy St — front exterior", "is_primary": True, "order": 0},
        ],
        "amenities": [
            {"category": "Outdoor & Grounds",    "name": "Private Backyard"},
            {"category": "Outdoor & Grounds",    "name": "Roof Deck"},
            {"category": "Outdoor & Grounds",    "name": "Fire Pit"},
            {"category": "Interior Features",    "name": "Exposed Brick"},
            {"category": "Interior Features",    "name": "Recessed Lighting"},
            {"category": "Interior Features",    "name": "High Ceilings"},
            {"category": "Interior Features",    "name": "Decorative Fireplace"},
            {"category": "Kitchen & Appliances", "name": "Chef's Kitchen"},
            {"category": "Kitchen & Appliances", "name": "Marble Countertops"},
            {"category": "Kitchen & Appliances", "name": "Kitchen Island"},
        ],
    },

    # ── 2 — 5033 39th Pl, Sunnyside, NY (Sunnyside Gardens) ──────────────────
    {
        "id": "mls_002",
        "data": {
            "title": "6BR Multi-Family Home in Sunnyside Gardens Historic District, Queens",
            "description": (
                "Welcome to Sunnyside Gardens — a vibrant, thriving, diverse community and unique historical district "
                "with private parks and English Garden-style architecture. The neighborhood boasts many landmarks, "
                "protected green spaces, parks, and playgrounds, and is renowned for its ethnic diversity and wide "
                "range of international cuisines along Queens Blvd. "
                "Property sold 'as-is'; seller makes no representation for appliances or fixtures. "
                "Easy access to all transportation — 15 minutes to Manhattan via the #7 train. "
                "Bus routes Q32, Q39, and Q60 nearby."
            ),
            "type":         "residential",
            "listing_type": "for-sale",
            "status":       "available",
            "condition":    "good",
            "price":        Decimal("1295000.00"),
            "price_label":  "",
            "bedrooms":     6,
            "bathrooms":    Decimal("3.0"),
            "sqft":         0,
            "lot_size":     None,
            "year_built":   1920,
            "garage":       0,
            "stories":      2,
            "address":      "5033 39th Pl",
            "city":         "Sunnyside",
            "state":        "NY",
            "zip_code":     "11104",
            "neighborhood": "Sunnyside Gardens",
            "cross_street": "",
            "latitude":     Decimal("40.737165"),
            "longitude":    Decimal("-73.926264"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":       False,
            "homepage_featured": False,
        },
        "images": [
            {"url": "https://brokerdata-b.b-cdn.net/mlsgrid/onekey/property/M00000489-988353/bda4b6a3-96ee-4b4f-8eab-056a3ba84349.webp?width=1200&height=630&quality=90&aspect_ratio=1200%3A630&sharpen=true",
             "caption": "5033 39th Pl — exterior", "is_primary": True, "order": 0},
        ],
        "amenities": [],
    },

    # ── 3 — 215 Gallagher St, Buchanan, NY ────────────────────────────────────
    {
        "id": "mls_003",
        "data": {
            "title": "3BR Classic Foursquare Home on Expansive Lot — Buchanan, NY",
            "description": (
                "Classic Foursquare-style home in the heart of Buchanan offering charm, functionality, and "
                "long-term potential. Set on a level and expansive lot with municipal systems (water, sewer, gas) "
                "and an unfinished basement great for additional storage or future-use flexibility. "
                "Detached 1-car garage and a manageable yard space with room to enjoy. "
                "Located within the Hendrick Hudson School District and minutes to local shops, schools, parks, "
                "riverfront amenities, and commuter routes. A strong opportunity for end users or investors "
                "looking to create value in a sought-after pocket of town."
            ),
            "type":         "residential",
            "listing_type": "for-sale",
            "status":       "available",
            "condition":    "good",
            "price":        Decimal("579000.00"),
            "price_label":  "",
            "bedrooms":     3,
            "bathrooms":    Decimal("2.0"),
            "sqft":         0,
            "lot_size":     None,
            "year_built":   1900,
            "garage":       1,
            "stories":      2,
            "address":      "215 Gallagher St",
            "city":         "Buchanan",
            "state":        "NY",
            "zip_code":     "10511",
            "neighborhood": "Buchanan",
            "cross_street": "",
            "latitude":     Decimal("41.257307"),
            "longitude":    Decimal("-73.938011"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":       False,
            "homepage_featured": False,
        },
        "images": [
            {"url": "https://brokerdata-b.b-cdn.net/mlsgrid/onekey/property/M00000489-980492/d4a2874f-0117-4aa2-b052-a6d2122368c4.webp?width=1200&height=630&quality=90&aspect_ratio=1200%3A630&sharpen=true",
             "caption": "215 Gallagher St — exterior", "is_primary": True, "order": 0},
        ],
        "amenities": [
            {"category": "Parking & Storage", "name": "Detached 1-Car Garage"},
        ],
    },

    # ── 4 — 567 Ashford St, Brooklyn, NY (East New York) ─────────────────────
    {
        "id": "mls_004",
        "data": {
            "title": "All-Brick Corner 3-Family Building — East New York, Brooklyn",
            "description": (
                "Impressive all-brick corner 3-family residence with strong investment upside. "
                "Currently features 3 apartments (3BR / 2BR / 2BR / 1BR) with potential for an added 4th unit. "
                "High-ceiling basement with legalization potential, spacious enough to accommodate two additional "
                "apartments with the right permits. Situated near the train and highway — a prime find for both "
                "owner-occupied living and investment. Monthly expenses could be less than half of the rent roll. "
                "By appointment only."
            ),
            "type":         "residential",
            "listing_type": "for-sale",
            "status":       "available",
            "condition":    "good",
            "price":        Decimal("1280000.00"),
            "price_label":  "",
            "bedrooms":     0,
            "bathrooms":    Decimal("0.0"),
            "sqft":         0,
            "lot_size":     None,
            "year_built":   1901,
            "garage":       0,
            "stories":      3,
            "address":      "567 Ashford St",
            "city":         "Brooklyn",
            "state":        "NY",
            "zip_code":     "11207",
            "neighborhood": "East New York",
            "cross_street": "",
            "latitude":     Decimal("40.668139"),
            "longitude":    Decimal("-73.883526"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":       False,
            "homepage_featured": False,
        },
        "images": [
            {"url": "https://brokerdata-b.b-cdn.net/mlsgrid/onekey/property/M00000489-992238/a26f4ba5-80a3-44cd-a41b-1f6bc0f56019.webp?width=1200&height=630&quality=90&aspect_ratio=1200%3A630&sharpen=true",
             "caption": "567 Ashford St — corner exterior", "is_primary": True, "order": 0},
        ],
        "amenities": [],
    },

    # ── 5 — 88 Cliff Ave, Sayville, NY ────────────────────────────────────────
    {
        "id": "mls_005",
        "data": {
            "title": "2BR Renovated Cottage on 10,000 sqft Lot — Sayville, NY",
            "description": (
                "Move-in-ready Sayville cottage on a deep and private 10,000 sq ft lot. "
                "Extensively renovated throughout with maple hardwood floors, a cathedral ceiling, and a beautifully "
                "updated kitchen featuring white shaker soft-close cabinets, quartz countertops, an island, and "
                "energy-efficient Samsung appliances. Fully renovated bath with soaking tub, two-in-one shower, "
                "soft-close vanity, and custom shelving. Main-floor mudroom/laundry with built-ins. "
                "Large attic/loft with potential for a third bedroom. "
                "Exterior upgrades include a new roof, new Pella windows, new Dutch-lap vinyl siding, and new "
                "front/rear walkways. Detached garage and cellar for abundant storage. "
                "Located in the highly rated Sayville School District, minutes from Main Street, the LIRR, "
                "ferries, parks, and beaches. Ideal for first-time buyers or downsizers seeking a prime South Shore location."
            ),
            "type":         "residential",
            "listing_type": "for-sale",
            "status":       "available",
            "condition":    "excellent",
            "price":        Decimal("599999.00"),
            "price_label":  "",
            "bedrooms":     2,
            "bathrooms":    Decimal("1.0"),
            "sqft":         0,
            "lot_size":     Decimal("0.23"),
            "year_built":   1932,
            "garage":       1,
            "stories":      2,
            "address":      "88 Cliff Ave",
            "city":         "Sayville",
            "state":        "NY",
            "zip_code":     "11782",
            "neighborhood": "Sayville",
            "cross_street": "",
            "latitude":     Decimal("40.744598"),
            "longitude":    Decimal("-73.092494"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":       False,
            "homepage_featured": False,
        },
        "images": [
            {"url": "https://brokerdata-b.b-cdn.net/mlsgrid/onekey/property/M00000489-992809/942a1178-ae24-402f-ad40-1ea74dc4c796.webp?width=1200&height=630&quality=90&aspect_ratio=1200%3A630&sharpen=true",
             "caption": "88 Cliff Ave — exterior", "is_primary": True, "order": 0},
        ],
        "amenities": [
            {"category": "Interior Features",    "name": "Cathedral Ceiling"},
            {"category": "Interior Features",    "name": "Hardwood Floors"},
            {"category": "Interior Features",    "name": "Attic / Loft"},
            {"category": "Kitchen & Appliances", "name": "Quartz Countertops"},
            {"category": "Kitchen & Appliances", "name": "Kitchen Island"},
            {"category": "Parking & Storage",    "name": "Detached Garage"},
        ],
    },

    # ── 6 — 13646 41st Ave Unit 1E, Flushing, NY (Commercial) ─────────────────
    {
        "id": "mls_006",
        "data": {
            "title": "800 sqft Commercial Space — High-Visibility Location, Flushing, Queens",
            "description": (
                "Prime commercial space offering approximately 800 sq ft, ideal for a variety of business uses. "
                "This well-maintained unit features an open layout easily customized for retail, office, or "
                "professional use. Excellent visibility and accessibility make it a strong opportunity for both "
                "owner-users and investors. Common charges are $247/month, offering manageable carrying costs. "
                "Conveniently located near major thoroughfares, public transportation, and established businesses, "
                "ensuring steady foot traffic and strong local presence."
            ),
            "type":         "commercial",
            "listing_type": "for-sale",
            "status":       "available",
            "condition":    "good",
            "price":        Decimal("920000.00"),
            "price_label":  "",
            "bedrooms":     0,
            "bathrooms":    Decimal("0.0"),
            "sqft":         800,
            "lot_size":     None,
            "year_built":   2008,
            "garage":       0,
            "stories":      1,
            "address":      "13646 41st Ave Unit 1E",
            "city":         "Flushing",
            "state":        "NY",
            "zip_code":     "11355",
            "neighborhood": "Flushing",
            "cross_street": "",
            "latitude":     Decimal("40.758755"),
            "longitude":    Decimal("-73.827702"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":       False,
            "homepage_featured": False,
        },
        "images": [
            {"url": "https://brokerdata-b.b-cdn.net/mlsgrid/onekey/property/M00000489-989950/57cc1703-dd69-4536-8b61-638c4cb02ecd.webp?width=1200&height=630&quality=90&aspect_ratio=1200%3A630&sharpen=true",
             "caption": "13646 41st Ave Unit 1E — commercial interior", "is_primary": True, "order": 0},
        ],
        "amenities": [],
    },

    # ── 7 — 23 Greenwich Ave, Woodbury, NY (Hudson Valley estate) ─────────────
    {
        "id": "mls_007",
        "data": {
            "title": "5BR Hudson Valley Estate — 7,500+ sqft, Heated Pool, Golf Course Views",
            "description": (
                "A Hudson Valley mini estate with 7,500+ sqft backing onto protected land and Falkirk Golf Course. "
                "The largest home in The Greens of Woodbury — 5,312 sqft above grade plus a 2,200 sqft fully "
                "finished lower level. A 0.76-acre lot backs onto Town of Woodbury preserve land and the Falkirk "
                "golf course with permanent mountain views and no new construction possible behind the property. "
                "Extensively upgraded by the current owner: hand-forged iron-and-glass entry doors with smart "
                "fingerprint access, three chandeliers, new solid hardwood throughout, motorized window treatments. "
                "Lower level includes a bar area, billiards, sauna with en-suite bath, au pair suite, and multi-person whirlpool. "
                "Outdoor: 796 sqft heated pool with waterfall (2020), stone paver patio, three entertaining zones, "
                "automated lighting, and whole-house solar (2024). "
                "Six full and one half baths, three fireplaces. Attached 1,482 sqft five-car garage. "
                "Monroe-Woodbury Central School District. 5 min to I-87, 9 min to Harriman train. "
                "50 minutes to the GWB — country estate living with city access."
            ),
            "type":         "residential",
            "listing_type": "for-sale",
            "status":       "available",
            "condition":    "excellent",
            "price":        Decimal("1980000.00"),
            "price_label":  "",
            "bedrooms":     5,
            "bathrooms":    Decimal("7.0"),
            "sqft":         7500,
            "lot_size":     Decimal("0.76"),
            "year_built":   2003,
            "garage":       5,
            "stories":      3,
            "address":      "23 Greenwich Ave",
            "city":         "Woodbury",
            "state":        "NY",
            "zip_code":     "10917",
            "neighborhood": "The Greens of Woodbury",
            "cross_street": "",
            "latitude":     Decimal("41.334422"),
            "longitude":    Decimal("-74.108975"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":       True,
            "homepage_featured": False,
        },
        "images": [
            {"url": "https://brokerdata-b.b-cdn.net/mlsgrid/onekey/property/M00000489-994262/99634361-4f72-45cf-b65f-074daffda2de.webp?width=1200&height=630&quality=90&aspect_ratio=1200%3A630&sharpen=true",
             "caption": "23 Greenwich Ave — estate exterior", "is_primary": True, "order": 0},
        ],
        "amenities": [
            {"category": "Outdoor & Grounds",    "name": "Heated Pool with Waterfall"},
            {"category": "Outdoor & Grounds",    "name": "Stone Paver Patio"},
            {"category": "Outdoor & Grounds",    "name": "Fire Pit Lounge"},
            {"category": "Interior Features",    "name": "Hardwood Floors"},
            {"category": "Interior Features",    "name": "Three Fireplaces"},
            {"category": "Interior Features",    "name": "Walk-in Pantry"},
            {"category": "Interior Features",    "name": "Sauna"},
            {"category": "Kitchen & Appliances", "name": "Six-Burner Range"},
            {"category": "Kitchen & Appliances", "name": "Granite Countertops"},
            {"category": "Kitchen & Appliances", "name": "Kitchen Island"},
            {"category": "Parking & Storage",    "name": "5-Car Attached Garage"},
            {"category": "Utilities & Climate",  "name": "Whole-House Solar"},
        ],
    },

    # ── 8 — 8 Lake Shore Dr W, Rock Hill, NY (Catskills) ─────────────────────
    {
        "id": "mls_008",
        "data": {
            "title": "3BR Updated Home in Emerald Green Community — Rock Hill, Catskills",
            "description": (
                "Beautifully updated home nestled in the desirable Emerald Green community of Rock Hill. "
                "This 3-bedroom, 3-bathroom residence features light-filled living spaces and a natural flow "
                "perfect for everyday comfort and entertaining. "
                "Exterior enhanced in 2025 with new siding and an expansive deck. Finished walk-out lower level "
                "with additional flexible space. Primary bathroom features a built-in sound system. "
                "Life in Emerald Green includes exclusive access to pristine lakes, sandy beaches, a swimming pool, "
                "clubhouse, and more. "
                "Just minutes from Resorts World Catskills, The Kartrite Resort & Indoor Waterpark, and Bethel Woods. "
                "Year-round activities — hiking, skiing, golfing, premier dining. "
                "Conveniently located 90 minutes from New York City. Perfect full-time residence or seasonal escape."
            ),
            "type":         "residential",
            "listing_type": "for-sale",
            "status":       "available",
            "condition":    "excellent",
            "price":        Decimal("450000.00"),
            "price_label":  "",
            "bedrooms":     3,
            "bathrooms":    Decimal("3.0"),
            "sqft":         0,
            "lot_size":     None,
            "year_built":   1987,
            "garage":       0,
            "stories":      2,
            "address":      "8 Lake Shore Dr W",
            "city":         "Rock Hill",
            "state":        "NY",
            "zip_code":     "12775",
            "neighborhood": "Emerald Green",
            "cross_street": "",
            "latitude":     Decimal("41.604360"),
            "longitude":    Decimal("-74.587060"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":       False,
            "homepage_featured": False,
        },
        "images": [
            {"url": "https://brokerdata-b.b-cdn.net/mlsgrid/onekey/property/M00000489-987391/ed881a1a-78e0-422e-9eff-7c6b87dce8b3.webp?width=1200&height=630&quality=90&aspect_ratio=1200%3A630&sharpen=true",
             "caption": "8 Lake Shore Dr W — exterior with deck", "is_primary": True, "order": 0},
        ],
        "amenities": [
            {"category": "Outdoor & Grounds",    "name": "Expansive Deck"},
            {"category": "Community & Building", "name": "Community Pool"},
            {"category": "Community & Building", "name": "Private Lake Access"},
            {"category": "Community & Building", "name": "Sandy Beach"},
            {"category": "Community & Building", "name": "Clubhouse"},
        ],
    },

    # ── 9 — 6 Cantitoe Rd, Yonkers, NY (Westchester Hills) ───────────────────
    {
        "id": "mls_009",
        "data": {
            "title": "3BR Updated Corner Lot Home — Westchester Hills, Yonkers",
            "description": (
                "Beautifully updated 3-bedroom home in the highly desirable Westchester Hills section of Yonkers. "
                "Features gleaming hardwood floors throughout, stainless steel appliances, and elegant granite countertops. "
                "All-electric living with brand-new central air conditioning for year-round comfort. "
                "Finished basement — perfect for a home office, gym, or recreation area. "
                "Situated on a spacious corner lot with a detached one-car garage, private driveway, and abundant "
                "street parking. Minutes from Central Avenue shopping and dining, with convenient access to "
                "Metro-North, major parkways, and New York City."
            ),
            "type":         "residential",
            "listing_type": "for-sale",
            "status":       "available",
            "condition":    "excellent",
            "price":        Decimal("749000.00"),
            "price_label":  "",
            "bedrooms":     3,
            "bathrooms":    Decimal("1.0"),
            "sqft":         0,
            "lot_size":     None,
            "year_built":   1949,
            "garage":       1,
            "stories":      2,
            "address":      "6 Cantitoe Rd",
            "city":         "Yonkers",
            "state":        "NY",
            "zip_code":     "10710",
            "neighborhood": "Westchester Hills",
            "cross_street": "",
            "latitude":     Decimal("40.983263"),
            "longitude":    Decimal("-73.833593"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":       False,
            "homepage_featured": False,
        },
        "images": [
            {"url": "https://brokerdata-b.b-cdn.net/mlsgrid/onekey/property/M00000489-986422/6bd6a8b6-2c20-445f-b0e2-8528f9f8c812.webp?width=1200&height=630&quality=90&aspect_ratio=1200%3A630&sharpen=true",
             "caption": "6 Cantitoe Rd — corner lot exterior", "is_primary": True, "order": 0},
        ],
        "amenities": [
            {"category": "Interior Features",    "name": "Hardwood Floors"},
            {"category": "Interior Features",    "name": "Finished Basement"},
            {"category": "Kitchen & Appliances", "name": "Granite Countertops"},
            {"category": "Kitchen & Appliances", "name": "Stainless Steel Appliances"},
            {"category": "Utilities & Climate",  "name": "Central A/C"},
            {"category": "Parking & Storage",    "name": "Detached 1-Car Garage"},
        ],
    },

    # ── 10 — 10515 Jamaica Ave, Richmond Hill, Queens ─────────────────────────
    {
        "id": "mls_010",
        "data": {
            "title": "6BR Mixed-Use Brick Building with Storefront & Large Backyard — Richmond Hill, Queens",
            "description": (
                "Exceptional opportunity to own a massive brick mixed-use building featuring a ground-floor storefront "
                "and two large residential units above, plus a full finished basement and spacious backyard. "
                "First floor: large storefront with excellent visibility and foot traffic — ideal for retail, office, "
                "or service business. "
                "Second floor: 3 large bedrooms, living room, dining room, eat-in kitchen, 2 full bathrooms. "
                "Third floor: 3 large bedrooms, living room, dining room, eat-in kitchen, 2 full bathrooms. "
                "Full finished basement perfect for storage or recreation. "
                "Large, clean backyard — rare for this type of property, ideal for tenant use or future improvements."
            ),
            "type":         "residential",
            "listing_type": "for-sale",
            "status":       "available",
            "condition":    "good",
            "price":        Decimal("1488000.00"),
            "price_label":  "",
            "bedrooms":     6,
            "bathrooms":    Decimal("5.0"),
            "sqft":         0,
            "lot_size":     None,
            "year_built":   1910,
            "garage":       0,
            "stories":      3,
            "address":      "10515 Jamaica Ave",
            "city":         "Richmond Hill",
            "state":        "NY",
            "zip_code":     "11418",
            "neighborhood": "Richmond Hill",
            "cross_street": "",
            "latitude":     Decimal("40.695437"),
            "longitude":    Decimal("-73.841418"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":       False,
            "homepage_featured": False,
        },
        "images": [
            {"url": "https://brokerdata-b.b-cdn.net/mlsgrid/onekey/property/M00000489-994335/52efa3fa-7ff0-454e-a4f1-2397cddb2293.webp?width=1200&height=630&quality=90&aspect_ratio=1200%3A630&sharpen=true",
             "caption": "10515 Jamaica Ave — brick building exterior", "is_primary": True, "order": 0},
        ],
        "amenities": [
            {"category": "Outdoor & Grounds", "name": "Large Private Backyard"},
            {"category": "Interior Features", "name": "Finished Basement"},
        ],
    },
]


class Command(BaseCommand):
    help = "Import 10 OneKey MLS listings (NY — for-sale residential & commercial) into the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--published",
            action="store_true",
            default=False,
            help="Set is_published=True on all imported listings (default: False — review in admin first).",
        )
        parser.add_argument(
            "--featured",
            action="store_true",
            default=False,
            help="Set is_featured=True on all imported listings.",
        )
        parser.add_argument(
            "--agent-email",
            default="admin@haskerrealtygroup.com",
            help="Email of the agent to assign to all listings.",
        )
        parser.add_argument(
            "--skip-images",
            action="store_true",
            default=False,
            help="Skip Cloudinary image upload (useful for quick test runs).",
        )
        parser.add_argument(
            "--reset-images",
            action="store_true",
            default=False,
            help="Delete and re-upload images for properties that already exist.",
        )

    def handle(self, *args, **options):
        agent_email  = options["agent_email"]
        is_published = options["published"]
        is_featured  = options["featured"]
        skip_images  = options["skip_images"]
        reset_images = options["reset_images"]

        # ── 1. Resolve agent ──────────────────────────────────────────────────
        agent = None
        try:
            candidate = User.objects.get(email=agent_email)
            if candidate.role == Role.AGENT:
                agent = candidate
            else:
                self.stdout.write(self.style.WARNING(
                    f"  Warning: {agent_email} has role={candidate.role}, not AGENT. "
                    "Looking for an AGENT fallback..."
                ))
        except User.DoesNotExist:
            self.stdout.write(self.style.WARNING(
                f"  Warning: No user found with email '{agent_email}'. "
                "Looking for any available AGENT user..."
            ))

        if agent is None:
            agent = User.objects.filter(role=Role.AGENT).first()
            if agent is None:
                raise CommandError(
                    "No AGENT user found in the database. "
                    "Create an agent account first or pass --agent-email with a valid agent address."
                )
            self.stdout.write(self.style.WARNING(f"  Falling back to agent: {agent.email}"))

        self.stdout.write(f"Agent: {agent.get_full_name()} <{agent.email}>")

        # ── 2. Ensure amenity categories exist ────────────────────────────────
        cat_map: dict[str, AmenityCategory] = {}
        for cat_def in AMENITY_CATEGORIES:
            obj, created = AmenityCategory.objects.get_or_create(
                name=cat_def["name"],
                defaults={"icon": cat_def["icon"], "order": cat_def["order"]},
            )
            cat_map[cat_def["name"]] = obj
            if created:
                self.stdout.write(f"  Created category: {obj.name}")

        # ── 3. Import properties ──────────────────────────────────────────────
        created_count = skipped_count = 0
        total_images = total_amenities = 0

        for listing in LISTINGS:
            data    = listing["data"]
            address = data["address"]
            city    = data["city"]

            existing = Property.objects.filter(address=address, city=city).first()

            if existing and not reset_images:
                self.stdout.write(f"  Skipping (exists): {data['title']}")
                skipped_count += 1
                continue

            if existing and reset_images:
                prop = existing
                self.stdout.write(f"  Resetting images: {prop.title}")
                prop.images.all().delete()
            else:
                prop = Property.objects.create(
                    agent=agent,
                    is_published=is_published,
                    is_featured=is_featured or data.get("is_featured", False),
                    homepage_featured=data.get("homepage_featured", False),
                    title=data["title"],
                    description=data["description"],
                    type=data["type"],
                    listing_type=data["listing_type"],
                    status=data["status"],
                    condition=data["condition"],
                    price=data["price"],
                    price_label=data["price_label"],
                    bedrooms=data["bedrooms"],
                    bathrooms=data["bathrooms"],
                    sqft=data["sqft"],
                    lot_size=data["lot_size"],
                    year_built=data["year_built"],
                    garage=data["garage"],
                    stories=data["stories"],
                    address=address,
                    city=city,
                    state=data["state"],
                    zip_code=data["zip_code"],
                    neighborhood=data["neighborhood"],
                    cross_street=data["cross_street"],
                    latitude=data["latitude"],
                    longitude=data["longitude"],
                    virtual_tour_url=data["virtual_tour_url"],
                    tour_360_url=data["tour_360_url"],
                )
                created_count += 1

            # ── Images ───────────────────────────────────────────────────────
            img_count = 0
            if not skip_images:
                image_objs = []
                for img in listing["images"]:
                    try:
                        result = cloudinary.uploader.upload(
                            img["url"],
                            folder="properties/mls",
                            resource_type="image",
                            unique_filename=True,
                            overwrite=False,
                        )
                        stored = result["public_id"]
                        self.stdout.write(f"    ✓ Uploaded: {img['caption']}")
                    except Exception as exc:
                        self.stdout.write(self.style.WARNING(
                            f"    ✗ Upload failed ({img['caption']}): {exc}"
                        ))
                        stored = img["url"]

                    image_objs.append(PropertyImage(
                        property=prop,
                        image=stored,
                        caption=img["caption"],
                        is_primary=img["is_primary"],
                        order=img["order"],
                    ))

                if image_objs:
                    PropertyImage.objects.bulk_create(image_objs)
                    img_count = len(image_objs)
                    total_images += img_count

            # ── Amenities ────────────────────────────────────────────────────
            amenity_count = 0
            if not existing:
                amenity_objs = [
                    PropertyAmenity(
                        property=prop,
                        category=cat_map.get(a["category"]),
                        name=a["name"],
                    )
                    for a in listing["amenities"]
                ]
                if amenity_objs:
                    PropertyAmenity.objects.bulk_create(amenity_objs, ignore_conflicts=True)
                    amenity_count = len(amenity_objs)
                    total_amenities += amenity_count

            action = "Reset images" if existing else "Created"
            self.stdout.write(
                f"  {action}: {prop.title} "
                f"({img_count} images, {amenity_count} amenities)"
            )

        # ── 4. Summary ────────────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== IMPORT COMPLETE ==="))
        self.stdout.write(self.style.SUCCESS(f"Properties created : {created_count}"))
        self.stdout.write(self.style.SUCCESS(f"Properties skipped : {skipped_count}"))
        self.stdout.write(self.style.SUCCESS(f"Images uploaded    : {total_images}"))
        self.stdout.write(self.style.SUCCESS(f"Amenities attached : {total_amenities}"))
        self.stdout.write(self.style.SUCCESS(f"Published          : {is_published}"))
        if not is_published:
            self.stdout.write(self.style.WARNING(
                "\nListings are unpublished. Review in admin, then set is_published=True to go live.\n"
                "Admin: https://admin.haskerrealtygroup.com/admin/properties/property/"
            ))
