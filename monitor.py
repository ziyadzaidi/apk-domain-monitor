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

    if not sender_email or not sender_password:
        print("[-] Email credentials missing in secrets.")
        return

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = f"📊 Daily APK Domains Report - {date_str}"

    if apk_domains:
        body = f"Bhai, aaj kul {len(apk_domains)} naye APK domains register hui hain.\n\nList integrity ke sath niche attach kar di hai."
        msg.attach(MIMEText(body, 'plain'))
        
        content = "\n".join(apk_domains)
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(content.encode('utf-8'))
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="apk_domains_{date_str}.txt"')
        msg.attach(part)
    else:
        body = "Bhai, aaj koi bhi APK domain register nahi hui."
        msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('://gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.quit()
        print("[+] Email sent successfully!")
    except Exception as e:
        print(f"[-] Email sending failed: {e}")

def get_apk_domains():
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"[+] Fetching data for date: {yesterday}")
    
    download_url = f"https://whoisds.com{yesterday}.zip/nrd"
    zip_filename = f"{yesterday}.zip"
    txt_filename = "domain-names.txt"

    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(download_url, headers=headers, stream=True)
    
    if response.status_code != 200:
        print("[-] File abhi tak server par upload nahi hui.")
        return

    with open(zip_filename, 'wb') as f:
        f.write(response.content)

    apk_domains = []
    try:
        with zipfile.ZipFile(zip_filename, 'r') as z:
            with z.open(txt_filename) as f:
                for line in f:
                    domain = line.decode('utf-8').strip().lower()
                    if 'apk' in domain:
                        apk_domains.append(domain)
    except Exception as e:
        print(f"[-] Zip error: {e}")
        return
    finally:
        if os.path.exists(zip_filename): os.remove(zip_filename)

    send_email(apk_domains, yesterday)

if __name__ == "__main__":
    get_apk_domains()
