"""
Management command: python manage.py seed_dev

Populates the database with:
  - 1 Admin user
  - 3 Agent users + AgentProfile each
  - 8 Properties (matching the mock data from the Next.js frontend)
  - 5 Sample leads
  - 2 Viewings
"""

from django.core.management.base import BaseCommand
from django.utils.text import slugify


AGENTS = [
    {
        "email": "sarah.johnson@haskerrealtygroup.com",
        "first_name": "Sarah",
        "last_name": "Johnson",
        "phone": "+1-310-555-0101",
        "profile": {
            "bio": "With over 12 years of experience in luxury real estate, Sarah specializes in high-end residential properties in Beverly Hills and Bel Air.",
            "license_number": "CA-DRE-01234567",
            "specialties": ["Luxury Estates", "Buyer Representation", "Investment Properties"],
            "languages": ["English", "French"],
            "commission_rate": "3.00",
            "total_sales": "45000000.00",
            "years_experience": 12,
        },
    },
    {
        "email": "michael.chen@haskerrealtygroup.com",
        "first_name": "Michael",
        "last_name": "Chen",
        "phone": "+1-310-555-0102",
        "profile": {
            "bio": "Michael brings 8 years of expertise in commercial and luxury residential real estate, with a focus on the Malibu and Santa Monica markets.",
            "license_number": "CA-DRE-07654321",
            "specialties": ["Commercial Properties", "Waterfront Estates", "1031 Exchanges"],
            "languages": ["English", "Mandarin"],
            "commission_rate": "2.75",
            "total_sales": "32000000.00",
            "years_experience": 8,
        },
    },
    {
        "email": "emily.rodriguez@haskerrealtygroup.com",
        "first_name": "Emily",
        "last_name": "Rodriguez",
        "phone": "+1-310-555-0103",
        "profile": {
            "bio": "Emily is a dedicated real estate professional with a passion for matching clients with their perfect home. Specializing in the Los Feliz and Silver Lake areas.",
            "license_number": "CA-DRE-09876543",
            "specialties": ["First-Time Buyers", "Luxury Condos", "Relocation Services"],
            "languages": ["English", "Spanish"],
            "commission_rate": "3.00",
            "total_sales": "18000000.00",
            "years_experience": 5,
        },
    },
]

