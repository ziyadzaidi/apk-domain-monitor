import os
import requests
import zipfile
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

def send_email(apk_domains, date_str, status_msg=""):
    sender_email = os.environ.get("SENDER_EMAIL")
    sender_password = os.environ.get("SENDER_PASSWORD")
    receiver_email = os.environ.get("RECEIVER_EMAIL")

    if not sender_email or not sender_password or not receiver_email:
        print("[-] Error: GitHub Secrets missing.")
        return

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = f"📊 APK Domains Report - {date_str}"

    if apk_domains:
        body = f"Bhai, {date_str} ki kul {len(apk_domains)} naye APK domains mili hain.\n\nList niche attach kar di hai.\nStatus: {status_msg}"
        msg.attach(MIMEText(body, 'plain'))
        
        content = "\n".join(apk_domains)
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(content.encode('utf-8'))
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="apk_domains_{date_str}.txt"')
        msg.attach(part)
    else:
        body = f"Bhai, {date_str} ke liye koi data nahi mila.\nStatus: {status_msg}"
        msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('://gmail.com', 587, timeout=30)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.quit()
        print("[+] Email sent successfully!")
    except Exception as e:
        print(f"[-] Email sending failed: {e}")

def get_apk_domains():
    headers = {'User-Agent': 'Mozilla/5.0'}
    apk_domains = []
    success_date = ""
    status = ""

    # FIXED: Added correct loop parameters [1, 2, 3] to check past 3 days dynamically
    for days_ago in:
        target_date = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%d')
        download_url = f"https://whoisds.com{target_date}.zip/nrd"
        zip_filename = f"{target_date}.zip"
        txt_filename = "domain-names.txt"
        
        print(f"[+] Checking WhoisDS for date: {target_date}")
        try:
            response = requests.get(download_url, headers=headers, stream=True, timeout=15)
            if response.status_code == 200:
                with open(zip_filename, 'wb') as f:
                    f.write(response.content)
                
                with zipfile.ZipFile(zip_filename, 'r') as z:
                    with z.open(txt_filename) as f:
                        for line in f:
                            domain = line.decode('utf-8', errors='ignore').strip().lower()
                            if 'apk' in domain:
                                apk_domains.append(domain)
                success_date = target_date
                status = f"WhoisDS processed data successfully for {target_date}."
                break
        except Exception as e:
            print(f"[-] Date {target_date} link process issue: {e}")
        finally:
            if os.path.exists(zip_filename): 
                os.remove(zip_filename)

    if not success_date:
        print("[-] Checking backup live feed...")
        backup_url = "https://githubusercontent.com"
        try:
            res = requests.get(backup_url, headers=headers, timeout=20)
            if res.status_code == 200:
                domains = res.text.split('\n')
                for d in domains:
                    if 'apk' in d.lower():
                        apk_domains.append(d.strip().lower())
                success_date = datetime.now().strftime('%Y-%m-%d')
                status = "Processed live fallback link."
        except Exception as e:
            status = f"Network failure: {e}"
            success_date = datetime.now().strftime('%Y-%m-%d')

    send_email(apk_domains, success_date, status)

if __name__ == "__main__":
    get_apk_domains()
