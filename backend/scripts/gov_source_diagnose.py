"""
Phase A Stage-Wise Source Diagnostic Tool (A1 & A2).
Strictly implements A1, A2, R5, and R6:
- Stage-wise breakdown: DNS -> TCP connect (10s) -> TLS handshake -> GET /robots.txt -> GET target path.
- Classifies failures: dns_failure | tcp_timeout | tls_error | http_403_challenge | http_429 | http_5xx | robots_disallow | parse_error | ok.
- Records comparison with default standard client to distinguish bot-blocking from network/site outages.
- Tests both registry endpoints and real feed endpoints (Income Tax, PIB, GSTN, ICAI IDTC, GSTAT, etc.).
"""

import socket
import ssl
import time
import json
import os
import sys
import urllib.robotparser
from urllib.parse import urlparse, urljoin
from datetime import datetime, timezone
import requests
import feedparser
from bs4 import BeautifulSoup

USER_AGENT = "FinLedgerBot/1.0 (+compliance@finledger.ai)"
TIMEOUT_TCP = 10.0
TIMEOUT_HTTP = 20.0
MAX_BYTES = 15 * 1024 * 1024

TARGET_SOURCES = [
    # ── Registry Sources ──
    {"code": "rbi_notifications", "name": "Reserve Bank of India (Notifications)", "url": "https://rbi.org.in/notifications_rss.xml", "base_url": "https://rbi.org.in"},
    {"code": "rbi_pressreleases", "name": "Reserve Bank of India (Press Releases)", "url": "https://rbi.org.in/pressreleases_rss.xml", "base_url": "https://rbi.org.in"},
    {"code": "gstcouncil", "name": "Goods and Services Tax Council", "url": "https://gstcouncil.gov.in", "base_url": "https://gstcouncil.gov.in"},
    {"code": "icai_announcements", "name": "ICAI Announcements", "url": "https://www.icai.org/category/announcements", "base_url": "https://www.icai.org"},
    {"code": "egazette_recent", "name": "e-Gazette of India (Extraordinary)", "url": "https://egazette.gov.in", "base_url": "https://egazette.gov.in"},
    {"code": "nfra_orders", "name": "National Financial Reporting Authority", "url": "https://nfra.gov.in/orders", "base_url": "https://nfra.gov.in"},
    {"code": "sebi_circulars", "name": "SEBI Circulars", "url": "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&smid=0&ssid=0", "base_url": "https://www.sebi.gov.in"},
    {"code": "cbic_taxinfo", "name": "CBIC Tax Information Publisher", "url": "https://taxinformation.cbic.gov.in", "base_url": "https://taxinformation.cbic.gov.in"},
    {"code": "cbic_gst", "name": "CBIC GST Portal", "url": "https://cbic-gst.gov.in", "base_url": "https://cbic-gst.gov.in"},
    {"code": "gstn_news", "name": "GST Portal News & Updates", "url": "https://www.gst.gov.in/newsandupdates", "base_url": "https://www.gst.gov.in"},
    {"code": "incometax_feed", "name": "Income Tax Department RSS", "url": "https://incometaxindia.gov.in/pages/tax-feeds.aspx", "base_url": "https://incometaxindia.gov.in"},
    {"code": "pib_rss", "name": "PIB Press Information Bureau RSS", "url": "https://pib.gov.in/RssMain.aspx", "base_url": "https://pib.gov.in"},
    {"code": "mca", "name": "Ministry of Corporate Affairs", "url": "https://www.mca.gov.in/content/mca/global/en/notifications-circulars.html", "base_url": "https://www.mca.gov.in"},
    {"code": "finmin", "name": "Ministry of Finance", "url": "https://finmin.gov.in", "base_url": "https://finmin.gov.in"},
    {"code": "dor", "name": "Department of Revenue", "url": "https://dor.gov.in", "base_url": "https://dor.gov.in"},
    {"code": "indiabudget", "name": "Union Budget of India", "url": "https://www.indiabudget.gov.in", "base_url": "https://www.indiabudget.gov.in"},
    {"code": "mahagst", "name": "Maharashtra State GST", "url": "https://mahagst.gov.in", "base_url": "https://mahagst.gov.in"},

    # ── A2 Real Endpoints / K11 Candidates ──
    {"code": "incometax_press_rss", "name": "Income Tax Press Release RSS Feed", "url": "https://www.incometaxindia.gov.in/press-release-rss-feed/-/asset_publisher/ovrx/rss", "base_url": "https://www.incometaxindia.gov.in"},
    {"code": "incometax_notif_rss", "name": "Income Tax Notifications RSS Feed", "url": "https://www.incometaxindia.gov.in/notifications-rss-feed/-/asset_publisher/9x0v/rss", "base_url": "https://www.incometaxindia.gov.in"},
    {"code": "incometax_circ_rss", "name": "Income Tax Circulars RSS Feed", "url": "https://www.incometaxindia.gov.in/circulars-rss-feed/-/asset_publisher/9x0v/rss", "base_url": "https://www.incometaxindia.gov.in"},
    {"code": "pib_mof_rss", "name": "PIB Ministry of Finance RSS", "url": "https://pib.gov.in/rss/RssMain.aspx?ModId=1", "base_url": "https://pib.gov.in"},
    {"code": "pib_mca_rss", "name": "PIB Ministry of Corporate Affairs RSS", "url": "https://pib.gov.in/rss/RssMain.aspx?ModId=2", "base_url": "https://pib.gov.in"},
    {"code": "gstcouncil_circulars", "name": "GST Council Circulars & Advisories", "url": "https://gstcouncil.gov.in/circulars-advisories", "base_url": "https://gstcouncil.gov.in"},
    {"code": "gstcouncil_whatsnew", "name": "GST Council What's New", "url": "https://gstcouncil.gov.in/whats-new", "base_url": "https://gstcouncil.gov.in"},
    {"code": "gstcouncil_newsletters", "name": "GST Council Newsletters", "url": "https://gstcouncil.gov.in/newsletters", "base_url": "https://gstcouncil.gov.in"},
    {"code": "icai_idtc", "name": "ICAI Indirect Taxes Committee", "url": "https://idtc.icai.org", "base_url": "https://idtc.icai.org"},
    {"code": "icai_dtc", "name": "ICAI Direct Taxes Committee", "url": "https://dtc.icai.org", "base_url": "https://dtc.icai.org"},
    {"code": "icai_accounting_std", "name": "ICAI Accounting Standards Overview", "url": "https://www.icai.org/post/accounting-standards-overview", "base_url": "https://www.icai.org"},
    {"code": "gstat", "name": "GST Appellate Tribunal", "url": "https://gstat.gov.in", "base_url": "https://gstat.gov.in"},
    {"code": "dggi", "name": "DGGI Directorate General of GST Intelligence", "url": "https://dggi.gov.in", "base_url": "https://dggi.gov.in"},
    {"code": "indiacode", "name": "India Code (Legislative Department)", "url": "https://www.indiacode.nic.in", "base_url": "https://www.indiacode.nic.in"},
    {"code": "gujarat_gst", "name": "Gujarat State Commercial Tax", "url": "https://commercialtax.gujarat.gov.in", "base_url": "https://commercialtax.gujarat.gov.in"},
    {"code": "karnataka_gst", "name": "Karnataka Commercial Taxes", "url": "https://ctax.kar.nic.in", "base_url": "https://ctax.kar.nic.in"},
    {"code": "tamilnadu_gst", "name": "Tamil Nadu Commercial Taxes", "url": "https://ctd.tn.gov.in", "base_url": "https://ctd.tn.gov.in"},
    {"code": "delhi_gst", "name": "Delhi Trade & Taxes", "url": "https://dvat.gov.in", "base_url": "https://dvat.gov.in"},
    {"code": "epfo", "name": "Employees Provident Fund Organisation", "url": "https://www.epfindia.gov.in", "base_url": "https://www.epfindia.gov.in"},
    {"code": "esic", "name": "Employees State Insurance Corporation", "url": "https://www.esic.gov.in", "base_url": "https://www.esic.gov.in"},
]