PROPERTIES = [
    {
        "title": "Opulent Beverly Hills Estate",
        "description": "An extraordinary trophy property set on over an acre of manicured grounds in the heart of Beverly Hills. This magnificent estate offers the pinnacle of luxury living with museum-quality finishes throughout.",
        "type": "residential",
        "listing_type": "for-sale",
        "status": "available",
        "price": "12500000.00",
        "bedrooms": 7,
        "bathrooms": "9.0",
        "sqft": 14500,
        "year_built": 2019,
        "garage": 4,
        "stories": 2,
        "address": "4521 Oak Ridge Drive",
        "city": "Beverly Hills",
        "state": "CA",
        "zip_code": "90210",
        "neighborhood": "Beverly Hills",
        "is_featured": True,
        "is_published": True,
        "agent_index": 0,
    },
    {
        "title": "Malibu Oceanfront Modern Villa",
        "description": "Perched above the Pacific Ocean, this architectural masterpiece offers unobstructed ocean views from every room. Floor-to-ceiling glass walls dissolve the boundary between indoors and out.",
        "type": "residential",
        "listing_type": "for-sale",
        "status": "available",
        "price": "8950000.00",
        "bedrooms": 5,
        "bathrooms": "6.0",
        "sqft": 9200,
        "year_built": 2021,
        "garage": 3,
        "stories": 3,
        "address": "23100 Pacific Coast Highway",
        "city": "Malibu",
        "state": "CA",
        "zip_code": "90265",
        "neighborhood": "Malibu Colony",
        "is_featured": True,
        "is_published": True,
        "agent_index": 1,
    },
    {
        "title": "Bel Air Architectural Marvel",
        "description": "A true architectural statement perched in the prestigious hills of Bel Air. This ultra-modern sanctuary combines cutting-edge design with unparalleled privacy and security.",
        "type": "residential",
        "listing_type": "for-sale",
        "status": "available",
        "price": "6200000.00",
        "bedrooms": 6,
        "bathrooms": "7.0",
        "sqft": 11300,
        "year_built": 2020,
        "garage": 3,
        "stories": 2,
        "address": "1155 Bel Air Road",
        "city": "Los Angeles",
        "state": "CA",
        "zip_code": "90077",
        "neighborhood": "Bel Air",
        "is_featured": True,
        "is_published": True,
        "agent_index": 0,
    },
    {
        "title": "Penthouse Collection — Century City",
        "description": "A rare opportunity to own the crown jewel of Century City's most prestigious address. This sky-high residence offers 360-degree panoramic views stretching from the ocean to the mountains.",
        "type": "condo",
        "listing_type": "for-sale",
        "status": "available",
        "price": "4800000.00",
        "bedrooms": 4,
        "bathrooms": "4.5",
        "sqft": 6500,
        "year_built": 2022,
        "garage": 3,
        "stories": 1,
        "address": "2025 Avenue of the Stars, PH",
        "city": "Los Angeles",
        "state": "CA",
        "zip_code": "90067",
        "neighborhood": "Century City",
        "is_featured": True,
        "is_published": True,
        "agent_index": 2,
    },
    {
        "title": "Hollywood Hills Contemporary Retreat",
        "description": "Nestled in the coveted Bird Streets of Hollywood Hills, this contemporary masterpiece offers an enviable lifestyle with sweeping city and mountain views.",
        "type": "residential",
        "listing_type": "for-sale",
        "status": "available",
        "price": "3750000.00",
        "bedrooms": 4,
        "bathrooms": "4.0",
        "sqft": 5200,
        "year_built": 2018,
        "garage": 2,
        "stories": 2,
        "address": "8760 Oriole Way",
        "city": "Los Angeles",
        "state": "CA",
        "zip_code": "90046",
        "neighborhood": "Hollywood Hills",
        "is_featured": False,
        "is_published": True,
        "agent_index": 1,
    },
    {
        "title": "Santa Monica Luxury Penthouse",
        "description": "Experience the ultimate in coastal luxury living in this stunning penthouse residence. Offering expansive ocean and city views, this meticulously designed home epitomizes the California lifestyle.",
        "type": "condo",
        "listing_type": "for-rent",
        "status": "available",
        "price": "25000.00",
        "price_label": "/mo",
        "bedrooms": 3,
        "bathrooms": "3.0",
        "sqft": 3800,
        "year_built": 2020,
        "garage": 2,
        "stories": 1,
        "address": "1700 Ocean Ave, PH-A",
        "city": "Santa Monica",
        "state": "CA",
        "zip_code": "90401",
        "neighborhood": "Santa Monica",
        "is_featured": False,
        "is_published": True,
        "agent_index": 2,
    },
    {
        "title": "Calabasas Equestrian Estate",
        "description": "A breathtaking compound offering the ultimate in luxurious country living. Situated on over 5 acres of lush, tree-studded grounds, this property is a true sanctuary for those seeking privacy.",
        "type": "residential",
        "listing_type": "for-sale",
        "status": "available",
        "price": "5900000.00",
        "bedrooms": 8,
        "bathrooms": "10.0",
        "sqft": 18000,
        "lot_size": "5.20",
        "year_built": 2015,
        "garage": 6,
        "stories": 2,
        "address": "4450 Las Virgenes Road",
        "city": "Calabasas",
        "state": "CA",
        "zip_code": "91302",
        "neighborhood": "Hidden Hills",
        "is_featured": True,
        "is_published": True,
        "agent_index": 0,
    },
    {
        "title": "West Hollywood Designer Townhome",
        "description": "An impeccably designed new-construction townhome in the heart of West Hollywood. This sophisticated residence offers an unparalleled combination of luxury, privacy, and walkable urban living.",
        "type": "townhouse",
        "listing_type": "for-sale",
        "status": "available",
        "price": "2100000.00",
        "bedrooms": 3,
        "bathrooms": "3.5",
        "sqft": 2900,
        "year_built": 2023,
        "garage": 2,
        "stories": 3,
        "address": "917 N Sweetzer Avenue",
        "city": "West Hollywood",
        "state": "CA",
        "zip_code": "90069",
        "neighborhood": "West Hollywood",
        "is_featured": False,
        "is_published": True,
        "agent_index": 2,
    },
    # ── Affordable Rentals ───────────────────────────────────────────────
    {
        "title": "Cozy Studio in Midtown Atlanta",
        "description": "A bright, well-maintained studio apartment steps from the BeltLine trail and Ponce City Market. Freshly updated kitchen, ample closet space, and rooftop access. Utilities included. Ideal for a single professional.",
        "type": "condo",
        "listing_type": "for-rent",
        "status": "available",
        "price": "875.00",
        "price_label": "/mo",
        "bedrooms": 0,
        "bathrooms": "1.0",
        "sqft": 450,
        "year_built": 2005,
        "garage": 0,
        "stories": 1,
        "address": "740 Ralph McGill Blvd NE, Apt 3B",
        "city": "Atlanta",
        "state": "GA",
        "zip_code": "30312",
        "neighborhood": "Midtown",
        "is_featured": True,
        "is_published": True,
        "agent_index": 0,
    },
    {
        "title": "Affordable 1-Bed in South End Charlotte",
        "description": "Charming 1-bedroom apartment in the heart of South End. Walkable to light rail, breweries, and restaurants. Hardwood floors, updated bathroom, in-unit washer/dryer hookups. Pet-friendly with small fee.",
        "type": "condo",
        "listing_type": "for-rent",
        "status": "available",
        "price": "1095.00",
        "price_label": "/mo",
        "bedrooms": 1,
        "bathrooms": "1.0",
        "sqft": 680,
        "year_built": 2001,
        "garage": 0,
        "stories": 1,
        "address": "1201 South Blvd, Apt 12",
        "city": "Charlotte",
        "state": "NC",
        "zip_code": "28203",
        "neighborhood": "South End",
        "is_featured": True,
        "is_published": True,
        "agent_index": 1,
    },
    {
        "title": "Spacious 2-Bed in Deep Ellum Dallas",
        "description": "Modern 2-bedroom apartment in vibrant Deep Ellum with exposed brick and stained concrete floors. Open floor plan, private balcony, secured parking. Minutes from downtown Dallas, Uptown, and major highways.",
        "type": "condo",
        "listing_type": "for-rent",
        "status": "available",
        "price": "1375.00",
        "price_label": "/mo",
        "bedrooms": 2,
        "bathrooms": "2.0",
        "sqft": 1050,
        "year_built": 2010,
        "garage": 1,
        "stories": 1,
        "address": "2800 Main St, Apt 205",
        "city": "Dallas",
        "state": "TX",
        "zip_code": "75226",
        "neighborhood": "Deep Ellum",
        "is_featured": True,
        "is_published": True,
        "agent_index": 2,
    },
    {
        "title": "1-Bedroom Near Vanderbilt — Nashville",
        "description": "Well-kept 1-bedroom unit just minutes from Vanderbilt University and Centennial Park. Freshly painted, ceiling fans throughout, large windows with great natural light. Water and trash included in rent.",
        "type": "condo",
        "listing_type": "for-rent",
        "status": "available",
        "price": "1200.00",
        "price_label": "/mo",
        "bedrooms": 1,
        "bathrooms": "1.0",
        "sqft": 720,
        "year_built": 1998,
        "garage": 0,
        "stories": 1,
        "address": "2109 West End Ave, Unit 4",
        "city": "Nashville",
        "state": "TN",
        "zip_code": "37203",
        "neighborhood": "West End",
        "is_featured": False,
        "is_published": True,
        "agent_index": 0,
    },
    {
        "title": "2-Bed House in Montrose Houston",
        "description": "Cheerful 2-bedroom bungalow in the beloved Montrose neighborhood. Private yard, covered porch, updated kitchen with granite counters, off-street parking. Short walking distance to top restaurants and bars.",
        "type": "residential",
        "listing_type": "for-rent",
        "status": "available",
        "price": "1450.00",
        "price_label": "/mo",
        "bedrooms": 2,
        "bathrooms": "1.0",
        "sqft": 1100,
        "year_built": 1965,
        "garage": 0,
        "stories": 1,
        "address": "419 Harold St",
        "city": "Houston",
        "state": "TX",
        "zip_code": "77006",
        "neighborhood": "Montrose",
        "is_featured": False,
        "is_published": True,
        "agent_index": 1,
    },
    {
        "title": "3-Bed Family Home in Phoenix",
        "description": "Move-in-ready 3-bedroom, 2-bath home with a private backyard and covered patio. New A/C unit, updated flooring throughout, 2-car garage, and a large master suite. Near schools, shopping, and the I-10.",
        "type": "residential",
        "listing_type": "for-rent",
        "status": "available",
        "price": "1750.00",
        "price_label": "/mo",
        "bedrooms": 3,
        "bathrooms": "2.0",
        "sqft": 1450,
        "year_built": 1992,
        "garage": 2,
        "stories": 1,
        "address": "3324 W Camelback Rd",
        "city": "Phoenix",
        "state": "AZ",
        "zip_code": "85017",
        "neighborhood": "Camelback East",
        "is_featured": False,
        "is_published": True,
        "agent_index": 2,
    },
    {
        "title": "Bright Studio in East Austin",
        "description": "Trendy studio apartment with high ceilings, polished concrete floors, and a modern kitchenette. Located in the heart of East Austin near coffee shops, food trucks, and nightlife. Bike-friendly neighborhood.",
        "type": "condo",
        "listing_type": "for-rent",
        "status": "available",
        "price": "995.00",
        "price_label": "/mo",
        "bedrooms": 0,
        "bathrooms": "1.0",
        "sqft": 420,
        "year_built": 2015,
        "garage": 0,
        "stories": 1,
        "address": "1611 E 6th St, Unit 8",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78702",
        "neighborhood": "East Austin",
        "is_featured": True,
        "is_published": True,
        "agent_index": 0,
    },
    {
        "title": "1-Bed Condo in RiNo Denver",
        "description": "Contemporary 1-bedroom condo in the River North Art District. Features quartz countertops, stainless appliances, and a private balcony with mountain views. Building gym and rooftop terrace included.",
        "type": "condo",
        "listing_type": "for-rent",
        "status": "available",
        "price": "1495.00",
        "price_label": "/mo",
        "bedrooms": 1,
        "bathrooms": "1.0",
        "sqft": 760,
        "year_built": 2018,
        "garage": 1,
        "stories": 1,
        "address": "3400 Walnut St, Unit 310",
        "city": "Denver",
        "state": "CO",
        "zip_code": "80205",
        "neighborhood": "RiNo",
        "is_featured": False,
        "is_published": True,
        "agent_index": 1,
    },
    {
        "title": "2-Bed Townhouse in Seminole Heights Tampa",
        "description": "Updated 2-bedroom townhouse in the historic Seminole Heights neighborhood. Hardwood floors, new windows, screened back porch, private fenced yard, and detached 1-car garage. No HOA.",
        "type": "townhouse",
        "listing_type": "for-rent",
        "status": "available",
        "price": "1595.00",
        "price_label": "/mo",
        "bedrooms": 2,
        "bathrooms": "1.5",
        "sqft": 1200,
        "year_built": 1945,
        "garage": 1,
        "stories": 2,
        "address": "5803 N Florida Ave",
        "city": "Tampa",
        "state": "FL",
        "zip_code": "33604",
        "neighborhood": "Seminole Heights",
        "is_featured": False,
        "is_published": True,
        "agent_index": 2,
    },
    {
        "title": "3-Bed Home Near Downtown Raleigh",
        "description": "Spacious 3-bedroom, 2-bath home in an established neighborhood minutes from downtown Raleigh. Large deck, fenced backyard, two-car driveway. Freshly painted interior, new carpet in bedrooms. Great school zone.",
        "type": "residential",
        "listing_type": "for-rent",
        "status": "available",
        "price": "1725.00",
        "price_label": "/mo",
        "bedrooms": 3,
        "bathrooms": "2.0",
        "sqft": 1380,
        "year_built": 1988,
        "garage": 0,
        "stories": 1,
        "address": "821 Brookside Dr",
        "city": "Raleigh",
        "state": "NC",
        "zip_code": "27604",
        "neighborhood": "Five Points",
        "is_featured": False,
        "is_published": True,
        "agent_index": 0,
    },
]

