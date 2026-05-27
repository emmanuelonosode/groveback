from decimal import Decimal

import cloudinary.uploader
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role
from apps.properties.models import AmenityCategory, Property, PropertyAmenity, PropertyImage

User = get_user_model()

# ── Amenity categories (8-category schema) ─────────────────────────────────────
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

# ── 10 NYC condo listings ──────────────────────────────────────────────────────
# Source: StreetEasy / Apartments.com  |  Scraped: 2026-05-05
# All set to is_published=False. Review in admin before going live.
# Note: image URLs are from apartments.com / zillowstatic CDNs.
#       Replace with Cloudinary-hosted copies for permanent storage.
LISTINGS = [
    # ── 1 ─────────────────────────────────────────────────────────────────────
    {
        "id": "prop_001",
        "data": {
            "title": "Modern 1BD Loft-Style Condo in Financial District",
            "description": (
                "Massive loft-like one bedroom in a full-service condo located in the heart of FiDi. "
                "Features soaring high ceilings and oversized windows flooding the space with natural light, "
                "along with an open renovated kitchen with stainless steel appliances. Originally designed by "
                "the architects behind the Empire State Building and converted to 442 luxury condo units in 2007. "
                "Building offers 24-hour doorman and concierge, a landscaped rooftop terrace with panoramic views "
                "of the East River and Manhattan Bridges, fitness center, residents’ lounge with fireplace and "
                "screening room, 5th floor Zen garden with grills, children’s playroom, and an on-site "
                "parking garage, grocery, and pharmacy."
            ),
            "type":         "condo",
            "listing_type": "for-rent",
            "status":       "available",
            "condition":    "excellent",
            "price":        Decimal("3600.00"),
            "price_label":  "/mo",
            "bedrooms":     1,
            "bathrooms":    Decimal("1.0"),
            "sqft":         789,
            "lot_size":     None,
            "year_built":   1933,
            "garage":       0,
            "stories":      22,
            "address":      "90 John St Unit 514",
            "city":         "New York",
            "state":        "NY",
            "zip_code":     "10038",
            "neighborhood": "Financial District",
            "cross_street": "John St & Gold St",
            "latitude":     Decimal("40.7082"),
            "longitude":    Decimal("-74.0071"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":        False,
            "homepage_featured":  False,
        },
        "images": [
            {"url": "https://images1.apartments.com/i2/8wtJNJNyYJ28VnYk6OY7YGCd1fX_WRFAIG7qkO06npc/111/99-john-st-unit-514-new-york-ny-primary-photo.jpg?p=1",  "caption": "Front exterior — 99 John St Deco Lofts", "is_primary": True,  "order": 0},
            {"url": "https://images1.apartments.com/i2/pSVAhQHgy3wJxko8T95MywUCIuabC_pWARdUOevlao4/117/99-john-st-unit-514-new-york-ny-building-photo.jpg?p=1",  "caption": "Living room",     "is_primary": False, "order": 1},
            {"url": "https://images1.apartments.com/i2/qGOkflZIgOjkIoMby_oNDG9T-2FJ49Y-ik_sFQDjQxc/117/99-john-st-unit-514-new-york-ny-building-photo.jpg?p=1",  "caption": "Kitchen",         "is_primary": False, "order": 2},
            {"url": "https://images1.apartments.com/i2/6_MaucMPLSMxKtX_CEMGuMERR3nvL5Yg_rYLalVKSbY/117/99-john-st-unit-514-new-york-ny-building-photo.jpg?p=1",  "caption": "Bedroom",         "is_primary": False, "order": 3},
            {"url": "https://images1.apartments.com/i2/ULzhyTGGC2tYp75aJrp4_ouHS4Umy_MItXjQ4_dnxvw/117/99-john-st-unit-514-new-york-ny-building-photo.jpg?p=1",  "caption": "Rooftop terrace", "is_primary": False, "order": 4},
        ],
        "amenities": [
            {"category": "Community & Building", "name": "24-Hour Doorman"},
            {"category": "Community & Building", "name": "Concierge"},
            {"category": "Community & Building", "name": "Rooftop Terrace"},
            {"category": "Community & Building", "name": "Residents’ Lounge"},
            {"category": "Community & Building", "name": "Fitness Center"},
            {"category": "Community & Building", "name": "Children’s Playroom"},
            {"category": "Parking & Storage",    "name": "Parking Garage"},
            {"category": "Interior Features",    "name": "High Ceilings"},
            {"category": "Interior Features",    "name": "Hardwood Floors"},
            {"category": "Interior Features",    "name": "Oversized Windows"},
            {"category": "Kitchen & Appliances", "name": "Stainless Steel Appliances"},
            {"category": "Outdoor & Grounds",    "name": "Zen Garden"},
        ],
    },

    # ── 2 ─────────────────────────────────────────────────────────────────────
    {
        "id": "prop_002",
        "data": {
            "title": "1BD Condo with City Views at The Atelier, Hell’s Kitchen",
            "description": (
                "Bright one-bedroom unit at The Atelier, a premier full-service luxury condo tower in Midtown West. "
                "Features hardwood floors, oversized windows with stunning Manhattan skyline views, and a brand new "
                "kitchen with stainless steel appliances and granite countertops. The 478-unit building offers "
                "exceptional amenities in one of Manhattan’s most vibrant neighborhoods, steps from Hudson Yards, "
                "the Theater District, and the Hudson River waterfront. Built in 2005 with a modern glass facade."
            ),
            "type":         "condo",
            "listing_type": "for-rent",
            "status":       "available",
            "condition":    "excellent",
            "price":        Decimal("3200.00"),
            "price_label":  "/mo",
            "bedrooms":     1,
            "bathrooms":    Decimal("1.0"),
            "sqft":         650,
            "lot_size":     None,
            "year_built":   2005,
            "garage":       0,
            "stories":      48,
            "address":      "635 W 42nd St Unit 17C",
            "city":         "New York",
            "state":        "NY",
            "zip_code":     "10036",
            "neighborhood": "Hell’s Kitchen",
            "cross_street": "W 42nd St & 12th Ave",
            "latitude":     Decimal("40.7593"),
            "longitude":    Decimal("-74.0013"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":        False,
            "homepage_featured":  False,
        },
        "images": [
            {"url": "https://images1.apartments.com/i2/DfQ_BLzPrnyMxzlYeRmGivvM0p55rI-pnDLeAtZHV0E/111/635-w-42nd-st-new-york-ny-primary-photo.jpg?p=1",  "caption": "The Atelier exterior",        "is_primary": True,  "order": 0},
            {"url": "https://images1.apartments.com/i2/UBNIjsrskxivymjf2gLs8LXR8_VSx5tvaX0g8seEhLQ/117/635-w-42nd-st-new-york-ny-building-photo.jpg?p=1",  "caption": "Living room with city views", "is_primary": False, "order": 1},
            {"url": "https://images1.apartments.com/i2/mm1XOYdEtOMhCH6G0vE4bwRVOurXQ2dP9ecxrHKjXCk/117/635-w-42nd-st-new-york-ny-building-photo.jpg?p=1",  "caption": "Kitchen",                    "is_primary": False, "order": 2},
            {"url": "https://images1.apartments.com/i2/kSY-BqUuC6WSUdVJ8-pO-b7OzVAJSDOIp_kQGg0-HC4/117/635-w-42nd-st-new-york-ny-building-photo.jpg?p=1",  "caption": "Master bedroom",             "is_primary": False, "order": 3},
            {"url": "https://images1.apartments.com/i2/wacGsB9tLNYyoaRzh_tmcuRXflMl334qq2Lr0gW8BDA/117/635-w-42nd-st-new-york-ny-building-photo.jpg?p=1",  "caption": "Building amenities",         "is_primary": False, "order": 4},
        ],
        "amenities": [
            {"category": "Interior Features",    "name": "Hardwood Floors"},
            {"category": "Interior Features",    "name": "Oversized Windows"},
            {"category": "Interior Features",    "name": "City Views"},
            {"category": "Kitchen & Appliances", "name": "Stainless Steel Appliances"},
            {"category": "Kitchen & Appliances", "name": "Granite Countertops"},
            {"category": "Community & Building", "name": "Full-Service Building"},
            {"category": "Security & Access",    "name": "Doorman"},
        ],
    },

    # ── 3 ─────────────────────────────────────────────────────────────────────
    {
        "id": "prop_003",
        "data": {
            "title": "1BD Luxury Condo at W Downtown Residences, Lower Manhattan",
            "description": (
                "Elegant one-bedroom at the W Downtown Residences, an iconic 56-story glass tower in Lower Manhattan. "
                "Starting above the 21st floor, every unit enjoys breathtaking up-close views of One World Trade Center, "
                "the Lower Manhattan skyline, and the Hudson River. The unit features luxury finishes, floor-to-ceiling "
                "windows, and premium appliances. Full-time doorman and concierge service. Built in 2010, this building "
                "defines the new Downtown Manhattan lifestyle with proximity to Tribeca, the Financial District, and the "
                "Hudson River Greenway."
            ),
            "type":         "condo",
            "listing_type": "for-rent",
            "status":       "available",
            "condition":    "excellent",
            "price":        Decimal("3100.00"),
            "price_label":  "/mo",
            "bedrooms":     1,
            "bathrooms":    Decimal("1.0"),
            "sqft":         708,
            "lot_size":     None,
            "year_built":   2010,
            "garage":       0,
            "stories":      56,
            "address":      "120 Washington St Unit 28H",
            "city":         "New York",
            "state":        "NY",
            "zip_code":     "10006",
            "neighborhood": "Financial District",
            "cross_street": "Washington St & Rector St",
            "latitude":     Decimal("40.7106"),
            "longitude":    Decimal("-74.0143"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":        False,
            "homepage_featured":  False,
        },
        "images": [
            {"url": "https://images1.apartments.com/i2/ta2ItQ1YkGq-mwrPLFtpy0dCOrnPVStZIn07BxIdkiE/111/123-washington-st-new-york-ny-primary-photo.jpg?p=1",   "caption": "W Downtown Residences exterior", "is_primary": True,  "order": 0},
            {"url": "https://images1.apartments.com/i2/NZvxWmQbGAH7x-k_gk_n_q1iv5ZXJZj5eS5WxPVL3rM/117/123-washington-st-new-york-ny-building-photo.jpg?p=1",  "caption": "Living room — WTC views",  "is_primary": False, "order": 1},
            {"url": "https://images1.apartments.com/i2/bTSLVka_dTLyXuglWu16qHBYmewXrMu894HVE6Kfq9w/117/123-washington-st-new-york-ny-building-photo.jpg?p=1",  "caption": "Kitchen",                      "is_primary": False, "order": 2},
            {"url": "https://images1.apartments.com/i2/8SAbHaH30i-SyhQYYCOdHotByo44n85z6YV9BxVlfpk/117/123-washington-st-new-york-ny-building-photo.jpg?p=1",  "caption": "Master bedroom",               "is_primary": False, "order": 3},
            {"url": "https://images1.apartments.com/i2/wTMO7MRajNx7r950WqhIIBy0aYV59erIgbyl2-J1-O4/117/123-washington-st-new-york-ny-building-photo.jpg?p=1",  "caption": "Building lobby",               "is_primary": False, "order": 4},
        ],
        "amenities": [
            {"category": "Community & Building", "name": "24-Hour Doorman"},
            {"category": "Community & Building", "name": "Concierge"},
            {"category": "Interior Features",    "name": "Floor-to-Ceiling Windows"},
            {"category": "Interior Features",    "name": "Luxury Finishes"},
            {"category": "Interior Features",    "name": "Hudson River Views"},
            {"category": "Kitchen & Appliances", "name": "Premium Appliances"},
        ],
    },

    # ── 4 ─────────────────────────────────────────────────────────────────────
    {
        "id": "prop_004",
        "data": {
            "title": "1BD Doorman Condo — Utilities Included, Upper East Side",
            "description": (
                "Spacious one-bedroom condominium in a full-service doorman building at Yorkville Tower 1 on Third "
                "Avenue. A rare find: gas and electric utilities are INCLUDED in the monthly rent, delivering "
                "exceptional value in New York City. Located at the border of the Upper East Side and East Harlem, "
                "this well-maintained building provides attentive staff and is superbly connected via the 4, 5, and "
                "6 trains and multiple bus lines. Groceries, dining, and parks are all within easy walking distance."
            ),
            "type":         "condo",
            "listing_type": "for-rent",
            "status":       "available",
            "condition":    "good",
            "price":        Decimal("1800.00"),
            "price_label":  "/mo",
            "bedrooms":     1,
            "bathrooms":    Decimal("1.0"),
            "sqft":         650,
            "lot_size":     None,
            "year_built":   1980,
            "garage":       0,
            "stories":      25,
            "address":      "1620 Third Ave Unit 21D",
            "city":         "New York",
            "state":        "NY",
            "zip_code":     "10035",
            "neighborhood": "East Harlem",
            "cross_street": "Third Ave & E 96th St",
            "latitude":     Decimal("40.7844"),
            "longitude":    Decimal("-73.9495"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":        False,
            "homepage_featured":  False,
        },
        "images": [
            {"url": "https://images1.apartments.com/i2/frE9ncjov7phTe1f5JzdYiM1BX0UF3Je8o6KRmZMzhc/111/1623-third-ave-new-york-ny-primary-photo.jpg?p=1",   "caption": "Yorkville Tower 1 exterior", "is_primary": True,  "order": 0},
            {"url": "https://images1.apartments.com/i2/i6i_Hx1_VabE7hKZMy9k-cf6tpdgCaDyW6gHnXaPoFY/111/1623-third-ave-new-york-ny-building-photo.jpg?p=1", "caption": "Living room",               "is_primary": False, "order": 1},
            {"url": "https://images1.apartments.com/i2/olXA6U0HrFfVRww_2z8Ja_86NH3ywNA2-V6mIFTLX1A/111/1623-third-ave-new-york-ny-building-photo.jpg?p=1", "caption": "Kitchen",                   "is_primary": False, "order": 2},
            {"url": "https://images1.apartments.com/i2/fjPy9IAIyfDl32ckgL6iPi-MuKRZGiRlpnpKUj4q-zY/111/1623-third-ave-new-york-ny-building-photo.jpg?p=1", "caption": "Bedroom",                   "is_primary": False, "order": 3},
        ],
        "amenities": [
            {"category": "Security & Access",  "name": "Doorman"},
            {"category": "Utilities & Climate","name": "Gas Included"},
            {"category": "Utilities & Climate","name": "Electric Included"},
            {"category": "Community & Building","name": "Elevator"},
        ],
    },

    # ── 5 ─────────────────────────────────────────────────────────────────────
    {
        "id": "prop_005",
        "data": {
            "title": "1BD Duplex Condo with Private Garden — Clinton Hill, Brooklyn",
            "description": (
                "Stunning 1,252 sq ft duplex condo in a boutique 16-unit building on Classon Avenue in Clinton Hill, "
                "Brooklyn. This legally configured one-bedroom home offers a rare private backyard garden, dishwasher, "
                "central A/C, and in-unit washer/dryer. The spacious lower level recreation room/den can easily be "
                "configured as a second bedroom or home office. One of Clinton Hill’s most sought-after blocks, "
                "within walking distance to Pratt Institute, Fort Greene Park, and an array of acclaimed restaurants "
                "and coffee shops."
            ),
            "type":         "condo",
            "listing_type": "for-rent",
            "status":       "available",
            "condition":    "excellent",
            "price":        Decimal("2550.00"),
            "price_label":  "/mo",
            "bedrooms":     1,
            "bathrooms":    Decimal("1.5"),
            "sqft":         1252,
            "lot_size":     None,
            "year_built":   2008,
            "garage":       0,
            "stories":      6,
            "address":      "512 Classon Ave Unit 1A",
            "city":         "Brooklyn",
            "state":        "NY",
            "zip_code":     "11238",
            "neighborhood": "Clinton Hill",
            "cross_street": "Classon Ave & Fulton St",
            "latitude":     Decimal("40.6826"),
            "longitude":    Decimal("-73.9596"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":        False,
            "homepage_featured":  False,
        },
        "images": [
            {"url": "https://images1.apartments.com/i2/708_a23rHIMCgIkhAij0sJVw52mN3nXMbAtt-FYlKZ0/111/516-classon-ave-brooklyn-ny-primary-photo.jpg?p=1",   "caption": "516 Classon Ave exterior", "is_primary": True,  "order": 0},
            {"url": "https://images1.apartments.com/i2/_XUdeZFIDWyfh6EVg3SyAEKwnyGJeIwPAkcfFWq2Mpk/117/516-classon-ave-brooklyn-ny-building-photo.jpg?p=1", "caption": "Living area",              "is_primary": False, "order": 1},
            {"url": "https://images1.apartments.com/i2/_KI-uRAJVlrHZh6eAzouRSWMftqbse9z7RChbANli3I/117/516-classon-ave-brooklyn-ny-building-photo.jpg?p=1", "caption": "Kitchen",                  "is_primary": False, "order": 2},
            {"url": "https://images1.apartments.com/i2/qp24FThUgn4IE2AB1mfoC5K504vpp4BYqIrz86bCVRc/117/516-classon-ave-brooklyn-ny-building-photo.jpg?p=1", "caption": "Private backyard garden",  "is_primary": False, "order": 3},
            {"url": "https://images1.apartments.com/i2/8D4dV7OXDlMRB7GUvcqkVIgF0eSzQHQNIasCVPJ7-lw/117/516-classon-ave-brooklyn-ny-building-photo.jpg?p=1", "caption": "Lower level den/office",   "is_primary": False, "order": 4},
        ],
        "amenities": [
            {"category": "Outdoor & Grounds",    "name": "Private Backyard Garden"},
            {"category": "Utilities & Climate",  "name": "Central A/C"},
            {"category": "Utilities & Climate",  "name": "In-unit Washer/Dryer"},
            {"category": "Kitchen & Appliances", "name": "Dishwasher"},
            {"category": "Interior Features",    "name": "Duplex Layout"},
            {"category": "Pet Policy",           "name": "Pets Allowed"},
        ],
    },

    # ── 6 ─────────────────────────────────────────────────────────────────────
    {
        "id": "prop_006",
        "data": {
            "title": "Renovated 1BD Condo Near Transit — Hallett’s Cove, Astoria",
            "description": (
                "Fully renovated one-bedroom condo in the historic Hallett’s Cove neighborhood of Astoria, Queens. "
                "Features a renovated kitchen with stainless steel appliances, a full bath, and ample closet space "
                "throughout. Located on a quiet residential street in a neighborhood once known as a recreational "
                "destination for Manhattan’s elite. Easy 10-minute walk to the Q/R train at 21st Station. Close "
                "to shops, restaurants, and the Astoria waterfront. A great value in one of Queens’ most "
                "desirable communities."
            ),
            "type":         "condo",
            "listing_type": "for-rent",
            "status":       "available",
            "condition":    "good",
            "price":        Decimal("2600.00"),
            "price_label":  "/mo",
            "bedrooms":     1,
            "bathrooms":    Decimal("1.0"),
            "sqft":         600,
            "lot_size":     None,
            "year_built":   1965,
            "garage":       0,
            "stories":      4,
            "address":      "35-32 10th St",
            "city":         "Astoria",
            "state":        "NY",
            "zip_code":     "11106",
            "neighborhood": "Hallett’s Cove",
            "cross_street": "10th St & 36th Ave",
            "latitude":     Decimal("40.7682"),
            "longitude":    Decimal("-73.9365"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":        False,
            "homepage_featured":  False,
        },
        "images": [
            {"url": "https://images1.apartments.com/i2/orOHsSy43lKvHmnfO2bE_xfMEpa7NuCH8JzGWYNl16s/111/35-31-35-10-10th-st-queens-ny-primary-photo.jpg?p=1",  "caption": "35-31 10th St exterior", "is_primary": True,  "order": 0},
            {"url": "https://images1.apartments.com/i2/5kj6c0hNywO2OC4aRD1-ThShdzq6Vn5wbm058nU-b4I/111/35-31-35-10-10th-st-queens-ny-building-photo.jpg?p=1", "caption": "Living room",            "is_primary": False, "order": 1},
            {"url": "https://images1.apartments.com/i2/dpaEqz4BkWrPu0SHIGyugcuZzKA_iPpkt8w5DjI-SPY/111/35-31-35-10-10th-st-queens-ny-building-photo.jpg?p=1", "caption": "Renovated kitchen",      "is_primary": False, "order": 2},
            {"url": "https://images1.apartments.com/i2/ZZctHV-uLu3L6BHfSCETLbI63VF1Rx18rVgBISvvg6U/111/35-31-35-10-10th-st-queens-ny-building-photo.jpg?p=1", "caption": "Bedroom",                "is_primary": False, "order": 3},
        ],
        "amenities": [
            {"category": "Kitchen & Appliances", "name": "Stainless Steel Appliances"},
            {"category": "Interior Features",    "name": "Renovated Interior"},
            {"category": "Interior Features",    "name": "Walk-in Closet"},
        ],
    },

    # ── 7 ─────────────────────────────────────────────────────────────────────
    {
        "id": "prop_007",
        "data": {
            "title": "1BD Condo at The Williamsburg — Iconic Wythe Ave, Brooklyn",
            "description": (
                "Contemporary one-bedroom condo at The Williamsburg, a full-service building on iconic Wythe Avenue "
                "in the heart of Williamsburg, Brooklyn. Open-plan living space with oversized windows flooding the "
                "home with natural light. The building features a rooftop terrace with sweeping Manhattan skyline "
                "views. Steps from the East River waterfront, boutique fashion, acclaimed restaurants, vibrant "
                "nightlife, and the L and G trains. Units range from 455–680 sq ft, priced starting at $2,675/month."
            ),
            "type":         "condo",
            "listing_type": "for-rent",
            "status":       "available",
            "condition":    "excellent",
            "price":        Decimal("2675.00"),
            "price_label":  "/mo",
            "bedrooms":     1,
            "bathrooms":    Decimal("1.0"),
            "sqft":         560,
            "lot_size":     None,
            "year_built":   2014,
            "garage":       0,
            "stories":      8,
            "address":      "375 Wythe Ave",
            "city":         "Brooklyn",
            "state":        "NY",
            "zip_code":     "11249",
            "neighborhood": "Williamsburg",
            "cross_street": "Wythe Ave & S 4th St",
            "latitude":     Decimal("40.7148"),
            "longitude":    Decimal("-73.9645"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":        False,
            "homepage_featured":  False,
        },
        "images": [
            {"url": "https://images1.apartments.com/i2/HrAR91B3lZUuth-scBG9p4s9nEsRQIIbAIZUpPB5UlU/111/the-williamsburg-brooklyn-ny-primary-photo.jpg?p=1", "caption": "The Williamsburg building exterior", "is_primary": True, "order": 0},
        ],
        "amenities": [
            {"category": "Outdoor & Grounds",    "name": "Rooftop Terrace"},
            {"category": "Interior Features",    "name": "Oversized Windows"},
            {"category": "Interior Features",    "name": "Open Floor Plan"},
            {"category": "Community & Building", "name": "Full-Service Building"},
        ],
    },

    # ── 8 ─────────────────────────────────────────────────────────────────────
    {
        "id": "prop_008",
        "data": {
            "title": "Spacious 1BD Condo in East Williamsburg, Brooklyn",
            "description": (
                "Large and light-filled one-bedroom condo in a well-maintained 6-story building in East Williamsburg. "
                "Features a big living room, a generously sized bedroom, windows in every room, a large eat-in kitchen "
                "with stainless steel appliances, and an oversized bathroom with a window — a rare NYC luxury. "
                "Ideally located steps from the J/M/Z trains and within easy reach of the thriving Bushwick art scene, "
                "local coffee shops, and diverse dining. Priced well below the Williamsburg market average."
            ),
            "type":         "condo",
            "listing_type": "for-rent",
            "status":       "available",
            "condition":    "good",
            "price":        Decimal("1900.00"),
            "price_label":  "/mo",
            "bedrooms":     1,
            "bathrooms":    Decimal("1.0"),
            "sqft":         750,
            "lot_size":     None,
            "year_built":   1924,
            "garage":       0,
            "stories":      6,
            "address":      "396 Hooper St Apt 1F",
            "city":         "Brooklyn",
            "state":        "NY",
            "zip_code":     "11211",
            "neighborhood": "East Williamsburg",
            "cross_street": "Hooper St & Borinquen Pl",
            "latitude":     Decimal("40.7077"),
            "longitude":    Decimal("-73.9441"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":        False,
            "homepage_featured":  False,
        },
        "images": [
            {"url": "https://images1.apartments.com/i2/6EoUfLB5FXihbozerFir_Xn9-HL5i3ou8tBba-ln5Kc/111/390-hooper-st-brooklyn-ny-primary-photo.jpg?p=1",   "caption": "390 Hooper St exterior", "is_primary": True,  "order": 0},
            {"url": "https://images1.apartments.com/i2/wt_XHhLAmNF9Cojy-f2q6ZJEJeDCgt9vsgnloCah7Io/117/390-hooper-st-brooklyn-ny-building-photo.jpg?p=1", "caption": "Living room",            "is_primary": False, "order": 1},
            {"url": "https://images1.apartments.com/i2/iQyG_p50fVq_FpygiUdXo792SOhx6RUmCr6YdLFfrBA/117/390-hooper-st-brooklyn-ny-building-photo.jpg?p=1", "caption": "Eat-in kitchen",         "is_primary": False, "order": 2},
            {"url": "https://images1.apartments.com/i2/POBTBgRzUDrYKSTDlcMpJoPO_Qj2DcfaWmO4ND3mmaU/117/390-hooper-st-brooklyn-ny-building-photo.jpg?p=1", "caption": "Bedroom",                "is_primary": False, "order": 3},
            {"url": "https://images1.apartments.com/i2/yroHrQriCVqmHLzpC7-v0LZPLrdJ0iLuw0RQwIBEVnw/117/390-hooper-st-brooklyn-ny-building-photo.jpg?p=1", "caption": "Bathroom",               "is_primary": False, "order": 4},
        ],
        "amenities": [
            {"category": "Kitchen & Appliances", "name": "Stainless Steel Appliances"},
            {"category": "Kitchen & Appliances", "name": "Eat-in Kitchen"},
            {"category": "Interior Features",    "name": "Large Bathroom with Window"},
            {"category": "Interior Features",    "name": "Windows in Every Room"},
        ],
    },

    # ── 9 ─────────────────────────────────────────────────────────────────────
    {
        "id": "prop_009",
        "data": {
            "title": "1BD Condo on 31st St — Astoria, Queens",
            "description": (
                "Well-appointed third-floor one-bedroom condo on 31st Street in Astoria, Queens. Modern finishes "
                "throughout with a functional layout and good natural light. Just steps from the N/W trains on "
                "31st Street, offering a quick and direct commute to Midtown Manhattan. Astoria’s vibrant dining "
                "scene — known for Greek, Mediterranean, and international cuisine — parks, and cultural "
                "institutions including the Museum of the Moving Image are all within easy reach."
            ),
            "type":         "condo",
            "listing_type": "for-rent",
            "status":       "available",
            "condition":    "good",
            "price":        Decimal("2100.00"),
            "price_label":  "/mo",
            "bedrooms":     1,
            "bathrooms":    Decimal("1.0"),
            "sqft":         580,
            "lot_size":     None,
            "year_built":   1970,
            "garage":       0,
            "stories":      6,
            "address":      "31-38 31st St Unit 308",
            "city":         "Astoria",
            "state":        "NY",
            "zip_code":     "11106",
            "neighborhood": "Astoria",
            "cross_street": "31st St & 31st Ave",
            "latitude":     Decimal("40.7657"),
            "longitude":    Decimal("-73.9322"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":        False,
            "homepage_featured":  False,
        },
        "images": [
            {"url": "https://images1.apartments.com/i2/LpPXIOBzI278Y_qCGDGM1xwhTUzESpVYxefnQ56Ljvw/111/31-35-35-31st-st-queens-ny-primary-photo.jpg?p=1",   "caption": "Astor Condo exterior", "is_primary": True,  "order": 0},
            {"url": "https://images1.apartments.com/i2/0qz3U1daVeB-VJfTFZGxqQBGDs2yShPf23JTbDy1XBs/117/31-35-35-31st-st-queens-ny-building-photo.jpg?p=1", "caption": "Living room",          "is_primary": False, "order": 1},
            {"url": "https://images1.apartments.com/i2/QV-8GoMCPl7Yu249fcpC7Jex1YjRK4WjOeQL1LlR1Ls/117/31-35-35-31st-st-queens-ny-building-photo.jpg?p=1", "caption": "Kitchen",              "is_primary": False, "order": 2},
            {"url": "https://images1.apartments.com/i2/ifndT_0y2nhlu5YB1pH6EsHWp5w6B4ZqKJYhgg2DEmI/117/31-35-35-31st-st-queens-ny-building-photo.jpg?p=1", "caption": "Bedroom",              "is_primary": False, "order": 3},
            {"url": "https://images1.apartments.com/i2/LJXX-ZcW22z82R1J4a6oX55cEtgAJqrBpwV_RcfJJuQ/117/31-35-35-31st-st-queens-ny-building-photo.jpg?p=1", "caption": "Building hallway",    "is_primary": False, "order": 4},
        ],
        "amenities": [
            {"category": "Interior Features",    "name": "Modern Finishes"},
            {"category": "Community & Building", "name": "Elevator"},
        ],
    },

    # ── 10 ────────────────────────────────────────────────────────────────────
    {
        "id": "prop_010",
        "data": {
            "title": "Brand New 1BD Condo at Queens Plaza — Long Island City, NY",
            "description": (
                "Newly constructed 2025 one-bedroom condominium in the heart of Long Island City, offering "
                "cutting-edge design and premium finishes throughout. Floor-to-ceiling windows, open kitchen with "
                "quartz countertops, and in-unit washer/dryer. The 19-story building features a rooftop lounge with "
                "breathtaking Manhattan skyline views, a state-of-the-art fitness center, and concierge service. "
                "Located at Queens Plaza North, steps from the 7, E, M, R, and N trains — just a 10-minute "
                "commute to Midtown Manhattan."
            ),
            "type":         "condo",
            "listing_type": "for-rent",
            "status":       "available",
            "condition":    "new",
            "price":        Decimal("2400.00"),
            "price_label":  "/mo",
            "bedrooms":     1,
            "bathrooms":    Decimal("1.0"),
            "sqft":         720,
            "lot_size":     None,
            "year_built":   2025,
            "garage":       0,
            "stories":      19,
            "address":      "22-01 Queens Plaza North Unit 5C",
            "city":         "Long Island City",
            "state":        "NY",
            "zip_code":     "11101",
            "neighborhood": "Long Island City",
            "cross_street": "Queens Plaza N & Crescent St",
            "latitude":     Decimal("40.7480"),
            "longitude":    Decimal("-73.9353"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":        False,
            "homepage_featured":  False,
        },
        "images": [
            {"url": "https://photos.zillowstatic.com/fp/f5db7f3fa62010cfd0a7b5df0e863965-se_large_800_400.webp",  "caption": "Radiant LIC exterior",              "is_primary": True,  "order": 0},
            {"url": "https://photos.zillowstatic.com/fp/424fed9abf5c57c76ce08912d5562ce7-se_medium_500_250.webp", "caption": "Living room — Manhattan views", "is_primary": False, "order": 1},
            {"url": "https://photos.zillowstatic.com/fp/b8b97f771cbad79eaf95f488328bc1a1-se_medium_500_250.webp", "caption": "Open kitchen with quartz counters",  "is_primary": False, "order": 2},
            {"url": "https://photos.zillowstatic.com/fp/c2de670ce30e2bc4c4da160fd1f44f44-se_medium_500_250.webp", "caption": "Bedroom",                           "is_primary": False, "order": 3},
            {"url": "https://photos.zillowstatic.com/fp/8673b5138bd560b2b9b646b8be45c5e9-p_e.webp",              "caption": "Rooftop terrace",                   "is_primary": False, "order": 4},
        ],
        "amenities": [
            {"category": "Interior Features",    "name": "Floor-to-Ceiling Windows"},
            {"category": "Interior Features",    "name": "Manhattan Skyline Views"},
            {"category": "Kitchen & Appliances", "name": "Quartz Countertops"},
            {"category": "Utilities & Climate",  "name": "In-unit Washer/Dryer"},
            {"category": "Community & Building", "name": "Rooftop Lounge"},
            {"category": "Community & Building", "name": "Fitness Center"},
            {"category": "Community & Building", "name": "Concierge"},
        ],
    },
]


class Command(BaseCommand):
    help = "Import 10 NYC condo listings (Manhattan, Brooklyn, Queens) into the database."

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
            help="Email of the agent to assign to all listings (must exist in the database).",
        )
        parser.add_argument(
            "--skip-images",
            action="store_true",
            default=False,
            help="Skip image uploading (useful for quick test runs).",
        )
        parser.add_argument(
            "--reset-images",
            action="store_true",
            default=False,
            help="Delete and re-upload images for properties that already exist (fixes broken images).",
        )

    def handle(self, *args, **options):
        agent_email  = options["agent_email"]
        is_published = options["published"]
        is_featured  = options["featured"]
        skip_images  = options["skip_images"]
        reset_images = options["reset_images"]

        # ── 1. Resolve agent ───────────────────────────────────────────────────
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

        # ── 2. Ensure amenity categories exist ─────────────────────────────────
        cat_map: dict[str, AmenityCategory] = {}
        for cat_def in AMENITY_CATEGORIES:
            obj, created = AmenityCategory.objects.get_or_create(
                name=cat_def["name"],
                defaults={"icon": cat_def["icon"], "order": cat_def["order"]},
            )
            cat_map[cat_def["name"]] = obj
            if created:
                self.stdout.write(f"  Created category: {obj.name}")

        # ── 3. Import properties ───────────────────────────────────────────────
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

            # ── Images ────────────────────────────────────────────────────────
            img_count = 0
            if not skip_images:
                image_objs = []
                for img in listing["images"]:
                    try:
                        result = cloudinary.uploader.upload(
                            img["url"],
                            folder="properties/nyc",
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
                        stored = img["url"]  # fallback — raw URL stored as-is

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

            # ── Amenities ─────────────────────────────────────────────────────
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

        # ── 4. Summary ─────────────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== IMPORT COMPLETE ==="))
        self.stdout.write(self.style.SUCCESS(f"Properties created : {created_count}"))
        self.stdout.write(self.style.SUCCESS(f"Properties skipped : {skipped_count}"))
        if reset_images:
            self.stdout.write(self.style.SUCCESS(f"Images reset on    : {len(LISTINGS) - skipped_count - created_count} existing properties"))
        self.stdout.write(self.style.SUCCESS(f"Images attached    : {total_images}"))
        self.stdout.write(self.style.SUCCESS(f"Amenities attached : {total_amenities}"))
        self.stdout.write(self.style.SUCCESS(f"Published          : {is_published}"))
        if not is_published:
            self.stdout.write(
                self.style.WARNING(
                    "\nListings are unpublished. Review in admin, then set is_published=True to go live.\n"
                    "Admin: https://admin.haskerrealtygroup.com/admin/properties/property/"
                )
            )
