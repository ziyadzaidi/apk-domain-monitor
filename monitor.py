#!/usr/bin/env python3
"""
APK Domain Monitor
-------------------
Fetches Newly Registered Domains (NRD) from WhoisDS (free daily feed),
falls back to a public mirror if WhoisDS is unavailable, filters for
domains containing "apk", and emails the result as a .txt attachment.

Designed to run unattended on GitHub Actions.
"""

import os
import sys
import io
import base64
import zipfile
import smtplib
import ssl
import time
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

import requests

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
KEYWORD = "apk"
DAYS_BACK_TO_TRY = 3          # WhoisDS data lags; try today, yesterday, day before
REQUEST_TIMEOUT = 30
MAX_EMAIL_RETRIES = 3
FALLBACK_URL = "https://raw.githubusercontent.com/cenk/nrd/main/nrd-last-10-days.txt"
OUTPUT_FILE = f"apk_domains_{datetime.utcnow().strftime('%Y-%m-%d')}.txt"

SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")


# ---------------------------------------------------------------------------
# STEP 1: FETCH DOMAINS FROM WHOISDS (PRIMARY SOURCE)
# ---------------------------------------------------------------------------
def fetch_whoisds_domains():
    """
    Try the last N days of WhoisDS NRD zip files until one succeeds.
    Returns a list of domain strings, or an empty list if all attempts fail.
    """
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (apk-domain-monitor)"})

    for days_ago in range(1, DAYS_BACK_TO_TRY + 1):
        target_date = (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        encoded_date = base64.b64encode(f"{target_date}.zip".encode()).decode()
        url = f"https://whoisds.com/whois-database/newly-registered-domains/{encoded_date}/nrd"

        print(f"[WhoisDS] Attempting {target_date} -> {url}")
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()

            if not resp.content or len(resp.content) < 100:
                print(f"[WhoisDS] Empty/too-small response for {target_date}, trying next day.")
                continue

            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                txt_files = [n for n in zf.namelist() if n.lower().endswith(".txt")]
                if not txt_files:
                    print(f"[WhoisDS] No .txt file inside zip for {target_date}.")
                    continue

                with zf.open(txt_files[0]) as f:
                    raw_text = f.read().decode("utf-8", errors="ignore")

            domains = [line.strip().lower() for line in raw_text.splitlines() if line.strip()]
            if domains:
                print(f"[WhoisDS] SUCCESS: {len(domains)} domains pulled for {target_date}.")
                return domains

        except zipfile.BadZipFile:
            print(f"[WhoisDS] Response for {target_date} was not a valid zip. Trying next day.")
        except requests.exceptions.RequestException as e:
            print(f"[WhoisDS] Network error for {target_date}: {e}. Trying next day.")

    print("[WhoisDS] All attempts exhausted. No data retrieved from primary source.")
    return []


# ---------------------------------------------------------------------------
# STEP 2: FALLBACK SOURCE
# ---------------------------------------------------------------------------
def fetch_fallback_domains():
    """
    Pulls a plain-text mirrored NRD list as backup if WhoisDS fails entirely.
    """
    print(f"[Fallback] Attempting {FALLBACK_URL}")
    try:
        resp = requests.get(FALLBACK_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        domains = [line.strip().lower() for line in resp.text.splitlines() if line.strip()]
        print(f"[Fallback] SUCCESS: {len(domains)} domains pulled from mirror.")
        return domains
    except requests.exceptions.RequestException as e:
        print(f"[Fallback] Failed: {e}")
        return []


# ---------------------------------------------------------------------------
# STEP 3: FILTER FOR KEYWORD
# ---------------------------------------------------------------------------
def filter_domains(domains, keyword):
    filtered = sorted(set(d for d in domains if keyword in d))
    print(f"[Filter] {len(filtered)} domains matched keyword '{keyword}'.")
    return filtered


# ---------------------------------------------------------------------------
# STEP 4: EMAIL DELIVERY (WITH RETRIES ACROSS SSL/STARTTLS)
# ---------------------------------------------------------------------------
def build_message(body_text, attachment_path, attachment_text):
    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg["Subject"] = f"APK Domain Report - {datetime.utcnow().strftime('%Y-%m-%d')}"
    msg.attach(MIMEText(body_text, "plain"))

    part = MIMEBase("application", "octet-stream")
    part.set_payload(attachment_text.encode("utf-8"))
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename={attachment_path}")
    msg.attach(part)
    return msg


def send_via_ssl_465(msg):
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=REQUEST_TIMEOUT, context=context) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)


def send_via_starttls_587(msg):
    context = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=REQUEST_TIMEOUT) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)


def send_email_with_retries(msg):
    """
    Tries SSL:465, then STARTTLS:587, each up to MAX_EMAIL_RETRIES times
    with exponential backoff. Returns True on success, False if all fail.
    """
    methods = [
        ("SSL:465", send_via_ssl_465),
        ("STARTTLS:587", send_via_starttls_587),
    ]

    for method_name, method_func in methods:
        for attempt in range(1, MAX_EMAIL_RETRIES + 1):
            try:
                print(f"[Email] Trying {method_name}, attempt {attempt}/{MAX_EMAIL_RETRIES}...")
                method_func(msg)
                print(f"[Email] SUCCESS via {method_name}.")
                return True
            except (smtplib.SMTPException, OSError, TimeoutError) as e:
                print(f"[Email] {method_name} attempt {attempt} failed: {e}")
                time.sleep(2 ** attempt)  # 2s, 4s, 8s backoff

    print("[Email] All SMTP methods and retries exhausted.")
    return False


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    if not all([SENDER_EMAIL, RECEIVER_EMAIL, SENDER_PASSWORD]):
        print("FATAL: Missing one or more required environment variables "
              "(SENDER_EMAIL, RECEIVER_EMAIL, SENDER_PASSWORD).")
        sys.exit(1)

    domains = fetch_whoisds_domains()
    source_used = "WhoisDS"

    if not domains:
        domains = fetch_fallback_domains()
        source_used = "Fallback Mirror"

    if not domains:
        print("FATAL: Both primary and fallback sources failed to return data.")
        # Still write an empty-state file so the workflow artifact isn't missing.
        attachment_text = "No data retrieved from any source today.\n"
        filtered = []
    else:
        filtered = filter_domains(domains, KEYWORD)
        if filtered:
            attachment_text = "\n".join(filtered)
        else:
            attachment_text = f"No domains containing '{KEYWORD}' found today.\n"

    # Always write the local file first -- this is our safety net regardless
    # of whether email succeeds.
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(attachment_text)
    print(f"[Output] Local file written: {OUTPUT_FILE}")

    body_text = (
        f"APK Domain Monitor Report\n"
        f"Date (UTC): {datetime.utcnow().strftime('%Y-%m-%d')}\n"
        f"Source used: {source_used}\n"
        f"Total domains scanned: {len(domains)}\n"
        f"Matches for '{KEYWORD}': {len(filtered)}\n\n"
        f"See attached file for the full list.\n"
    )

    msg = build_message(body_text, OUTPUT_FILE, attachment_text)
    email_sent = send_email_with_retries(msg)

    if not email_sent:
        print("WARNING: Email delivery failed after all retries. "
              "The result file has still been saved locally and will be "
              "uploaded as a GitHub Actions artifact (see workflow).")
        # Exit 0 (not 1) so the artifact-upload step in the workflow still runs.
        # We only want a hard failure if data collection itself failed.
        if not domains:
            sys.exit(1)
        sys.exit(0)

    print("Run complete. Email delivered successfully.")


if __name__ == "__main__":
    main()
