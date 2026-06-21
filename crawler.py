import time
import urllib.parse
from datetime import datetime, timezone, timedelta

import requests

AREA_CODES = {
    '台北市': '6001001000',
    '新北市': '6001002000',
    '桃園市': '6001008000',
    '新竹市': '6001007000',
    '新竹縣': '6001006000',
}

API_URL  = 'https://www.104.com.tw/jobs/search/api/jobs'
TAIPEI_TZ = timezone(timedelta(hours=8))

_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
}


def today_taipei() -> str:
    return datetime.now(TAIPEI_TZ).strftime('%Y%m%d')


def _build_area_param(area_names: list[str]) -> str:
    return ','.join(AREA_CODES[a] for a in area_names if a in AREA_CODES)


def _parse_job(raw: dict, keyword: str) -> dict:
    return {
        'id':         raw.get('jobNo', ''),
        'title':      raw.get('jobName', ''),
        'company':    raw.get('custName', ''),
        'location':   raw.get('jobAddrNoDesc', ''),
        'salary':     raw.get('salaryDesc', '面議'),
        'experience': raw.get('periodDesc', ''),
        'education':  raw.get('eduDesc', ''),
        'date':       raw.get('appearDate', ''),
        'url':        raw.get('link', {}).get('job', ''),
        'keyword':    keyword,
    }


def crawl_all(config: dict) -> list[dict]:
    search     = config['search']
    keywords   = search['keywords']
    area_param = _build_area_param(search.get('areas', []))
    max_pages  = search.get('max_pages', 3)
    today_only = search.get('today_only', True)
    today      = today_taipei()

    seen_ids: set[str] = set()
    all_jobs:  list[dict] = []

    session = requests.Session()
    session.headers.update(_HEADERS)

    # warm-up: 取得首頁 cookies
    print('[*] 初始化 session，訪問 104 首頁...')
    try:
        session.get('https://www.104.com.tw/jobs/search/', timeout=15)
    except Exception as e:
        print(f'  [!] 首頁初始化失敗（繼續執行）: {e}')
    time.sleep(1)

    for keyword in keywords:
        print(f'[*] 搜尋: {keyword}')
        kw_count = 0
        kw_enc   = urllib.parse.quote(keyword, safe='')
        referer  = (
            f'https://www.104.com.tw/jobs/search/'
            f'?keyword={kw_enc}&area={area_param}'
            f'&order=15&asc=0&page=1&mode=s'
        )

        for pg in range(1, max_pages + 1):
            params = {
                'keyword':   keyword,
                'area':      area_param,
                'order':     '15',
                'asc':       '0',
                'page':      str(pg),
                'mode':      's',
                'jobsource': '2018indexpoc',
            }
            try:
                resp = session.get(
                    API_URL,
                    params=params,
                    headers={'Referer': referer},
                    timeout=20,
                )
                resp.raise_for_status()
                data  = resp.json()
                items = data.get('data', []) or []
                print(f'    [DEBUG] page={pg} status={resp.status_code} items={len(items)}')
            except Exception as e:
                print(f'  [!] API 請求失敗 keyword={keyword} page={pg}: {e}')
                break

            if not items:
                break

            page_had_today = False
            for raw in items:
                appear_date = raw.get('appearDate', '')
                if today_only and appear_date != today:
                    continue
                page_had_today = True
                job = _parse_job(raw, keyword)
                if job['id'] not in seen_ids:
                    seen_ids.add(job['id'])
                    all_jobs.append(job)
                    kw_count += 1

            if today_only and not page_had_today:
                break

            time.sleep(0.8)

        print(f'    → 今日新增 {kw_count} 筆 (累計去重 {len(all_jobs)} 筆)')
        time.sleep(0.5)

    return all_jobs
