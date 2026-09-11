import os
import requests
import zipfile
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

def send_email(apk_domains, date_str):
    sender_email = os.environ.get("SENDER_EMAIL")
    sender_password = os.environ.get("SENDER_PASSWORD")
    receiver_email = os.environ.get("RECEIVER_EMAIL")

    if not sender_email or not sender_password or not receiver_email:
        print("[-] Error: GitHub Secrets mein email credentials ya receiver email missing hai.")
        return

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = f"📊 Daily APK Domains Report - {date_str}"

    if apk_domains:
        body = f"Bhai, aaj kul {len(apk_domains)} naye APK domains register hui hain.\n\nList niche attach kar di hai."
        msg.attach(MIMEText(body, 'plain'))
        
        content = "\n".join(apk_domains)
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(content.encode('utf-8'))
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="apk_domains_{date_str}.txt"')
        msg.attach(part)
    else:
        body = f"Bhai, {date_str} ko koi bhi APK domain register nahi hui ya data blank tha."
        msg.attach(MIMEText(body, 'plain'))

    try:
        # Port 587 bilkul standard aur safe hai Gmail ke liye
        server = smtplib.SMTP('://gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.quit()
        print("[+] Email sent successfully!")
    except Exception as e:
        print(f"[-] Email sending failed: {e}")

def get_apk_domains():
    # WhoisDS kabhi kabhi pichle din ki file late upload karta hai, is liye hum 2 din pehle ka data check karte hain safe side ke liye
    target_date = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    print(f"[+] Fetching data for date: {target_date}")
    
    download_url = f"https://whoisds.com{target_date}.zip/nrd"
    zip_filename = f"{target_date}.zip"
    txt_filename = "domain-names.txt"

    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(download_url, headers=headers, stream=True, timeout=30)
        if response.status_code != 200:
            print(f"[-] File for {target_date} is not available on WhoisDS yet. Sending empty/status alert.")
            send_email([], target_date)
            return
            
        with open(zip_filename, 'wb') as f:
            f.write(response.content)
    except Exception as e:
        print(f"[-] Network Error while downloading: {e}")
        send_email([], target_date)
        return

    apk_domains = []
    try:
        with zipfile.ZipFile(zip_filename, 'r') as z:
            with z.open(txt_filename) as f:
                for line in f:
                    domain = line.decode('utf-8', errors='ignore').strip().lower()
                    if 'apk' in domain:
                        apk_domains.append(domain)
    except Exception as e:
        print(f"[-] Zip processing error: {e}")
    finally:
        if os.path.exists(zip_filename): 
            os.remove(zip_filename)

    send_email(apk_domains, target_date)

if __name__ == "__main__":
    get_apk_domains()
