import os
import smtplib
import textwrap
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta

TAIPEI_TZ = timezone(timedelta(hours=8))
MAX_TG_CHARS = 4000   # Telegram 單則上限 4096，留緩衝


# ── Email ──────────────────────────────────────────────────────────────────

def _build_html(jobs: list[dict], today: str, report_url: str = '') -> str:
    if not jobs:
        body_content = '<p style="color:#666;">今日無符合條件的新職缺。</p>'
    else:
        rows = ''.join(
            f'''<tr>
              <td><a href="{j["url"]}" style="color:#1a73e8;text-decoration:none;">{j["title"]}</a></td>
              <td>{j["company"]}</td>
              <td>{j["location"]}</td>
              <td>{j["salary"]}</td>
              <td>{j["experience"]}</td>
              <td style="color:#888;font-size:12px;">{j["keyword"]}</td>
            </tr>'''
            for j in jobs
        )
        body_content = f'''
        <p>共找到 <strong>{len(jobs)}</strong> 筆符合條件的職缺：</p>
        <table border="0" cellpadding="8" cellspacing="0"
               style="border-collapse:collapse;width:100%;font-size:14px;">
          <thead>
            <tr style="background:#1a73e8;color:#fff;">
              <th align="left">職缺</th>
              <th align="left">公司</th>
              <th align="left">地點</th>
              <th align="left">薪資</th>
              <th align="left">年資</th>
              <th align="left">關鍵字</th>
            </tr>
          </thead>
          <tbody>
            {rows}
          </tbody>
        </table>'''

    report_btn = (
        f'<p style="margin-top:20px;">'
        f'<a href="{report_url}" style="display:inline-block;padding:10px 20px;'
        f'background:#1a73e8;color:#fff;text-decoration:none;border-radius:6px;'
        f'font-weight:bold;">🔍 開啟互動式報告</a></p>'
    ) if report_url else ''

    return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:900px;margin:auto;padding:20px;">
  <h2 style="color:#1a73e8;">📋 104 每日職缺通知 — {today}</h2>
  {report_btn}
  {body_content}
  <hr style="margin-top:30px;border:none;border-top:1px solid #eee;">
  <p style="color:#aaa;font-size:12px;">由 104-job-crawler 自動產生</p>
</body></html>'''


def send_email(jobs: list[dict], config: dict, today: str, report_url: str = '') -> None:
    email_cfg = config['notification']['email']
    if not email_cfg.get('enabled', False):
        return

    sender = os.environ.get('EMAIL_SENDER', '')
    password = os.environ.get('EMAIL_PASSWORD', '')
    recipients: list[str] = email_cfg.get('recipients', [])

    if not sender or not password or not recipients:
        print('[Email] 缺少 EMAIL_SENDER / EMAIL_PASSWORD 或 recipients，略過。')
        return

    subject = f'【104職缺】{today} 共 {len(jobs)} 筆新職缺'
    html_body = _build_html(jobs, today, report_url)

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = ', '.join(recipients)
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(sender, password)
            smtp.sendmail(sender, recipients, msg.as_string())
        print(f'[Email] 已寄送至 {recipients}')
    except Exception as e:
        print(f'[Email] 寄送失敗: {e}')


# ── Telegram ───────────────────────────────────────────────────────────────

def _format_job_tg(job: dict) -> str:
    return (
        f'💼 [{job["title"]}]({job["url"]})\n'
        f'🏢 {job["company"]}　📍 {job["location"]}\n'
        f'💰 {job["salary"]}　🔍 #{job["keyword"]}\n'
    )


def _tg_send(bot_token: str, chat_id: str, text: str) -> None:
    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown', 'disable_web_page_preview': True}
    resp = requests.post(url, json=payload, timeout=10)
    if not resp.ok:
        print(f'[Telegram] 發送失敗: {resp.text}')


def send_telegram(jobs: list[dict], config: dict, today: str) -> None:
    tg_cfg = config['notification']['telegram']
    if not tg_cfg.get('enabled', False):
        return

    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')

    if not bot_token or not chat_id:
        print('[Telegram] 缺少 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID，略過。')
        return

    header = f'📋 *104 每日職缺 — {today}*\n共 {len(jobs)} 筆新職缺\n\n'
    if not jobs:
        _tg_send(bot_token, chat_id, header + '今日無符合條件的新職缺。')
        return

    # 拆成多則避免超過長度限制
    chunks: list[str] = []
    current = header
    for job in jobs:
        block = _format_job_tg(job) + '\n'
        if len(current) + len(block) > MAX_TG_CHARS:
            chunks.append(current)
            current = block
        else:
            current += block
    chunks.append(current)

    for chunk in chunks:
        _tg_send(bot_token, chat_id, chunk)
    print(f'[Telegram] 已發送 {len(chunks)} 則訊息')


# ── 統一入口 ────────────────────────────────────────────────────────────────

def notify(jobs: list[dict], config: dict, report_url: str = '') -> None:
    today = datetime.now(TAIPEI_TZ).strftime('%Y/%m/%d')
    send_email(jobs, config, today, report_url)
    send_telegram(jobs, config, today)
