"""
seed.py
───────
Master demo seed — creates users, amenity categories, and 10 showcase
properties, each with a full image gallery (5-8 photos) stored via raw SQL
to avoid CloudinaryField mangling external image URLs.

Usage:
    python manage.py seed            # fresh seed (clears everything first)
    python manage.py seed --keep-users   # keep existing users, recreate properties
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection

from apps.accounts.models import Role
from apps.properties.models import AmenityCategory, Property, PropertyAmenity, PropertyImage

User = get_user_model()


# ── Raw SQL image helper ─────────────────────────────────────────────────────

def _insert_images(property_id: int, images: list[dict]) -> int:
    """
    Insert PropertyImage rows via raw SQL.
    Bypasses CloudinaryField.to_python() which mangles external CDN URLs.
    Each dict: {url, caption, is_primary, order}
    """
    clean = [
        img for img in images
        if img.get("url") and img["url"].startswith("https://")
    ]
    if not clean:
        return 0
    q = connection.ops.quote_name
    sql = (
        f"INSERT INTO {q('properties_propertyimage')} "
        f"({q('property_id')}, {q('image')}, {q('caption')}, "
        f"{q('is_primary')}, {q('order')}) "
        f"VALUES (%s, %s, %s, %s, %s)"
    )
    rows = [
        (property_id, img["url"], img.get("caption", ""), img.get("is_primary", False), img["order"])
        for img in clean
    ]
    with connection.cursor() as cur:
        cur.executemany(sql, rows)
    return len(rows)


# ── Property data ────────────────────────────────────────────────────────────

CATEGORIES = [
    ("home",      "Home Features",         "Home",     0),
    ("kitchen",   "Kitchen Features",      "ChefHat",  1),
    ("utility",   "Utility & Maintenance", "Zap",      2),
    ("community", "Community Features",    "Users",    3),
    ("pet",       "Pet Policy",            "PawPrint", 4),
]

PROPERTIES = [
    # ── 1 · Atlanta, GA — 3-Bed House for Rent ───────────────────────────────
    {
        "data": {
            "title":        "Spacious 3-Bed Home in East Atlanta Village",
            "slug":         "spacious-3bed-east-atlanta-village",
            "type":         "residential",
            "listing_type": "for-rent",
            "status":       "available",
            "condition":    "good",
            "price":        Decimal("1850"),
            "price_label":  "/mo",
            "bedrooms":     3,
            "bathrooms":    Decimal("2.0"),
            "sqft":         1420,
            "lot_size":     None,
            "year_built":   1998,
            "garage":       1,
            "stories":      2,
            "address":      "742 Peachtree Rd NE",
            "city":         "Atlanta",
            "state":        "GA",
            "zip_code":     "30306",
            "neighborhood": "East Atlanta Village",
            "cross_street": "Moreland Ave",
            "latitude":     Decimal("33.7490"),
            "longitude":    Decimal("-84.3880"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":       True,
            "homepage_featured": True,
            "is_published":      True,
            "description": (
                "Bright and airy 3-bedroom home just minutes from Ponce City Market and the Atlanta BeltLine. "
                "Fully updated kitchen with granite countertops and stainless appliances, large fenced backyard "
                "perfect for entertaining, and covered carport parking. Hardwood floors throughout the main level. "
                "Central A/C, in-unit laundry, and walk-in closet in the primary bedroom. "
                "Pets welcome with deposit. Easy access to I-20 and MARTA."
            ),
        },
        "amenities": {
            "home":      ["Central Air", "Hardwood Floors", "In-Unit Laundry", "Walk-in Closet", "Fenced Backyard"],
            "kitchen":   ["Granite Countertops", "Stainless Appliances", "Dishwasher", "Refrigerator Included"],
            "utility":   ["Trash Pickup Included", "Lawn Care Included"],
            "community": ["Street Parking", "Near BeltLine Trail"],
            "pet":       ["Dogs Allowed", "Cats Allowed", "Pet Deposit Required"],
        },
        "images": [
            {"url": "https://images.unsplash.com/photo-1568605114967-8130f3a36994?w=1200&q=85",
             "caption": "Front exterior — 742 Peachtree Rd NE", "is_primary": True,  "order": 0},
            {"url": "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=1200&q=85",
             "caption": "Spacious living room with hardwood floors",  "is_primary": False, "order": 1},
            {"url": "https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?w=1200&q=85",
             "caption": "Updated kitchen with granite countertops",   "is_primary": False, "order": 2},
            {"url": "https://images.unsplash.com/photo-1616594039964-ae9021a400a0?w=1200&q=85",
             "caption": "Primary bedroom with walk-in closet",        "is_primary": False, "order": 3},
            {"url": "https://images.unsplash.com/photo-1552321554-5fefe8c9ef14?w=1200&q=85",
             "caption": "Full bathroom — updated fixtures",           "is_primary": False, "order": 4},
            {"url": "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?w=1200&q=85",
             "caption": "Fenced backyard with patio",                 "is_primary": False, "order": 5},
        ],
    },

    # ── 2 · Charlotte, NC — 2-Bed Apartment for Rent ─────────────────────────
    {
        "data": {
            "title":        "Modern 2-Bed Apartment in Uptown Charlotte",
            "slug":         "modern-2bed-uptown-charlotte",
            "type":         "condo",
            "listing_type": "for-rent",
            "status":       "available",
            "condition":    "excellent",
            "price":        Decimal("1450"),
            "price_label":  "/mo",
            "bedrooms":     2,
            "bathrooms":    Decimal("2.0"),
            "sqft":         980,
            "lot_size":     None,
            "year_built":   2019,
            "garage":       1,
            "stories":      1,
            "address":      "301 S Tryon St",
            "city":         "Charlotte",
            "state":        "NC",
            "zip_code":     "28202",
            "neighborhood": "Uptown",
            "cross_street": "Stonewall St",
            "latitude":     Decimal("35.2271"),
            "longitude":    Decimal("-80.8431"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":       True,
            "homepage_featured": False,
            "is_published":      True,
            "description": (
                "Contemporary 2-bedroom, 2-bath apartment in the heart of Uptown Charlotte. "
                "Floor-to-ceiling windows, in-unit washer/dryer, and an open chef's kitchen with quartz countertops. "
                "Building amenities include a rooftop pool with city skyline views, fully equipped fitness center, "
                "24-hour concierge, and secured covered parking. Walking distance to Bank of America Stadium, "
                "Spectrum Center, and the best Uptown restaurants and nightlife. Pets welcome."
            ),
        },
        "amenities": {
            "home":      ["Central Air", "In-Unit Laundry", "Balcony", "Floor-to-Ceiling Windows", "High-Speed Internet Ready"],
            "kitchen":   ["Quartz Countertops", "Stainless Appliances", "Gas Range", "Microwave"],
            "community": ["Rooftop Pool", "Fitness Center", "24/7 Concierge", "Package Lockers", "Secured Parking"],
            "pet":       ["Cats Allowed", "Small Dogs (under 25 lbs)"],
        },
        "images": [
            {"url": "https://images.unsplash.com/photo-1512918728651-35e3b48e6a9f?w=1200&q=85",
             "caption": "Building exterior — 301 S Tryon St",        "is_primary": True,  "order": 0},
            {"url": "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=1200&q=85",
             "caption": "Open-plan living room with city views",      "is_primary": False, "order": 1},
            {"url": "https://images.unsplash.com/photo-1556909172-54557c7e4fb7?w=1200&q=85",
             "caption": "Chef's kitchen with quartz countertops",     "is_primary": False, "order": 2},
            {"url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=1200&q=85",
             "caption": "Primary bedroom",                            "is_primary": False, "order": 3},
            {"url": "https://images.unsplash.com/photo-1584622650111-993a426fbf0a?w=1200&q=85",
             "caption": "En-suite bathroom",                          "is_primary": False, "order": 4},
            {"url": "https://images.unsplash.com/photo-1571939228382-b2f2b585ce15?w=1200&q=85",
             "caption": "Rooftop pool with skyline views",            "is_primary": False, "order": 5},
        ],
    },

    # ── 3 · Houston, TX — 1-Bed Apartment for Rent ───────────────────────────
    {
        "data": {
            "title":        "Cozy 1-Bed Near Houston Medical Center",
            "slug":         "cozy-1bed-houston-medical-center",
            "type":         "condo",
            "listing_type": "for-rent",
            "status":       "available",
            "condition":    "good",
            "price":        Decimal("950"),
            "price_label":  "/mo",
            "bedrooms":     1,
            "bathrooms":    Decimal("1.0"),
            "sqft":         620,
            "lot_size":     None,
            "year_built":   2005,
            "garage":       0,
            "stories":      1,
            "address":      "5800 Almeda Rd",
            "city":         "Houston",
            "state":        "TX",
            "zip_code":     "77004",
            "neighborhood": "Museum District",
            "cross_street": "Old Spanish Trail",
            "latitude":     Decimal("29.7107"),
            "longitude":    Decimal("-95.3850"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":       False,
            "homepage_featured": False,
            "is_published":      True,
            "description": (
                "Affordable, well-maintained 1-bedroom apartment in Houston's Museum District — "
                "steps from Hermann Park, the Museum of Fine Arts, and the Houston Zoo. "
                "On-site laundry, gated community, and covered parking available. "
                "Water and trash included in rent. METRORail Red Line at your doorstep makes "
                "commuting to the Texas Medical Center and Downtown effortless. No smoking. "
                "Small pets considered with additional deposit."
            ),
        },
        "amenities": {
            "home":      ["Central Air", "Ceiling Fans", "Carpet / Tile Flooring"],
            "kitchen":   ["Dishwasher", "Refrigerator Included", "Electric Range"],
            "utility":   ["Water & Trash Included", "On-Site Laundry"],
            "community": ["Gated Community", "Swimming Pool", "METRORail Access", "Covered Parking"],
            "pet":       ["Small Pets Considered", "Pet Deposit Required"],
        },
        "images": [
            {"url": "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=1200&q=85",
             "caption": "Apartment exterior — gated community",   "is_primary": True,  "order": 0},
            {"url": "https://images.unsplash.com/photo-1598928506311-c55ded91a20c?w=1200&q=85",
             "caption": "Living and dining area",                 "is_primary": False, "order": 1},
            {"url": "https://images.unsplash.com/photo-1565183997392-2f6f122e5912?w=1200&q=85",
             "caption": "Kitchen with full appliances",           "is_primary": False, "order": 2},
            {"url": "https://images.unsplash.com/photo-1489171078254-c3365d6e359f?w=1200&q=85",
             "caption": "Bedroom with ample closet space",        "is_primary": False, "order": 3},
            {"url": "https://images.unsplash.com/photo-1575429198097-0414ec08e8cd?w=1200&q=85",
             "caption": "Community swimming pool",                "is_primary": False, "order": 4},
        ],
    },

    # ── 4 · Scottsdale, AZ — 4-Bed House for Sale ────────────────────────────
    {
        "data": {
            "title":        "4-Bed Desert Oasis For Sale in Old Town Scottsdale",
            "slug":         "4bed-desert-oasis-scottsdale",
            "type":         "residential",
            "listing_type": "for-sale",
            "status":       "available",
            "condition":    "excellent",
            "price":        Decimal("489000"),
            "price_label":  "",
            "bedrooms":     4,
            "bathrooms":    Decimal("3.0"),
            "sqft":         2640,
            "lot_size":     Decimal("0.35"),
            "year_built":   2015,
            "garage":       3,
            "stories":      1,
            "address":      "9800 E McDowell Rd",
            "city":         "Scottsdale",
            "state":        "AZ",
            "zip_code":     "85256",
            "neighborhood": "Old Town Scottsdale",
            "cross_street": "Pima Rd",
            "latitude":     Decimal("33.4942"),
            "longitude":    Decimal("-111.9261"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":       True,
            "homepage_featured": True,
            "is_published":      True,
            "description": (
                "Stunning single-story 4-bedroom home with private pool and McDowell Mountain views. "
                "Open-plan great room with vaulted ceilings flows into a chef's kitchen featuring a "
                "6-burner gas range, double wall oven, granite countertops, and a large center island. "
                "Primary suite with spa-style bath and direct pool access. "
                "Three-car garage, 0.35-acre lot with low-maintenance desert landscaping. "
                "HOA community with tennis courts, walking trails, and 24/7 gated entry. "
                "Minutes from Old Town dining, Scottsdale Fashion Square, and TPC Scottsdale."
            ),
        },
        "amenities": {
            "home":      ["Private Pool", "Mountain Views", "Smart Home System", "Solar Panels", "Walk-in Closet", "Vaulted Ceilings"],
            "kitchen":   ["Chef's Kitchen", "Granite Countertops", "Wine Refrigerator", "Double Oven", "Gas Range", "Kitchen Island"],
            "community": ["HOA Community", "Gated Entry", "Tennis Courts", "Walking Trails"],
            "utility":   ["Central A/C", "Solar-Powered Water Heater"],
            "pet":       ["Dogs Allowed", "Cats Allowed"],
        },
        "images": [
            {"url": "https://images.unsplash.com/photo-1583608205776-bfd35f0d9f83?w=1200&q=85",
             "caption": "Exterior — pool and desert landscaping",        "is_primary": True,  "order": 0},
            {"url": "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=1200&q=85",
             "caption": "Front of home with 3-car garage",               "is_primary": False, "order": 1},
            {"url": "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=1200&q=85",
             "caption": "Great room with vaulted ceilings",               "is_primary": False, "order": 2},
            {"url": "https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?w=1200&q=85",
             "caption": "Chef's kitchen with granite island",             "is_primary": False, "order": 3},
            {"url": "https://images.unsplash.com/photo-1616594039964-ae9021a400a0?w=1200&q=85",
             "caption": "Primary suite with pool access",                 "is_primary": False, "order": 4},
            {"url": "https://images.unsplash.com/photo-1552321554-5fefe8c9ef14?w=1200&q=85",
             "caption": "Spa-style primary bathroom",                     "is_primary": False, "order": 5},
            {"url": "https://images.unsplash.com/photo-1575429198097-0414ec08e8cd?w=1200&q=85",
             "caption": "Private pool with mountain views",               "is_primary": False, "order": 6},
        ],
    },

    # ── 5 · Nashville, TN — 2-Bed Townhouse for Rent ─────────────────────────
    {
        "data": {
            "title":        "Stylish 2-Bed Townhouse in The Gulch",
            "slug":         "stylish-2bed-townhouse-nashville-gulch",
            "type":         "townhouse",
            "listing_type": "for-rent",
            "status":       "available",
            "condition":    "excellent",
            "price":        Decimal("2100"),
            "price_label":  "/mo",
            "bedrooms":     2,
            "bathrooms":    Decimal("2.5"),
            "sqft":         1280,
            "lot_size":     None,
            "year_built":   2021,
            "garage":       1,
            "stories":      2,
            "address":      "1100 Division St",
            "city":         "Nashville",
            "state":        "TN",
            "zip_code":     "37203",
            "neighborhood": "The Gulch",
            "cross_street": "12th Ave S",
            "latitude":     Decimal("36.1492"),
            "longitude":    Decimal("-86.7908"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":       True,
            "homepage_featured": False,
            "is_published":      True,
            "description": (
                "Trendy 2-story townhouse in Nashville's most coveted neighborhood, The Gulch. "
                "Rooftop terrace with skyline views, attached 1-car garage, and an open kitchen "
                "with quartz countertops and a gas range. Hardwood floors throughout, "
                "in-unit washer/dryer, and a smart thermostat. Two spacious bedrooms, "
                "2.5 bathrooms. Steps from award-winning restaurants, live music venues, "
                "Whole Foods, and the SoBro greenway. Tenant pays electric and gas; "
                "water and trash included. One dog under 50 lbs welcome."
            ),
        },
        "amenities": {
            "home":      ["Rooftop Terrace", "Hardwood Floors", "In-Unit Laundry", "Smart Thermostat", "Attached Garage"],
            "kitchen":   ["Quartz Countertops", "Gas Range", "Wine Refrigerator", "Stainless Appliances"],
            "utility":   ["Water & Trash Included"],
            "community": ["Walkable Neighborhood", "Near Greenway Trail"],
            "pet":       ["Dogs Allowed (under 50 lbs)", "Cats Allowed", "Pet Deposit Required"],
        },
        "images": [
            {"url": "https://images.unsplash.com/photo-1570129477492-45c003edd2be?w=1200&q=85",
             "caption": "Townhouse exterior — The Gulch",               "is_primary": True,  "order": 0},
            {"url": "https://images.unsplash.com/photo-1493809842364-78817add7ffb?w=1200&q=85",
             "caption": "Open-plan kitchen and dining",                 "is_primary": False, "order": 1},
            {"url": "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=1200&q=85",
             "caption": "Modern living room — hardwood floors",         "is_primary": False, "order": 2},
            {"url": "https://images.unsplash.com/photo-1616594039964-ae9021a400a0?w=1200&q=85",
             "caption": "Primary bedroom",                              "is_primary": False, "order": 3},
            {"url": "https://images.unsplash.com/photo-1449844908441-8829872d2607?w=1200&q=85",
             "caption": "Rooftop terrace with Nashville skyline views", "is_primary": False, "order": 4},
        ],
    },

    # ── 6 · Miami, FL — 3-Bed Waterfront Condo for Sale ──────────────────────
    {
        "data": {
            "title":        "3-Bed Waterfront Condo in Brickell with Bay Views",
            "slug":         "3bed-waterfront-condo-brickell-miami",
            "type":         "condo",
            "listing_type": "for-sale",
            "status":       "available",
            "condition":    "new",
            "price":        Decimal("725000"),
            "price_label":  "",
            "bedrooms":     3,
            "bathrooms":    Decimal("2.0"),
            "sqft":         1680,
            "lot_size":     None,
            "year_built":   2022,
            "garage":       2,
            "stories":      1,
            "address":      "801 Brickell Key Dr",
            "city":         "Miami",
            "state":        "FL",
            "zip_code":     "33131",
            "neighborhood": "Brickell",
            "cross_street": "SE 8th St",
            "latitude":     Decimal("25.7617"),
            "longitude":    Decimal("-80.1918"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":       False,
            "homepage_featured": False,
            "is_published":      True,
            "description": (
                "Luxury waterfront condo with unobstructed Biscayne Bay and Miami skyline views. "
                "Floor-to-ceiling impact glass, Italian-designed kitchen with Miele appliances and "
                "marble countertops, and wide-plank white oak flooring throughout. "
                "Primary suite with spa bath featuring a soaking tub and dual vanity. "
                "Two assigned parking spaces, private storage unit, and two covered balconies. "
                "Resort-style amenities: infinity-edge pool, full-service spa, valet parking, "
                "24/7 concierge, and a state-of-the-art fitness center. "
                "Walking distance to Brickell City Centre and Mary Brickell Village."
            ),
        },
        "amenities": {
            "home":      ["Bay Views", "Floor-to-Ceiling Windows", "Private Balcony", "Smart Home", "Impact Glass", "Oak Flooring"],
            "kitchen":   ["Miele Appliances", "Marble Countertops", "Italian Cabinetry", "Wine Cooler", "Island"],
            "community": ["Infinity Pool", "Full-Service Spa", "Valet Parking", "Fitness Center", "24/7 Concierge"],
            "utility":   ["Central A/C", "In-Unit Laundry"],
            "pet":       ["Pets Allowed (breed restrictions apply)"],
        },
        "images": [
            {"url": "https://images.unsplash.com/photo-1613490493576-7fde63acd811?w=1200&q=85",
             "caption": "Luxury condo exterior — Brickell Key",         "is_primary": True,  "order": 0},
            {"url": "https://images.unsplash.com/photo-1560185127-6ed189bf02f4?w=1200&q=85",
             "caption": "Living room with floor-to-ceiling bay views",  "is_primary": False, "order": 1},
            {"url": "https://images.unsplash.com/photo-1556909172-54557c7e4fb7?w=1200&q=85",
             "caption": "Italian kitchen with marble countertops",       "is_primary": False, "order": 2},
            {"url": "https://images.unsplash.com/photo-1616594039964-ae9021a400a0?w=1200&q=85",
             "caption": "Primary suite with spa bathroom",               "is_primary": False, "order": 3},
            {"url": "https://images.unsplash.com/photo-1584622650111-993a426fbf0a?w=1200&q=85",
             "caption": "Spa bath with soaking tub",                    "is_primary": False, "order": 4},
            {"url": "https://images.unsplash.com/photo-1575429198097-0414ec08e8cd?w=1200&q=85",
             "caption": "Infinity-edge pool with bay view",             "is_primary": False, "order": 5},
            {"url": "https://images.unsplash.com/photo-1449844908441-8829872d2607?w=1200&q=85",
             "caption": "Private balcony overlooking Biscayne Bay",     "is_primary": False, "order": 6},
        ],
    },

    # ── 7 · Virginia Beach, VA — 3-Bed Beach Cottage for Rent ────────────────
    {
        "data": {
            "title":        "3-Bed Beach Cottage — Minutes from the Oceanfront",
            "slug":         "3bed-beach-cottage-virginia-beach",
            "type":         "residential",
            "listing_type": "for-rent",
            "status":       "available",
            "condition":    "good",
            "price":        Decimal("2200"),
            "price_label":  "/mo",
            "bedrooms":     3,
            "bathrooms":    Decimal("2.0"),
            "sqft":         1380,
            "lot_size":     None,
            "year_built":   2002,
            "garage":       0,
            "stories":      1,
            "address":      "213 Bob Ln",
            "city":         "Virginia Beach",
            "state":        "VA",
            "zip_code":     "23454",
            "neighborhood": "Oceanfront District",
            "cross_street": "Atlantic Ave",
            "latitude":     Decimal("36.8529"),
            "longitude":    Decimal("-75.9780"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":       True,
            "homepage_featured": False,
            "is_published":      True,
            "description": (
                "Charming 3-bedroom beach cottage just blocks from the Atlantic Ocean. "
                "Large wraparound deck, outdoor shower, bike storage for 4, and a fully "
                "equipped kitchen. Light-filled open floor plan with coastal décor. "
                "Perfect for families relocating to Hampton Roads — summer and annual "
                "leases available. Water, trash, and lawn care included. "
                "Minutes from the Virginia Beach Boardwalk, restaurants, and shopping. "
                "Cats and small dogs welcome with deposit."
            ),
        },
        "amenities": {
            "home":      ["Wraparound Deck", "Ceiling Fans", "Bike Storage", "Outdoor Shower"],
            "kitchen":   ["Full Kitchen", "Dishwasher", "Refrigerator"],
            "utility":   ["Water & Trash Included", "Lawn Care Included"],
            "community": ["Blocks to Beach", "Near Boardwalk", "Street Parking"],
            "pet":       ["Cats Allowed", "Small Dogs Allowed", "Pet Deposit Required"],
        },
        "images": [
            {"url": "https://images.unsplash.com/photo-1499793983690-e29da59ef1c2?w=1200&q=85",
             "caption": "Beach cottage exterior with wraparound deck",  "is_primary": True,  "order": 0},
            {"url": "https://images.unsplash.com/photo-1506439773649-6e0eb8cfb237?w=1200&q=85",
             "caption": "Bright open living and dining area",           "is_primary": False, "order": 1},
            {"url": "https://images.unsplash.com/photo-1565183997392-2f6f122e5912?w=1200&q=85",
             "caption": "Fully equipped kitchen",                       "is_primary": False, "order": 2},
            {"url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=1200&q=85",
             "caption": "Master bedroom — coastal décor",               "is_primary": False, "order": 3},
            {"url": "https://images.unsplash.com/photo-1449844908441-8829872d2607?w=1200&q=85",
             "caption": "Wraparound deck — perfect for entertaining",   "is_primary": False, "order": 4},
        ],
    },

    # ── 8 · Denver, CO — Studio for Rent ─────────────────────────────────────
    {
        "data": {
            "title":        "Industrial-Chic Studio in RiNo Art District",
            "slug":         "studio-rino-art-district-denver",
            "type":         "condo",
            "listing_type": "for-rent",
            "status":       "available",
            "condition":    "excellent",
            "price":        Decimal("1150"),
            "price_label":  "/mo",
            "bedrooms":     0,
            "bathrooms":    Decimal("1.0"),
            "sqft":         480,
            "lot_size":     None,
            "year_built":   2018,
            "garage":       0,
            "stories":      1,
            "address":      "2940 Larimer St",
            "city":         "Denver",
            "state":        "CO",
            "zip_code":     "80205",
            "neighborhood": "River North Arts District",
            "cross_street": "29th St",
            "latitude":     Decimal("39.7673"),
            "longitude":    Decimal("-104.9763"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":       False,
            "homepage_featured": False,
            "is_published":      True,
            "description": (
                "Modern industrial-chic studio in Denver's trendiest neighborhood, the River North Arts District. "
                "Exposed brick, polished concrete floors, soaring 12-foot ceilings, and oversized factory windows "
                "flood the space with light. In-unit washer/dryer, stainless appliances, and ample closet storage. "
                "Building features a communal rooftop with panoramic mountain views, secured bike storage, "
                "and a package locker system. Walk to Denver's best galleries, craft breweries, "
                "and the 38th & Blake commuter rail station. Cats allowed; no dogs."
            ),
        },
        "amenities": {
            "home":      ["Exposed Brick", "Polished Concrete Floors", "High Ceilings", "In-Unit Laundry", "Oversized Windows"],
            "kitchen":   ["Open Kitchen", "Stainless Appliances", "Dishwasher"],
            "community": ["Rooftop Deck", "Mountain Views", "Secured Bike Storage", "Package Lockers", "Near Light Rail"],
            "pet":       ["Cats Allowed", "No Dogs"],
        },
        "images": [
            {"url": "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=1200&q=85",
             "caption": "Studio interior — exposed brick and concrete", "is_primary": True,  "order": 0},
            {"url": "https://images.unsplash.com/photo-1493809842364-78817add7ffb?w=1200&q=85",
             "caption": "Open kitchen and living area",                 "is_primary": False, "order": 1},
            {"url": "https://images.unsplash.com/photo-1584622650111-993a426fbf0a?w=1200&q=85",
             "caption": "Updated bathroom with modern fixtures",        "is_primary": False, "order": 2},
            {"url": "https://images.unsplash.com/photo-1449844908441-8829872d2607?w=1200&q=85",
             "caption": "Rooftop deck with mountain views",             "is_primary": False, "order": 3},
            {"url": "https://images.unsplash.com/photo-1519642918688-7e43b19245d8?w=1200&q=85",
             "caption": "RiNo neighborhood street art",                 "is_primary": False, "order": 4},
        ],
    },

    # ── 9 · Raleigh, NC — 4-Bed House for Sale ───────────────────────────────
    {
        "data": {
            "title":        "4-Bed Move-In Ready Family Home in North Hills Raleigh",
            "slug":         "4bed-family-home-north-hills-raleigh-nc",
            "type":         "residential",
            "listing_type": "for-sale",
            "status":       "available",
            "condition":    "excellent",
            "price":        Decimal("375000"),
            "price_label":  "",
            "bedrooms":     4,
            "bathrooms":    Decimal("3.0"),
            "sqft":         2200,
            "lot_size":     Decimal("0.28"),
            "year_built":   2010,
            "garage":       2,
            "stories":      2,
            "address":      "4501 Falls of Neuse Rd",
            "city":         "Raleigh",
            "state":        "NC",
            "zip_code":     "27609",
            "neighborhood": "North Hills",
            "cross_street": "Wake Forest Rd",
            "latitude":     Decimal("35.8468"),
            "longitude":    Decimal("-78.6413"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":       True,
            "homepage_featured": True,
            "is_published":      True,
            "description": (
                "Beautiful 4-bedroom, 3-bath home in Raleigh's sought-after North Hills neighborhood, "
                "zoned for top-rated Millbrook High School. Open-concept main floor with gleaming hardwood floors, "
                "gas fireplace, and a renovated kitchen featuring granite countertops, a breakfast bar, "
                "and stainless appliances. Vaulted primary suite with walk-in closet and spa bath. "
                "Large backyard with a patio, 2-car garage, and a full-size bonus room on the upper level. "
                "Move-in ready. Close to North Hills Mall, REI, and the Crabtree Valley Greenway. "
                "Walking distance to top-rated North Hills Elementary."
            ),
        },
        "amenities": {
            "home":      ["Hardwood Floors", "Vaulted Ceilings", "Gas Fireplace", "Walk-in Closet", "Bonus Room"],
            "kitchen":   ["Granite Countertops", "Stainless Appliances", "Breakfast Bar", "Gas Range"],
            "community": ["Top-Rated Schools", "Near Greenway Trail", "Quiet Cul-de-sac Street"],
            "utility":   ["Central A/C", "2-Car Garage"],
            "pet":       ["Dogs Allowed", "Cats Allowed"],
        },
        "images": [
            {"url": "https://images.unsplash.com/photo-1564013799919-ab600027ffc6?w=1200&q=85",
             "caption": "Front exterior — 4501 Falls of Neuse Rd",     "is_primary": True,  "order": 0},
            {"url": "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=1200&q=85",
             "caption": "Living room with gas fireplace",               "is_primary": False, "order": 1},
            {"url": "https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?w=1200&q=85",
             "caption": "Renovated kitchen with granite countertops",   "is_primary": False, "order": 2},
            {"url": "https://images.unsplash.com/photo-1616594039964-ae9021a400a0?w=1200&q=85",
             "caption": "Vaulted primary suite",                        "is_primary": False, "order": 3},
            {"url": "https://images.unsplash.com/photo-1552321554-5fefe8c9ef14?w=1200&q=85",
             "caption": "Primary spa bathroom",                         "is_primary": False, "order": 4},
            {"url": "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?w=1200&q=85",
             "caption": "Backyard patio and lawn",                      "is_primary": False, "order": 5},
        ],
    },

    # ── 10 · Austin, TX — 2-Bed Apartment for Rent ───────────────────────────
    {
        "data": {
            "title":        "2-Bed High-Rise Apartment in Downtown Austin",
            "slug":         "2bed-highrise-apartment-downtown-austin-tx",
            "type":         "condo",
            "listing_type": "for-rent",
            "status":       "available",
            "condition":    "excellent",
            "price":        Decimal("1750"),
            "price_label":  "/mo",
            "bedrooms":     2,
            "bathrooms":    Decimal("2.0"),
            "sqft":         1050,
            "lot_size":     None,
            "year_built":   2020,
            "garage":       1,
            "stories":      1,
            "address":      "600 W 6th St",
            "city":         "Austin",
            "state":        "TX",
            "zip_code":     "78701",
            "neighborhood": "Downtown Austin",
            "cross_street": "Lamar Blvd",
            "latitude":     Decimal("30.2672"),
            "longitude":    Decimal("-97.7431"),
            "virtual_tour_url": "",
            "tour_360_url":     "",
            "is_featured":       False,
            "homepage_featured": False,
            "is_published":      True,
            "description": (
                "Live in the heart of Austin — 2-bedroom, 2-bath unit on the 18th floor with "
                "panoramic city views and Lady Bird Lake in the distance. "
                "Modern kitchen with quartz countertops and a gas range, in-unit washer/dryer, "
                "smart thermostat, and a private balcony. One assigned parking space included. "
                "Building amenities: resort-style pool, rooftop dog park, fitness center, co-working lounge, "
                "and 24-hour concierge. Walk to 6th Street entertainment, Whole Foods, and the lakefront hike/bike trail. "
                "Dogs and cats welcome (breed restrictions)."
            ),
        },
        "amenities": {
            "home":      ["City Views", "Private Balcony", "In-Unit Laundry", "Smart Thermostat", "High-Speed Internet Ready"],
            "kitchen":   ["Quartz Countertops", "Gas Range", "Wine Cooler", "Stainless Appliances"],
            "community": ["Rooftop Dog Park", "Resort Pool", "Fitness Center", "Co-Working Lounge", "24/7 Concierge"],
            "pet":       ["Dogs Allowed (breed restrictions)", "Cats Allowed", "Pet Fee Required"],
        },
        "images": [
            {"url": "https://images.unsplash.com/photo-1555636222-cae831e670b3?w=1200&q=85",
             "caption": "High-rise exterior — Downtown Austin",         "is_primary": True,  "order": 0},
            {"url": "https://images.unsplash.com/photo-1560185127-6ed189bf02f4?w=1200&q=85",
             "caption": "Open living room with floor-to-ceiling views", "is_primary": False, "order": 1},
            {"url": "https://images.unsplash.com/photo-1556909172-54557c7e4fb7?w=1200&q=85",
             "caption": "Modern kitchen with quartz countertops",       "is_primary": False, "order": 2},
            {"url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=1200&q=85",
             "caption": "Primary bedroom with city views",              "is_primary": False, "order": 3},
            {"url": "https://images.unsplash.com/photo-1449844908441-8829872d2607?w=1200&q=85",
             "caption": "Private balcony overlooking Austin skyline",   "is_primary": False, "order": 4},
            {"url": "https://images.unsplash.com/photo-1571939228382-b2f2b585ce15?w=1200&q=85",
             "caption": "Rooftop pool and lounge deck",                 "is_primary": False, "order": 5},
        ],
    },
]


# ── Command ──────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Seed the database with demo users, amenity categories, and 10 showcase properties."

    def handle(self, *args, **options):
        # ── 1. Clear existing property data ────────────────────────────────
        # NOTE: We never delete users because Post.author and LeadActivity.agent
        #       use on_delete=PROTECT. Just get_or_create the accounts we need.
        self.stdout.write("Clearing property data …")
        PropertyAmenity.objects.all().delete()
        with connection.cursor() as cur:
            cur.execute("DELETE FROM properties_propertyimage")
        Property.objects.all().delete()
        AmenityCategory.objects.all().delete()
        self.stdout.write("  Property data cleared.")

        # ── 2. Users (get_or_create — never bulk-delete) ───────────────────
        admin, _ = User.objects.get_or_create(
            email="admin@haskerrealtygroup.com",
            defaults={"first_name": "Admin", "last_name": "Hasker"},
        )
        if not admin.has_usable_password():
            admin.set_password("Admin1234!")
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()
        self.stdout.write(self.style.SUCCESS("  admin@haskerrealtygroup.com / Admin1234!"))

        agent, _ = User.objects.get_or_create(
            email="agent@haskerrealtygroup.com",
            defaults={
                "first_name": "Marcus",
                "last_name":  "Reid",
                "role":       Role.AGENT,
                "phone":      "(757) 555-0101",
            },
        )
        if not agent.has_usable_password():
            agent.set_password("Agent1234!")
            agent.save()
        self.stdout.write(self.style.SUCCESS("  agent@haskerrealtygroup.com / Agent1234!"))

        tenant, _ = User.objects.get_or_create(
            email="tenant@test.com",
            defaults={
                "first_name": "Jamie",
                "last_name":  "Carter",
                "role":       Role.CLIENT,
                "phone":      "(404) 555-0202",
            },
        )
        if not tenant.has_usable_password():
            tenant.set_password("Tenant1234!")
            tenant.save()
        self.stdout.write(self.style.SUCCESS("  tenant@test.com / Tenant1234!"))

        # ── 3. Amenity categories ──────────────────────────────────────────
        self.stdout.write("Creating amenity categories …")
        cats: dict[str, AmenityCategory] = {}
        for key, name, icon, order in CATEGORIES:
            cats[key], _ = AmenityCategory.objects.get_or_create(
                name=name,
                defaults={"icon": icon, "order": order},
            )

        # ── 4. Properties ──────────────────────────────────────────────────
        self.stdout.write(f"Seeding {len(PROPERTIES)} properties …")
        total_images = total_amenities = 0

        for item in PROPERTIES:
            prop = Property.objects.create(agent=agent, **item["data"])

            # Amenities
            amenity_count = 0
            for cat_key, names in item["amenities"].items():
                cat = cats.get(cat_key)
                for name in names:
                    PropertyAmenity.objects.create(property=prop, category=cat, name=name)
                    amenity_count += 1
            total_amenities += amenity_count

            # Images — raw SQL to avoid CloudinaryField URL mangling
            n_imgs = _insert_images(prop.id, item["images"])
            total_images += n_imgs

            self.stdout.write(
                f"  ✓ {prop.title} "
                f"({n_imgs} images, {amenity_count} amenities)"
            )

        # ── 5. Summary ─────────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== SEED COMPLETE ==="))
        self.stdout.write(self.style.SUCCESS(f"Properties : {len(PROPERTIES)}"))
        self.stdout.write(self.style.SUCCESS(f"Images     : {total_images}"))
        self.stdout.write(self.style.SUCCESS(f"Amenities  : {total_amenities}"))
        self.stdout.write("")
        self.stdout.write("Accounts:")
        self.stdout.write("  Superuser : admin@haskerrealtygroup.com / Admin1234!")
        self.stdout.write("  Agent     : agent@haskerrealtygroup.com / Agent1234!")
        self.stdout.write("  Tenant    : tenant@test.com / Tenant1234!")
        self.stdout.write("")
        self.stdout.write("Admin:  http://127.0.0.1:8000/admin/")
        self.stdout.write("API:    http://127.0.0.1:8000/api/v1/properties/")
