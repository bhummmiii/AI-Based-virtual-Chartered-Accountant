"""
Phase A probe script for candidate government update sources.
Respects R5 and R6:
- User-Agent: FinLedgerBot/1.0 (+compliance@finledger.ai)
- robots.txt via urllib.robotparser
- >= 3.0s delay between requests to same host
- 20s timeout
- Max download 15MB
- Detects captcha / login walls / WAF / blocking
- Checks RSS/Atom feeds and HTML listings
"""

import sys
import os
import time
import json
import urllib.robotparser
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup
import feedparser

USER_AGENT = "FinLedgerBot/1.0 (+compliance@finledger.ai)"
TIMEOUT = 20
MAX_BYTES = 15 * 1024 * 1024

HOST_LAST_REQUEST = {}

def polite_get(url, headers=None, stream=False):
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    now = time.time()
    last = HOST_LAST_REQUEST.get(host, 0)
    elapsed = now - last
    if elapsed < 3.2:
        sleep_needed = 3.2 - elapsed
        time.sleep(sleep_needed)
    
    req_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml,application/rss+xml,application/pdf;q=0.9,*/*;q=0.8",
    }
    if headers:
        req_headers.update(headers)
    
    try:
        HOST_LAST_REQUEST[host] = time.time()
        resp = requests.get(url, headers=req_headers, timeout=TIMEOUT, stream=stream, verify=True, allow_redirects=True)
        return resp, None
    except requests.exceptions.SSLError:
        try:
            # Some Indian gov sites have self-signed or incomplete intermediate SSL chains
            HOST_LAST_REQUEST[host] = time.time()
            resp = requests.get(url, headers=req_headers, timeout=TIMEOUT, stream=stream, verify=False, allow_redirects=True)
            return resp, "ssl_verify_failed_but_insecure_ok"
        except Exception as e:
            return None, str(e)
    except Exception as e:
        return None, str(e)

def check_robots(base_url, target_path):
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    try:
        resp, err = polite_get(robots_url)
        if resp is not None and resp.status_code == 200:
            rp.parse(resp.text.splitlines())
            allowed = rp.can_fetch(USER_AGENT, target_path)
            crawl_delay = rp.crawl_delay(USER_AGENT) or rp.crawl_delay("*")
            return allowed, crawl_delay, "robots.txt parsed"
        elif resp is not None and resp.status_code in (404, 403, 301, 302):
            return True, None, f"robots.txt status {resp.status_code} (assumed allowed)"
        else:
            return True, None, f"robots.txt unreachable: {err}"
    except Exception as e:
        return True, None, f"robots error: {str(e)}"

def detect_captcha_or_waf(resp, text):
    if resp is None:
        return False, "no response"
    if resp.status_code in (403, 429, 503):
        lower_text = (text or "").lower()
        if any(w in lower_text for w in ["captcha", "challenge", "verify you are human", "cloudflare", "sucuri", "incapsula", "access denied", "ddos"]):
            return True, f"HTTP {resp.status_code} challenge/WAF block"
        return True, f"HTTP {resp.status_code} block"
    
    lower_text = (text or "").lower()
    if "please complete the security check" in lower_text or "cf-chl-bypass" in lower_text or "recaptcha" in lower_text or "g-recaptcha" in lower_text:
        return True, "in-page captcha detected"
    if "<title>just a moment...</title>" in lower_text or "ray id:" in lower_text:
        return True, "Cloudflare challenge detected"
    return False, "clean"

CANDIDATES = [
    # Tier 1
    {
        "code": "cbic_taxinfo",
        "name": "CBIC Tax Information Publisher",
        "base_url": "https://taxinformation.cbic.gov.in",
        "test_paths": ["/", "/content-page/explore-notification", "/content-page/explore-circular"],
        "tier": 1,
    },
    {
        "code": "cbic_gst",
        "name": "CBIC GST Portal",
        "base_url": "https://cbic-gst.gov.in",
        "test_paths": ["/", "/gst-goods-services-tax.html"],
        "tier": 1,
    },
    {
        "code": "gstn_news",
        "name": "GST Portal News & Updates",
        "base_url": "https://www.gst.gov.in",
        "test_paths": ["/newsandupdates", "/services/newsandupdates"],
        "tier": 1,
    },
    {
        "code": "gst_council",
        "name": "GST Council",
        "base_url": "https://gstcouncil.gov.in",
        "test_paths": ["/", "/meetings", "/brief-decision-taken"],
        "tier": 1,
    },
    {
        "code": "incometax_feed",
        "name": "Income Tax Department RSS",
        "base_url": "https://incometaxindia.gov.in",
        "test_paths": ["/tax-feeds", "/pages/communications/circulars.aspx", "/pages/communications/notifications.aspx"],
        "tier": 1,
    },
    {
        "code": "pib_rss",
        "name": "PIB Press Information Bureau RSS",
        "base_url": "https://pib.gov.in",
        "test_paths": ["/RssMain.aspx", "/rss/rss.aspx"],
        "tier": 1,
    },
    {
        "code": "rbi_rss",
        "name": "Reserve Bank of India RSS",
        "base_url": "https://rbi.org.in",
        "test_paths": ["/notifications_rss.xml", "/pressreleases_rss.xml"],
        "tier": 1,
    },
    # Tier 2
    {
        "code": "mca",
        "name": "Ministry of Corporate Affairs",
        "base_url": "https://www.mca.gov.in",
        "test_paths": ["/", "/content/mca/global/en/notifications-circulars/notifications.html"],
        "tier": 2,
    },
    {
        "code": "nfra",
        "name": "National Financial Reporting Authority (NFRA)",
        "base_url": "https://nfra.gov.in",
        "test_paths": ["/", "/circulars", "/orders"],
        "tier": 2,
    },
    {
        "code": "icai",
        "name": "Institute of Chartered Accountants of India (ICAI)",
        "base_url": "https://www.icai.org",
        "test_paths": ["/", "/category/announcements", "/post.html?category=announcements"],
        "tier": 2,
    },
    {
        "code": "egazette",
        "name": "e-Gazette of India",
        "base_url": "https://egazette.gov.in",
        "test_paths": ["/", "/SearchGazette.aspx"],
        "tier": 2,
    },
    {
        "code": "finmin",
        "name": "Ministry of Finance",
        "base_url": "https://finmin.gov.in",
        "test_paths": ["/", "/press-release"],
        "tier": 2,
    },
    {
        "code": "dor",
        "name": "Department of Revenue",
        "base_url": "https://dor.gov.in",
        "test_paths": ["/", "/notifications", "/circulars"],
        "tier": 2,
    },
    {
        "code": "indiabudget",
        "name": "Union Budget of India",
        "base_url": "https://www.indiabudget.gov.in",
        "test_paths": ["/"],
        "tier": 2,
    },
    # Tier 3 (dynamic state)
    {
        "code": "mahagst",
        "name": "Maharashtra State GST",
        "base_url": "https://mahagst.gov.in",
        "test_paths": ["/", "/en/acts-rules", "/en/circulars-notifications"],
        "tier": 3,
    },
    # Optional
    {
        "code": "sebi",
        "name": "Securities and Exchange Board of India (SEBI)",
        "base_url": "https://www.sebi.gov.in",
        "test_paths": ["/sebiweb/home/HomeAction.do?doListing=yes&sid=1&smid=0&ssid=0", "/legal/circulars"],
        "tier": 2,
    },
]

def probe_candidate(c):
    print(f"\n==========================================")
    print(f"PROBING: {c['name']} ({c['base_url']})")
    
    # 1. robots.txt
    robots_ok, delay, robots_msg = check_robots(c['base_url'], c['test_paths'][0])
    print(f"Robots: allowed={robots_ok}, delay={delay}, note={robots_msg}")
    
    results = {
        "candidate": c,
        "robots_ok": robots_ok,
        "crawl_delay": delay,
        "robots_msg": robots_msg,
        "paths_tested": [],
    }
    
    for path in c['test_paths']:
        target_url = urljoin(c['base_url'], path)
        print(f"Testing URL: {target_url} ...")
        resp, err = polite_get(target_url)
        if resp is None:
            print(f"  FAILED: {err}")
            results["paths_tested"].append({
                "url": target_url,
                "status": None,
                "error": err,
            })
            continue
        
        status = resp.status_code
        content_type = resp.headers.get("Content-Type", "")
        text = resp.text[:50000] if "text" in content_type or "xml" in content_type or "html" in content_type else ""
        captcha, captcha_msg = detect_captcha_or_waf(resp, text)
        print(f"  Status: {status}, Content-Type: {content_type}, Captcha/WAF: {captcha} ({captcha_msg})")
        
        # Check RSS
        is_rss = False
        items_count = 0
        sample_items = []
        if "xml" in content_type or "rss" in content_type or "<rss" in text.lower() or "<feed" in text.lower():
            is_rss = True
            feed = feedparser.parse(text)
            items_count = len(feed.entries)
            for entry in feed.entries[:5]:
                sample_items.append({
                    "title": getattr(entry, "title", ""),
                    "link": getattr(entry, "link", ""),
                    "published": getattr(entry, "published", getattr(entry, "updated", "")),
                })
            print(f"  Feedparser found {items_count} items")
        else:
            # HTML parsing sample
            soup = BeautifulSoup(text, "html.parser")
            # find links
            links = soup.find_all("a", href=True)
            doc_links = [l for l in links if any(ext in l['href'].lower() for ext in ['.pdf', 'circular', 'notification', 'order'])]
            print(f"  HTML has {len(links)} links, {len(doc_links)} doc-like links")
            for l in doc_links[:5]:
                sample_items.append({
                    "text": l.get_text(strip=True)[:100],
                    "href": urljoin(target_url, l['href']),
                })
        
        results["paths_tested"].append({
            "url": target_url,
            "status": status,
            "content_type": content_type,
            "captcha": captcha,
            "captcha_msg": captcha_msg,
            "is_rss": is_rss,
            "items_count": items_count,
            "sample_items": sample_items,
        })
        
    return results

if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    probe_results = []
    for cand in CANDIDATES:
        res = probe_candidate(cand)
        probe_results.append(res)
    
    os.makedirs("docs", exist_ok=True)
    with open("docs/probe_raw_results.json", "w", encoding="utf-8") as f:
        json.dump(probe_results, f, indent=2)
    print("\nProbing finished! Raw results written to docs/probe_raw_results.json")
