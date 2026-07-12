import json
import os
import sys

def main():
    # 1. Update JSON fixture if it exists in the current directory
    fixture_path = "properties_fixture_prod.json"
    if os.path.exists(fixture_path):
        print(f"Reading {fixture_path}...")
        with open(fixture_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Collect existing slugs to prevent unique constraint failures
        existing_slugs = set()
        for obj in data:
            if obj.get("model") == "properties.property":
                slug = obj.get("fields", {}).get("slug", "")
                if not slug.startswith("invh-"):
                    existing_slugs.add(slug)

        fixture_count = 0
        for obj in data:
            if obj.get("model") == "properties.property":
                fields = obj.get("fields", {})
                slug = fields.get("slug", "")
                cross_street = fields.get("cross_street", "")
                
                updated = False
                if slug.startswith("invh-"):
                    new_slug = slug[5:]  # Strip 'invh-'
                    if new_slug in existing_slugs:
                        new_slug = f"{new_slug}-invh"  # Avoid duplicate conflicts
                    fields["slug"] = new_slug
                    existing_slugs.add(new_slug)
                    updated = True
                
                if cross_street == "invh":
                    fields["cross_street"] = ""
                    updated = True
                    
                if updated:
                    fixture_count += 1

        with open(fixture_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"Success: Updated/cleaned {fixture_count} properties in properties_fixture_prod.json.")
    else:
        print("No properties_fixture_prod.json file found in the current working directory to process.")

    # 2. Update Database (if Django environment is initialized)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
    try:
        import django
        django.setup()
        from apps.properties.models import Property
        from django.db import IntegrityError
        from django.db.models import Q

        db_count = 0
        skipped_count = 0
        existing_db_slugs = set(Property.objects.exclude(slug__startswith="invh-").values_list("slug", flat=True))

        for p in Property.objects.filter(Q(slug__startswith="invh-") | Q(cross_street="invh")):
            updated = False
            
            if p.slug.startswith("invh-"):
                original_slug = p.slug
                new_slug = original_slug[5:]
                if new_slug in existing_db_slugs:
                    new_slug = f"{new_slug}-invh"
                p.slug = new_slug
                existing_db_slugs.add(new_slug)
                updated = True
                
            if p.cross_street == "invh":
                p.cross_street = ""
                updated = True
                
            if updated:
                try:
                    p.save()
                    db_count += 1
                except IntegrityError:
                    skipped_count += 1

        print(f"Success: Updated/cleaned {db_count} database properties. (Skipped/Failed: {skipped_count})")
    except Exception as e:
        print(f"Database update skipped or failed (not running inside a Django project): {e}")

if __name__ == "__main__":
    main()
