import os
import sys
import json
import datetime
from googleapiclient.discovery import build
from google.oauth2 import service_account

def main():
    BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
    SERVICE_ACCOUNT_FILE = os.path.join(BACKEND_DIR, "service_account.json")
    
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        print(f"Error: service_account.json not found at {SERVICE_ACCOUNT_FILE}")
        sys.exit(1)
        
    SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
    
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        service = build("webmasters", "v3", credentials=creds)
    except Exception as e:
        print(f"Failed to authenticate with Service Account: {e}")
        sys.exit(1)
        
    # Get verified sites to verify our site URL
    try:
        sites_resp = service.sites().list().execute()
        site_entries = sites_resp.get("siteEntry", [])
    except Exception as e:
        print(f"Failed to fetch sites list: {e}")
        sys.exit(1)
        
    target_site = None
    for entry in site_entries:
        url = entry.get("siteUrl", "")
        if "primefamilyhousing.com" in url:
            if url.startswith("sc-domain:"):
                target_site = url
                break
            elif not target_site:
                target_site = url
                
    if not target_site:
        if site_entries:
            target_site = site_entries[0].get("siteUrl")
        else:
            print("Error: No verified sites found.")
            sys.exit(1)
            
    print(f"Using site: {target_site}")
    
    # Define query parameters (last 90 days)
    today = datetime.date.today()
    ninety_days_ago = today - datetime.timedelta(days=90)
    
    print(f"Extracting Search Console metrics from {ninety_days_ago} to {today}...")
    
    # 1. Fetch Top 100 Queries
    print("Fetching top queries...")
    queries_body = {
        "startDate": ninety_days_ago.isoformat(),
        "endDate": today.isoformat(),
        "dimensions": ["query"],
        "rowLimit": 100
    }
    queries_resp = service.searchanalytics().query(siteUrl=target_site, body=queries_body).execute()
    queries_rows = queries_resp.get("rows", [])
    
    # 2. Fetch Top 100 Pages
    print("Fetching top pages...")
    pages_body = {
        "startDate": ninety_days_ago.isoformat(),
        "endDate": today.isoformat(),
        "dimensions": ["page"],
        "rowLimit": 100
    }
    pages_resp = service.searchanalytics().query(siteUrl=target_site, body=pages_body).execute()
    pages_rows = pages_resp.get("rows", [])
    
    # Save raw outputs
    with open(os.path.join(BACKEND_DIR, "seo_queries.json"), "w", encoding="utf-8") as f:
        json.dump(queries_rows, f, indent=2)
    with open(os.path.join(BACKEND_DIR, "seo_pages.json"), "w", encoding="utf-8") as f:
        json.dump(pages_rows, f, indent=2)
        
    print(f"Saved raw reports to seo_queries.json and seo_pages.json")
    
    # Generate Opportunities Analysis
    generate_opportunities(BACKEND_DIR, queries_rows, pages_rows)
    
def generate_opportunities(backend_dir, queries, pages):
    report_path = os.path.join(backend_dir, "seo_opportunities.md")
    
    # Find Low CTR Pages
    # Standard warning: Pages with impressions > 500 and CTR < 1.0%
    low_ctr_pages = []
    # Page One Candidates: Avg position between 10.1 and 20.0
    page_one_candidates = []
    
    for row in pages:
        page_url = row.get("keys", [""])[0]
        clicks = row.get("clicks", 0)
        impressions = row.get("impressions", 0)
        ctr = row.get("ctr", 0) * 100
        position = row.get("position", 0)
        
        if impressions >= 30 and ctr < 10.0 and position < 15:
            low_ctr_pages.append({
                "url": page_url,
                "clicks": clicks,
                "impressions": impressions,
                "ctr": ctr,
                "position": position
            })
            
        if impressions >= 20 and 10.0 < position <= 20.0:
            page_one_candidates.append({
                "url": page_url,
                "clicks": clicks,
                "impressions": impressions,
                "ctr": ctr,
                "position": position
            })
            
    # Top 15 Queries
    top_queries_table = "| Query | Clicks | Impressions | CTR | Avg Position |\n| :--- | :--- | :--- | :--- | :--- |\n"
    for q in queries[:15]:
        query_text = q.get("keys", [""])[0]
        clicks = q.get("clicks", 0)
        impressions = q.get("impressions", 0)
        ctr = q.get("ctr", 0) * 100
        position = q.get("position", 0)
        top_queries_table += f"| {query_text} | {clicks:,} | {impressions:,} | {ctr:.2f}% | {position:.1f} |\n"
        
    # Top 15 Pages
    top_pages_table = "| Page URL | Clicks | Impressions | CTR | Avg Position |\n| :--- | :--- | :--- | :--- | :--- |\n"
    for p in pages[:15]:
        page_url = p.get("keys", [""])[0]
        clicks = p.get("clicks", 0)
        impressions = p.get("impressions", 0)
        ctr = p.get("ctr", 0) * 100
        position = p.get("position", 0)
        slug_display = page_url.replace("https://primefamilyhousing.com", "") or "/"
        top_pages_table += f"| [{slug_display}]({page_url}) | {clicks:,} | {impressions:,} | {ctr:.2f}% | {position:.1f} |\n"

    # Compile Markdown Opportunities
    opportunities_md = f"""# Google Search Console SEO Opportunities Report

This report highlights top keywords, top pages, and specific keyword/page opportunities for optimization.

## Top 15 Search Queries (Keywords)
{top_queries_table}

## Top 15 Visited Pages
{top_pages_table}

## 🎯 Low-CTR Page Title & Meta Opportunities (High Impressions, Low Click-Through)
These pages have high search visibility (impressions) but users aren't clicking. Improving their **meta titles** and **descriptions** to be more compelling can instantly drive new traffic.

| Page URL | Clicks | Impressions | Current CTR | Avg Position | Optimization Recommendation |
| :--- | :--- | :--- | :--- | :--- | :--- |
"""

    if not low_ctr_pages:
        opportunities_md += "| None found | - | - | - | - | - |\n"
    for item in low_ctr_pages[:10]:
        slug = item["url"].replace("https://primefamilyhousing.com", "") or "/"
        opportunities_md += f"| [{slug}]({item['url']}) | {item['clicks']:,} | {item['impressions']:,} | {item['ctr']:.2f}% | {item['position']:.1f} | Revise title tag to include primary keywords; write a benefit-driven meta description. |\n"

    opportunities_md += """
## 🚀 Page-One Rank Boost Candidates (Average Position 10.1 - 20.0)
These pages are ranking on page two of Google results. A minor on-page SEO boost (improving H2/H3 headers, adding semantic keywords, internal linking) can push them to page one, exponentially increasing traffic.

| Page URL | Clicks | Impressions | Current CTR | Avg Position | Optimization Recommendation |
| :--- | :--- | :--- | :--- | :--- | :--- |
"""

    if not page_one_candidates:
        opportunities_md += "| None found | - | - | - | - | - |\n"
    for item in page_one_candidates[:10]:
        slug = item["url"].replace("https://primefamilyhousing.com", "") or "/"
        opportunities_md += f"| [{slug}]({item['url']}) | {item['clicks']:,} | {item['impressions']:,} | {item['ctr']:.2f}% | {item['position']:.1f} | Add targeted headers; increase page content depth; add 2-3 links from high-authority indexed pages. |\n"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(opportunities_md)
        
    print(f"Successfully compiled SEO opportunities report at {report_path}")

if __name__ == "__main__":
    main()
