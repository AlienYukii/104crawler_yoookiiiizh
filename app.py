"""
104 每日職缺爬蟲
執行方式：python app.py
"""

import csv
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml
from dotenv import load_dotenv

from crawler import crawl_all
from notifier import notify
from reporter import save_html

TAIPEI_TZ   = timezone(timedelta(hours=8))
REPORT_URL  = 'https://alienyukii.github.io/104crawler_yoookiiiizh/'

_AREA_PRIORITY = ['桃園市', '新竹市', '新竹縣', '台北市', '新北市']

def _location_rank(job: dict) -> int:
    loc = job.get('location', '')
    for i, city in enumerate(_AREA_PRIORITY):
        if city in loc:
            return i
    return len(_AREA_PRIORITY)


def load_config(path: str = 'config.yaml') -> dict:
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)


def save_results(jobs: list[dict], today: str) -> Path:
    results_dir = Path('results')
    results_dir.mkdir(exist_ok=True)

    date_str = today.replace('/', '-')

    # 序號遞增，不覆蓋舊檔
    seq = 1
    while (results_dir / f'{date_str}-{seq:02d}.csv').exists():
        seq += 1
    csv_path = results_dir / f'{date_str}-{seq:02d}.csv'

    fieldnames = ['title', 'company', 'location', 'salary', 'experience',
                  'education', 'keyword', 'date', 'url']

    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(jobs)

    summary = {
        'run_at': datetime.now(TAIPEI_TZ).isoformat(),
        'date': today,
        'total': len(jobs),
        'csv': str(csv_path),
    }
    (results_dir / 'latest.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8'
    )

    print(f'[*] 結果已存至 {csv_path}（{len(jobs)} 筆）')
    return csv_path


def main() -> None:
    load_dotenv()  # 本機開發：讀取 .env；GitHub Actions：直接讀環境變數

    config = load_config()
    today = datetime.now(TAIPEI_TZ).strftime('%Y/%m/%d')

    print(f'===== 104 職缺爬蟲 {today} =====')

    jobs = crawl_all(config)
    jobs.sort(key=_location_rank)

    results_dir = Path('results')
    config_yaml = Path('config.yaml').read_text(encoding='utf-8')
    save_results(jobs, today)
    save_html(jobs, today, results_dir, config_yaml=config_yaml)

    if jobs:
        print(f'\n[*] 今日共找到 {len(jobs)} 筆職缺，開始發送通知...')
    else:
        print('\n[*] 今日無新職缺，仍發送通知（空白報告）。')

    notify(jobs, config, report_url=REPORT_URL, results_dir=results_dir)
    print('===== 完成 =====')


if __name__ == '__main__':
    main()
