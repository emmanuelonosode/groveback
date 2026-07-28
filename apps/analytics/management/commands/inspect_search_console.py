import os
import sys
import json
import datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from apps.properties.models import Property
from apps.blog.models import Post

class Command(BaseCommand):
    help = "Authenticates with Google Search Console, lists sites, sitemaps, analytics, and runs URL inspection."

    def add_arguments(self, parser):
        parser.add_argument(
            "--site-url",
            type=str,
            help="Specify a custom site URL/sc-domain for Google Search Console (e.g. sc-domain:primefamilyhousing.com). If not provided, it will automatically search verified sites.",
        )
        parser.add_argument(
            "--inspect-limit",
            type=int,
            default=10,
            help="Limit the number of property/blog URLs inspected via the URL Inspection API to stay within quota.",
        )
        parser.add_argument(
            "--redirect-uri",
            type=str,
            default="http://localhost:8080/",
            help="The redirect URI registered in your Google Cloud Console (e.g., http://localhost:8080/ or http://localhost:8000/oauth2callback).",
        )

    def handle(self, *args, **options):
        # 1. Paths
        CLIENT_SECRETS_FILE = os.path.join(settings.BASE_DIR, "client_secret.json")
        SERVICE_ACCOUNT_FILE = os.path.join(settings.BASE_DIR, "service_account.json")
        TOKEN_FILE = os.path.join(settings.BASE_DIR, "google_tokens.json")
        REPORT_FILE = os.path.join(settings.BASE_DIR, "search_console_report.md")

        SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

        creds = None
        
        # Try Service Account first (bypasses browser OAuth and Redirect URIs)
        if os.path.exists(SERVICE_ACCOUNT_FILE):
            try:
                from google.oauth2 import service_account
                creds = service_account.Credentials.from_service_account_file(
                    SERVICE_ACCOUNT_FILE, scopes=SCOPES
                )
                self.stdout.write("Authenticated successfully using Service Account credentials.")
            except Exception as e:
                self.stdout.write(f"Warning: Failed to load service account: {e}")

        # Fallback to OAuth flow if no Service Account credentials are found
        if not creds:
            if not os.path.exists(CLIENT_SECRETS_FILE):
                self.stderr.write(f"Error: Neither service_account.json nor client_secret.json was found.")
                self.stderr.write("Please place your Service Account key in service_account.json or Web OAuth client in client_secret.json.")
                sys.exit(1)

            if os.path.exists(TOKEN_FILE):
                try:
                    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
                except Exception as e:
                    self.stdout.write(f"Warning: Failed to load existing token file: {e}")

            
            if not creds:
                self.stdout.write("Initiating Google OAuth2 authorization flow...")
                
                redirect_uri = options.get("redirect_uri")
                flow = InstalledAppFlow.from_client_secrets_file(
                    CLIENT_SECRETS_FILE, SCOPES, redirect_uri=redirect_uri
                )
                
                auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
                
                self.stdout.write("\n" + "="*80)
                self.stdout.write("GOOGLE AUTHORIZATION REQUIRED")
                self.stdout.write("="*80)
                self.stdout.write("1. Open the following URL in your browser:")
                self.stdout.write(f"\n   {auth_url}\n")
                self.stdout.write("2. Sign in with the account owning your Google Search Console property.")
                self.stdout.write("3. After you approve, you will be redirected to your Redirect URI.")
                self.stdout.write("   (e.g., http://localhost:8080/?code=... or similar).")
                self.stdout.write("   The page in your browser might fail to load (e.g. 'Site cannot be reached'),")
                self.stdout.write("   but that is expected! Just copy the ENTIRE URL from your browser's address bar.")
                self.stdout.write("="*80 + "\n")
                
                try:
                    pasted_input = input("Paste the redirected URL (or authorization code) here: ").strip()
                    
                    from urllib.parse import urlparse, parse_qs
                    parsed = urlparse(pasted_input)
                    query = parse_qs(parsed.query)
                    code = query.get("code")
                    
                    if code:
                        auth_code = code[0]
                    else:
                        # If they just pasted the code itself
                        auth_code = pasted_input
                        
                    if not auth_code:
                        self.stderr.write("Error: Could not retrieve authorization code from input.")
                        sys.exit(1)
                        
                    self.stdout.write("Exchanging authorization code for API tokens...")
                    flow.fetch_token(code=auth_code)
                    creds = flow.credentials
                except Exception as ex:
                    self.stderr.write(f"OAuth flow failed: {ex}")
                    sys.exit(1)

            # Save the credentials for next run
            with open(TOKEN_FILE, "w") as token:
                token.write(creds.to_json())
            self.stdout.write(f"Successfully authenticated and saved tokens to {TOKEN_FILE}.")


        # 3. Connect to APIs
        # webmasters v3 API is the Search Console API for sites, sitemaps, searchanalytics
        service = build("webmasters", "v3", credentials=creds)
        # searchconsole v1 API is for URL Inspection
        sc_service = build("searchconsole", "v1", credentials=creds)

        # 4. Fetch Verified Sites
        self.stdout.write("Fetching verified sites from Search Console...")
        try:
            sites_resp = service.sites().list().execute()
        except Exception as e:
            self.stderr.write(f"Failed to fetch verified sites: {e}")
            sys.exit(1)

        site_entries = sites_resp.get("siteEntry", [])
        if not site_entries:
            self.stderr.write("No verified sites found in this Google Search Console account.")
            sys.exit(1)

        self.stdout.write(f"Found {len(site_entries)} site(s) in Search Console:")
        for entry in site_entries:
            self.stdout.write(f"  - {entry.get('siteUrl')} ({entry.get('permissionLevel')})")

        # 5. Select target site
        target_site = options.get("site_url")
        if not target_site:
            # Look for primefamilyhousing.com matches
            pfh_domains = [
                e.get("siteUrl") for e in site_entries 
                if "primefamilyhousing.com" in e.get("siteUrl")
            ]
            if pfh_domains:
                # Prefer domain properties (sc-domain:primefamilyhousing.com)
                domain_props = [d for d in pfh_domains if d.startswith("sc-domain:")]
                if domain_props:
                    target_site = domain_props[0]
                else:
                    target_site = pfh_domains[0]
            else:
                # Fallback to the first verified site
                target_site = site_entries[0].get("siteUrl")

        self.stdout.write(f"Using site: {target_site}")

        # 6. Fetch Sitemaps
        self.stdout.write(f"Fetching sitemaps for {target_site}...")
        sitemaps_data = []
        try:
            sitemaps_resp = service.sitemaps().list(siteUrl=target_site).execute()
            sitemaps_data = sitemaps_resp.get("sitemap", [])
        except Exception as e:
            self.stdout.write(f"Warning: Could not fetch sitemaps: {e}")

        # 7. Fetch Search Analytics (last 30 days)
        self.stdout.write("Fetching search performance metrics (last 30 days)...")
        analytics_data = []
        try:
            today = datetime.date.today()
            thirty_days_ago = today - datetime.timedelta(days=30)
            analytics_body = {
                "startDate": thirty_days_ago.isoformat(),
                "endDate": today.isoformat(),
                "dimensions": ["date"],
            }
            analytics_resp = service.searchanalytics().query(
                siteUrl=target_site, body=analytics_body
            ).execute()
            analytics_data = analytics_resp.get("rows", [])
        except Exception as e:
            self.stdout.write(f"Warning: Could not fetch search analytics: {e}")

        # 8. Define URLs to Inspect
        base_domain = "https://primefamilyhousing.com"
        # Gather key URLs
        urls_to_inspect = [
            f"{base_domain}/",
            f"{base_domain}/houses-for-rent",
            f"{base_domain}/apply",
            f"{base_domain}/agents",
            f"{base_domain}/blog",
            f"{base_domain}/careers",
        ]

        # Fetch some properties and blog posts from the database to inspect
        properties = Property.objects.filter(is_published=True).order_by("-created_at")[:5]
        for p in properties:
            urls_to_inspect.append(f"{base_domain}/houses-for-rent/{p.slug}")

        posts = Post.objects.filter(is_published=True).order_by("-created_at")[:5]
        for post in posts:
            urls_to_inspect.append(f"{base_domain}/blog/{post.slug}")

        # Limit inspection list to stay under limits
        limit = options.get("inspect_limit", 10)
        urls_to_inspect = urls_to_inspect[:limit]

        # 9. Perform URL Inspections
        self.stdout.write(f"Running URL Inspection for {len(urls_to_inspect)} key URLs...")
        inspection_results = []

        for url in urls_to_inspect:
            self.stdout.write(f"Inspecting: {url}...")
            try:
                body = {
                    "inspectionUrl": url,
                    "siteUrl": target_site,
                    "languageCode": "en-US",
                }
                resp = sc_service.urlInspection().index().inspect(body=body).execute()
                inspection_results.append({
                    "url": url,
                    "status": "success",
                    "result": resp.get("inspectionResult", {})
                })
            except Exception as e:
                self.stdout.write(f"  Error inspecting {url}: {e}")
                inspection_results.append({
                    "url": url,
                    "status": "error",
                    "error": str(e)
                })

        # 10. Generate Markdown Report
        self.stdout.write("Generating Markdown Report...")
        report_md = self.create_report(target_site, sitemaps_data, analytics_data, inspection_results)
        
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            f.write(report_md)

        self.stdout.write(self.style.SUCCESS(f"Report successfully saved to {REPORT_FILE}"))

    def create_report(self, target_site, sitemaps, analytics, inspections):
        title = f"# Google Search Console Inspection Report for {target_site}"
        timestamp = f"\n*Generated on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n"
        
        # Sitemaps Section
        sitemaps_section = "\n## Sitemap Status\n"
        if not sitemaps:
            sitemaps_section += "No sitemaps registered or failed to retrieve sitemap records.\n"
        else:
            sitemaps_section += "| Sitemap Path | Last Submitted | Last Crawled | Status | Total URLs | Indexed | Errors | Warnings |\n"
            sitemaps_section += "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
            for sm in sitemaps:
                path = sm.get("path", "N/A")
                last_sub = sm.get("lastSubmitted", "N/A")
                last_crw = sm.get("lastDownloaded", "N/A")
                errors = sm.get("errors", 0)
                warnings = sm.get("warnings", 0)
                
                # Extract URL counts if present
                contents = sm.get("contents", [])
                total_urls = "N/A"
                indexed = "N/A"
                if contents:
                    total_urls = sum(int(c.get("submitted", 0)) for c in contents)
                    indexed = sum(int(c.get("indexed", 0)) for c in contents)
                
                status = "OK"
                if int(errors) > 0:
                    status = "🔴 Error"
                elif int(warnings) > 0:
                    status = "🟡 Warning"
                elif sm.get("isPending", False):
                    status = "🔵 Pending"

                sitemaps_section += f"| `{path}` | {last_sub} | {last_crw} | **{status}** | {total_urls} | {indexed} | {errors} | {warnings} |\n"

        # Search Analytics Summary Section
        analytics_section = "\n## Search Performance (Last 30 Days)\n"
        if not analytics:
            analytics_section += "No performance data found or failed to retrieve analytics.\n"
        else:
            total_clicks = sum(row.get("clicks", 0) for row in analytics)
            total_imps = sum(row.get("impressions", 0) for row in analytics)
            avg_ctr = (sum(row.get("ctr", 0) for row in analytics) / len(analytics) * 100) if analytics else 0
            avg_pos = (sum(row.get("position", 0) for row in analytics) / len(analytics)) if analytics else 0
            
            analytics_section += f"- **Total Search Clicks**: {total_clicks:,}\n"
            analytics_section += f"- **Total Impressions**: {total_imps:,}\n"
            analytics_section += f"- **Average Click-Through Rate (CTR)**: {avg_ctr:.2f}%\n"
            analytics_section += f"- **Average Search Position**: {avg_pos:.1f}\n"

        # URL Inspection Summary Section
        inspection_section = "\n## URL Indexing Status Summary\n"
        inspection_section += "| URL | Index Status | Mobile Usability | Rich Results | Robots.txt | Last Crawled |\n"
        inspection_section += "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
        
        detail_section = "\n## URL Inspection Details & Error Diagnostics\n"
        
        for idx, item in enumerate(inspections):
            url = item["url"]
            if item["status"] == "error":
                inspection_section += f"| [{url.split('/')[-1] or '/'}]({url}) | ⚠️ API Error | N/A | N/A | N/A | N/A |\n"
                detail_section += f"### {idx+1}. [{url}]({url})\n"
                detail_section += f"> [!WARNING]\n"
                detail_section += f"> **Inspection Failed**: {item['error']}\n\n"
                continue
                
            res = item["result"]
            index_status = res.get("indexStatusResult", {})
            mobile_usability = res.get("mobileUsabilityResult", {})
            rich_results = res.get("richResultsResult", {})
            
            # Index Verdict and Coverage
            verdict = index_status.get("verdict", "UNKNOWN")
            coverage = index_status.get("coverageState", "N/A")
            robots_txt = index_status.get("robotsTxtState", "N/A")
            last_crawl = index_status.get("lastCrawlTime", "N/A")
            if last_crawl != "N/A":
                # Format ISO timestamp if possible
                try:
                    last_crawl = last_crawl.split("T")[0]
                except Exception:
                    pass
            
            verdict_emoji = "🟢 Indexed" if verdict == "PASS" else "🔴 Not Indexed" if verdict == "FAIL" else "🟡 Warning"
            
            # Mobile usability
            mobile_verdict = mobile_usability.get("verdict", "N/A")
            mobile_emoji = "🟢 PASS" if mobile_verdict == "PASS" else "🔴 FAIL" if mobile_verdict == "FAIL" else "⚪ N/A"
            
            # Rich Results
            rich_verdict = rich_results.get("verdict", "N/A")
            rich_emoji = "🟢 PASS" if rich_verdict == "PASS" else "🔴 FAIL" if rich_verdict == "FAIL" else "⚪ N/A"
            
            # Add to table
            inspection_section += f"| [{url.split('/')[-1] or '/'}]({url}) | {verdict_emoji} | {mobile_emoji} | {rich_emoji} | {robots_txt} | {last_crawl} |\n"
            
            # Add to details
            detail_section += f"### {idx+1}. [{url}]({url})\n"
            detail_section += f"- **Index Status**: {verdict_emoji} (`{verdict}`)\n"
            detail_section += f"- **Google Coverage State**: `{coverage}`\n"
            detail_section += f"- **Robots.txt Permission**: `{robots_txt}`\n"
            detail_section += f"- **Last Crawled Time**: `{index_status.get('lastCrawlTime', 'N/A')}`\n"
            detail_section += f"- **Crawl Fetch State**: `{index_status.get('pageFetchState', 'N/A')}`\n"
            detail_section += f"- **Indexing State**: `{index_status.get('indexingState', 'N/A')}`\n"
            
            user_canonical = index_status.get("userCanonical", "None declared")
            google_canonical = index_status.get("googleCanonical", "None selected")
            detail_section += f"- **User Declared Canonical**: `{user_canonical}`\n"
            detail_section += f"- **Google Selected Canonical**: `{google_canonical}`\n"
            
            # Mobile Usability Info
            if mobile_verdict != "N/A":
                detail_section += f"- **Mobile Usability**: {mobile_emoji}\n"
                issues = mobile_usability.get("issues", [])
                if issues:
                    detail_section += "  - *Issues encountered*:\n"
                    for issue in issues:
                        detail_section += f"    - {issue.get('issueType')}: Severity {issue.get('severity')}\n"
            
            # Rich Results Info
            detected_items = rich_results.get("detectedItems", [])
            if detected_items:
                detail_section += "- **Rich Results / Structured Data**:\n"
                for item_dt in detected_items:
                    detail_name = item_dt.get("richResultType", "Unknown")
                    items_list = item_dt.get("items", [])
                    item_errors = sum(1 for it in items_list if it.get("issues"))
                    err_status = f"🔴 {item_errors} issue(s) found" if item_errors > 0 else "🟢 Valid"
                    detail_section += f"  - `{detail_name}`: {err_status}\n"
            
            # Diagnostic / Fix recommendations based on Coverage State
            detail_section += "\n#### Diagnostic & Fix Guidance:\n"
            guidance = self.get_error_guidance(coverage, verdict)
            detail_section += f"{guidance}\n\n---\n"
            
        return f"{title}\n{timestamp}\n{sitemaps_section}\n{analytics_section}\n{inspection_section}\n{detail_section}"

    def get_error_guidance(self, coverage, verdict):
        if verdict == "PASS":
            return "> [Safe to Ignore]\n> **No Action Needed**: Google has successfully indexed this page, and it is eligible to appear in search results."
            
        coverage = coverage.lower()
        if "noindex" in coverage:
            return (
                "> [!WARNING]\n"
                "> **Action Required: Excluded by 'noindex' tag**\n"
                "> - Google found a `noindex` meta tag or HTTP header on this page, which explicitly tells search bots not to index it.\n"
                "> - **How to fix**: Check the page HTML for `<meta name=\"robots\" content=\"noindex\">` or headers like `X-Robots-Tag: noindex`. Remove these if you want Google to index this page."
            )
        elif "robots.txt" in coverage or "blocked by robots.txt" in coverage:
            return (
                "> [!WARNING]\n"
                "> **Action Required: Blocked by robots.txt**\n"
                "> - Googlebot is prohibited from crawling this URL due to a rule in your `robots.txt` file.\n"
                "> - **How to fix**: Review `hargrove/frontend/app/robots.ts` or the served `/robots.txt` file. Make sure you don't have a `Disallow` rule matching this URL."
            )
        elif "soft 404" in coverage:
            return (
                "> [!WARNING]\n"
                "> **Action Required: Soft 404**\n"
                "> - The page returns a success status code (200 OK), but Googlebot believes it behaves like a 404 error page (e.g. it is empty, displays a 'Not Found' message, or has very little content).\n"
                "> - **How to fix**: Ensure the page contains high-quality, relevant content, or return a true 404/410 HTTP status code if the page is indeed missing."
            )
        elif "not found (404)" in coverage:
            return (
                "> [!WARNING]\n"
                "> **Action Required: Submitted URL Not Found (404)**\n"
                "> - Google attempted to crawl this page (which is in your sitemap or linked internally), but the server returned a 404 Not Found error.\n"
                "> - **How to fix**: If this URL is deprecated, remove it from the database / sitemap. If it is supposed to exist, verify that the routing and backend are functional."
            )
        elif "redirect error" in coverage:
            return (
                "> [!WARNING]\n"
                "> **Action Required: Redirect Error**\n"
                "> - Google experienced a redirect error (such as a redirect chain that is too long, a redirect loop, or an empty redirect URL).\n"
                "> - **How to fix**: Check the redirects defined in `hargrove/frontend/next.config.ts` or backend middleware. Verify the URL redirects cleanly to its final destination."
            )
        elif "discovered" in coverage and "not indexed" in coverage:
            return (
                "> [!TIP]\n"
                "> **Info: Discovered - currently not indexed**\n"
                "> - Google knows about this page but hasn't crawled it yet. This is usually because crawling it would have overloaded the site, or Google scheduled it for later.\n"
                "> - **How to fix**: No immediate code fix needed. Ensure your site's speed and response times are excellent, and Google will crawl it automatically. You can also request indexing manually in Search Console."
            )
        elif "crawled" in coverage and "not indexed" in coverage:
            return (
                "> [!TIP]\n"
                "> **Info: Crawled - currently not indexed**\n"
                "> - Google has crawled the page but decided not to index it yet. It may be indexed in the future.\n"
                "> - **How to fix**: Improve the quality and uniqueness of the content. Check if the page is a duplicate or very similar to another page. Ensure proper self-referencing canonical tags are present."
            )
        elif "canonical" in coverage or "duplicate" in coverage:
            return (
                "> [Safe to Ignore]\n"
                "> **Info: Excluded / Duplicate (Alternative Page)**\n"
                "> - Google detected this page as a duplicate of a canonical page, and is correctly indexing the canonical version instead.\n"
                "> - **How to fix**: Confirm that the Google Selected Canonical matches your intended canonical URL. If correct, no action is needed."
            )
        else:
            return (
                "> [!WARNING]\n"
                "> **Action Required: Crawl or Indexing Issue**\n"
                "> - Google encountered an issue indexing this page (State: `{coverage}`).\n"
                "> - **How to fix**: Inspect server logs to check for 5xx errors or slow load times. Ensure the URL returns a clean 200 OK with proper HTML markup."
            ).format(coverage=coverage)