LEADS = [
    {
        "full_name": "James Harrington",
        "email": "james.harrington@example.com",
        "phone": "+1-310-555-9001",
        "source": "GOOGLE",
        "interest_type": "BUY",
        "budget_min": "5000000",
        "budget_max": "15000000",
        "preferred_location": "Beverly Hills, Bel Air",
        "message": "Looking for an estate for my family. Need at least 6 bedrooms and a guest house.",
        "status": "QUALIFIED",
    },
    {
        "full_name": "Natalie Westbrook",
        "email": "natalie@westbrookcapital.com",
        "phone": "+1-213-555-9002",
        "source": "REFERRAL",
        "interest_type": "INVEST",
        "budget_min": "2000000",
        "budget_max": "8000000",
        "preferred_location": "West Los Angeles, Century City",
        "message": "Interested in commercial or mixed-use investment opportunities.",
        "status": "CONTACTED",
    },
    {
        "full_name": "Marcus Thompson",
        "email": "mthompson@gmail.com",
        "phone": "+1-424-555-9003",
        "source": "INSTAGRAM",
        "interest_type": "RENT",
        "budget_max": "30000",
        "preferred_location": "Santa Monica, Malibu",
        "message": "Looking for a luxury rental for 12 months, relocating from NYC.",
        "status": "NEW",
    },
    {
        "full_name": "Sophia Chen",
        "email": "sophia.c@techfund.io",
        "phone": "+1-650-555-9004",
        "source": "CONTACT_FORM",
        "interest_type": "BUY",
        "budget_min": "3000000",
        "budget_max": "6000000",
        "preferred_location": "Hollywood Hills, Silver Lake",
        "message": "Modern architectural home preferred. Must have stunning views.",
        "status": "VIEWING",
    },
    {
        "full_name": "Robert Alderman",
        "email": "ralderman@aldermanlaw.com",
        "phone": "+1-310-555-9005",
        "source": "DIRECT",
        "interest_type": "SELL",
        "message": "Looking to list my current Brentwood property. Approximately 5,000 sqft, built in 2010.",
        "status": "CONTACTED",
    },
]