def diagnose_source(src: dict) -> dict:
    url = src["url"]
    base_url = src["base_url"]
    parsed = urlparse(url)
    hostname = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    scheme = parsed.scheme

    diag = {
        "code": src["code"],
        "name": src["name"],
        "url": url,
        "hostname": hostname,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ip_addresses": [],
        "dns_status": "pending",
        "tcp_status": "pending",
        "tls_status": "pending",
        "robots_status": "pending",
        "robots_allowed": None,
        "http_status_code": None,
        "classification": "pending",
        "failure_stage": None,
        "error_detail": None,
        "is_bot_blocked": False,
        "baseline_default_client_code": None,
        "baseline_default_client_error": None,
        "usable": False,
    }

    # 1. DNS Resolution Stage
    try:
        addr_info = socket.getaddrinfo(hostname, port, socket.AF_INET, socket.SOCK_STREAM)
        ips = sorted(list({x[4][0] for x in addr_info}))
        diag["ip_addresses"] = ips
        diag["dns_status"] = "ok"
    except Exception as e:
        diag["dns_status"] = "failed"
        diag["classification"] = "dns_failure"
        diag["failure_stage"] = "dns"
        diag["error_detail"] = f"DNS lookup failed for {hostname}: {str(e)}"
        return diag

    target_ip = ips[0]

    # 2. TCP Connect Stage (10s timeout)
    t0 = time.time()
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT_TCP)
        sock.connect((target_ip, port))
        diag["tcp_status"] = "ok"
    except socket.timeout:
        diag["tcp_status"] = "timeout"
        diag["classification"] = "tcp_timeout"
        diag["failure_stage"] = "tcp"
        diag["error_detail"] = f"TCP connection timed out to {target_ip}:{port} (10s)"
        if sock:
            sock.close()
        return diag
    except Exception as e:
        diag["tcp_status"] = "failed"
        diag["classification"] = "tcp_timeout"
        diag["failure_stage"] = "tcp"
        diag["error_detail"] = f"TCP connection failed to {target_ip}:{port}: {str(e)}"
        if sock:
            sock.close()
        return diag
    finally:
        if sock:
            sock.close()

    # 3. TLS Handshake Stage (if HTTPS)
    if scheme == "https":
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE  # Check if TLS completes at all
            with socket.create_connection((target_ip, port), timeout=TIMEOUT_TCP) as plain_s:
                with ctx.wrap_socket(plain_s, server_hostname=hostname) as ssl_s:
                    cipher = ssl_s.cipher()
                    diag["tls_status"] = f"ok ({cipher[0]} {cipher[1]})"
        except Exception as e:
            diag["tls_status"] = "failed"
            diag["classification"] = "tls_error"
            diag["failure_stage"] = "tls"
            diag["error_detail"] = f"TLS handshake failed: {str(e)}"
            return diag
    else:
        diag["tls_status"] = "not_applicable"

    # 4. GET /robots.txt Stage
    robots_url = f"{scheme}://{hostname}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    try:
        r_resp = requests.get(
            robots_url,
            headers={"User-Agent": USER_AGENT},
            timeout=10,
            verify=False,
            allow_redirects=True,
        )
        diag["robots_http_code"] = r_resp.status_code
        if r_resp.status_code == 200:
            rp.parse(r_resp.text.splitlines())
            allowed = rp.can_fetch(USER_AGENT, url)
            diag["robots_allowed"] = allowed
            diag["robots_status"] = "ok" if allowed else "disallowed"
        elif r_resp.status_code in (401, 403):
            diag["robots_status"] = f"challenge_{r_resp.status_code}"
            diag["robots_allowed"] = False
        else:
            diag["robots_status"] = f"http_{r_resp.status_code}"
            diag["robots_allowed"] = True  # Standard robots fallback: allowed if 404
    except Exception as e:
        diag["robots_status"] = f"error: {str(e)[:40]}"
        diag["robots_allowed"] = True

    if diag["robots_allowed"] is False and diag["robots_status"] == "disallowed":
        diag["classification"] = "robots_disallow"
        diag["failure_stage"] = "robots"
        diag["error_detail"] = f"Disallowed by robots.txt at {robots_url}"
        return diag

    # 5. GET Target Path Stage (Polite FinLedgerBot)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml,application/rss+xml,*/*;q=0.8",
    }
    resp = None
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT_HTTP, verify=False, allow_redirects=True)
        diag["http_status_code"] = resp.status_code
        status_code = resp.status_code
        resp_text = resp.text or ""

        # Check for WAF / bot challenge (R6)
        is_challenge = False
        block_reason = None

        if status_code in (401, 403):
            is_challenge = True
            block_reason = f"HTTP {status_code} WAF / Forbidden"

        if status_code == 429:
            diag["classification"] = "http_429"
            diag["failure_stage"] = "http_429"
            diag["error_detail"] = "Rate limited (HTTP 429)"
            return diag

        # Body inspection for challenge signatures
        lower_body = resp_text.lower()
        if "cf-ray" in resp.headers or "cloudflare" in lower_body and "attention required" in lower_body:
            is_challenge = True
            block_reason = "Cloudflare WAF challenge page"
        elif "akamai" in lower_body and "access denied" in lower_body:
            is_challenge = True
            block_reason = "Akamai WAF block"
        elif "shield square" in lower_body or "imperva" in lower_body:
            is_challenge = True
            block_reason = "Bot protection challenge"
        elif "request rejected" in lower_body and "support id" in lower_body:
            is_challenge = True
            block_reason = "F5 BIG-IP / ASM Application Security Manager WAF block"
        elif "nic firewall" in lower_body or "security policy" in lower_body:
            is_challenge = True
            block_reason = "NIC Gateway Firewall block"

        if is_challenge:
            diag["classification"] = "http_403_challenge"
            diag["failure_stage"] = "http_challenge"
            diag["is_bot_blocked"] = True
            diag["error_detail"] = block_reason
        elif status_code >= 500:
            diag["classification"] = "http_5xx"
            diag["failure_stage"] = "server_error"
            diag["error_detail"] = f"Server Error HTTP {status_code}"
        elif status_code == 200:
            # Test parsing
            if "xml" in url or "rss" in url or "xml" in resp.headers.get("Content-Type", ""):
                feed = feedparser.parse(resp_text)
                if feed.entries:
                    diag["classification"] = "ok"
                    diag["usable"] = True
                    diag["items_count"] = len(feed.entries)
                else:
                    diag["classification"] = "parse_error"
                    diag["failure_stage"] = "parser"
                    diag["error_detail"] = "RSS/XML parsed 0 entries"
            else:
                soup = BeautifulSoup(resp_text[:100000], "html.parser")
                links = soup.find_all("a")
                tables = soup.find_all("table")
                if len(links) > 5 or len(tables) > 0:
                    diag["classification"] = "ok"
                    diag["usable"] = True
                    diag["items_count"] = len(links)
                else:
                    diag["classification"] = "parse_error"
                    diag["failure_stage"] = "parser"
                    diag["error_detail"] = "HTML content lacks standard links/tables"
        else:
            diag["classification"] = f"http_{status_code}"
            diag["failure_stage"] = "http"
            diag["error_detail"] = f"Unexpected HTTP status {status_code}"

    except requests.exceptions.Timeout:
        diag["classification"] = "tcp_timeout"
        diag["failure_stage"] = "http_timeout"
        diag["error_detail"] = f"HTTP request timed out after {TIMEOUT_HTTP}s"
    except Exception as e:
        diag["classification"] = "network_error"
        diag["failure_stage"] = "network"
        diag["error_detail"] = str(e)

    # 6. Baseline Check with Default Client (requests standard UA) to distinguish bot block vs network down
    try:
        base_resp = requests.get(base_url, timeout=10, verify=False, allow_redirects=True)
        diag["baseline_default_client_code"] = base_resp.status_code
    except Exception as be:
        diag["baseline_default_client_error"] = str(be)[:50]

    return diag


def run_full_diagnosis(iteration: int = 1) -> dict:
    print(f"\n========================================================")
    print(f"RUNNING PROBE ITERATION {iteration} AT {datetime.now(timezone.utc).isoformat()}")
    print(f"========================================================\n")

    results = []
    for src in TARGET_SOURCES:
        print(f"Probing {src['code']:25} ({src['url'][:45]}...)...", end="", flush=True)
        time.sleep(1.0)  # Gentle gap between probing different domains
        d = diagnose_source(src)
        print(f" [{d['classification'].upper()}] - Stage: {d['failure_stage']} - Code: {d['http_status_code']}")
        results.append(d)

    return {
        "iteration": iteration,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sources_count": len(results),
        "results": results,
    }


def main():
    iterations_data = []
    # Run 3 iterations as required by A1
    for i in range(1, 4):
        res = run_full_diagnosis(iteration=i)
        iterations_data.append(res)
        if i < 3:
            print("\nWaiting 60 seconds before next iteration...\n")
            time.sleep(60)

    out_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "../docs/stage_wise_probe_results.json"))
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(iterations_data, f, indent=2)
    print(f"\nAll 3 iterations complete! Saved results to {out_file}")


if __name__ == "__main__":
    main()