class Command(BaseCommand):
    help = "Seed the database with sample data for local development"

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete all existing data before seeding (non-destructive by default)",
        )

    def handle(self, *args, **options):
        from apps.accounts.models import CustomUser, AgentProfile, Role
        from apps.properties.models import Property, PropertyAmenity
        from apps.crm.models import Lead

        if options["flush"]:
            self.stdout.write("Flushing existing data...")
            Lead.objects.all().delete()
            Property.objects.all().delete()
            CustomUser.objects.filter(role__in=[Role.AGENT, Role.MANAGER]).delete()

        # --- Admin ---
        if not CustomUser.objects.filter(email="admin@haskerrealtygroup.com").exists():
            admin = CustomUser.objects.create_superuser(
                email="admin@haskerrealtygroup.com",
                password="Admin@123!",
                first_name="Admin",
                last_name="Hasker & Co.",
            )
            admin.role = Role.ADMIN
            admin.save()
            self.stdout.write(self.style.SUCCESS("Created admin: admin@haskerrealtygroup.com / Admin@123!"))
        else:
            self.stdout.write("Admin already exists — skipping.")

        # --- Agents ---
        agents = []
        for agent_data in AGENTS:
            profile_data = agent_data.pop("profile")
            agent, created = CustomUser.objects.get_or_create(
                email=agent_data["email"],
                defaults={**agent_data, "role": Role.AGENT, "is_staff": True},
            )
            if created:
                agent.set_password("Agent@123!")
                agent.save()
                AgentProfile.objects.create(user=agent, **profile_data)
                self.stdout.write(self.style.SUCCESS(f"Created agent: {agent.email}"))
            else:
                self.stdout.write(f"Agent {agent.email} already exists — skipping.")
            agents.append(agent)
            # Re-add profile data for next iteration if needed
            agent_data["profile"] = profile_data

        # --- Properties ---
        amenities_map = {
            "residential": ["Air Conditioning", "In-Unit Laundry", "Hardwood Floors",
                            "Private Yard", "Off-Street Parking", "Updated Kitchen"],
            "condo": ["In-Unit Laundry", "Fitness Center", "Secured Entry",
                      "Balcony", "Dishwasher", "Central A/C"],
            "townhouse": ["Private Entrance", "Attached Garage", "In-Unit Laundry",
                          "Patio/Deck", "Storage Space"],
        }

        for prop_data in PROPERTIES:
            agent_index = prop_data.pop("agent_index")
            agent = agents[agent_index]
            price_label = prop_data.pop("price_label", "")

            if not Property.objects.filter(address=prop_data["address"]).exists():
                prop = Property.objects.create(
                    agent=agent,
                    price_label=price_label,
                    **prop_data,
                )
                # Add amenities
                for amenity_name in amenities_map.get(prop.type, []):
                    PropertyAmenity.objects.create(property=prop, name=amenity_name)

                self.stdout.write(self.style.SUCCESS(f"Created property: {prop.title}"))
            else:
                self.stdout.write(f"Property at {prop_data['address']} already exists — skipping.")
            prop_data["agent_index"] = agent_index
            prop_data["price_label"] = price_label

        # --- Leads ---
        for lead_data in LEADS:
            if not Lead.objects.filter(email=lead_data["email"]).exists():
                Lead.objects.create(**lead_data)
                self.stdout.write(self.style.SUCCESS(f"Created lead: {lead_data['full_name']}"))
            else:
                self.stdout.write(f"Lead {lead_data['email']} already exists — skipping.")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("Seed complete! Login credentials:"))
        self.stdout.write(self.style.SUCCESS("  Admin: admin@haskerrealtygroup.com / Admin@123!"))
        self.stdout.write(self.style.SUCCESS("  Agent: sarah.johnson@haskerrealtygroup.com / Agent@123!"))
        self.stdout.write(self.style.SUCCESS("  Admin panel: http://localhost:8000/admin/"))
        self.stdout.write(self.style.SUCCESS("  API: http://localhost:8000/api/v1/"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
