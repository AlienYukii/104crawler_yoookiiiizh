import time
import requests
from datetime import datetime, timezone, timedelta

AREA_CODES = {
    '台北市': '6001001000',
    '新北市': '6001002000',
    '桃園市': '6001008000',
    '新竹市': '6001007000',
    '新竹縣': '6001006000',
}

SEARCH_URL = 'https://www.104.com.tw/jobs/search/list'

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Referer': 'https://www.104.com.tw/jobs/search/',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8',
}

TAIPEI_TZ = timezone(timedelta(hours=8))


def today_taipei() -> str:
    return datetime.now(TAIPEI_TZ).strftime('%Y/%m/%d')


def _build_area_param(area_names: list[str]) -> str:
    return ','.join(AREA_CODES[a] for a in area_names if a in AREA_CODES)


def _fetch_page(keyword: str, area_param: str, page: int) -> list[dict]:
    params = {
        'ro': 0,
        'kwop': 7,
        'keyword': keyword,
        'expansionType': 'area,spec,com,job,wf,wktm',
        'area': area_param,
        'order': 15,   # 最新日期排序
        'asc': 0,
        'page': page,
        'mode': 's',
        'jobsource': '2018indexpoc',
    }
    try:
        resp = requests.get(SEARCH_URL, headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json().get('data', {}).get('list', [])
    except requests.RequestException as e:
        print(f'  [!] 請求失敗 keyword={keyword} page={page}: {e}')
        return []


def _parse_job(raw: dict, keyword: str) -> dict:
    job_no = raw.get('jobNo', '')
    return {
        'id': job_no,
        'title': raw.get('jobName', ''),
        'company': raw.get('custName', ''),
        'location': raw.get('jobAddrNoDesc', ''),
        'salary': raw.get('salaryDesc', '面議'),
        'experience': raw.get('periodDesc', ''),
        'education': raw.get('eduDesc', ''),
        'date': raw.get('appearDate', ''),
        'url': f'https://www.104.com.tw/job/{job_no}',
        'keyword': keyword,
    }


def crawl_all(config: dict) -> list[dict]:
    search = config['search']
    keywords: list[str] = search['keywords']
    area_param = _build_area_param(search.get('areas', []))
    max_pages: int = search.get('max_pages', 3)
    today_only: bool = search.get('today_only', True)
    today = today_taipei()

    seen_ids: set[str] = set()
    all_jobs: list[dict] = []

    for keyword in keywords:
        print(f'[*] 搜尋: {keyword}')
        kw_count = 0

        for page in range(1, max_pages + 1):
            raw_list = _fetch_page(keyword, area_param, page)
            if not raw_list:
                break

            page_had_today = False
            for raw in raw_list:
                appear_date = raw.get('appearDate', '')
                if today_only and appear_date != today:
                    continue
                page_had_today = True
                job = _parse_job(raw, keyword)
                if job['id'] not in seen_ids:
                    seen_ids.add(job['id'])
                    all_jobs.append(job)
                    kw_count += 1

            # 若本頁完全沒有今日職缺，後面幾頁更不會有
            if today_only and not page_had_today:
                break

            time.sleep(1)

        print(f'    → 今日新增 {kw_count} 筆 (累計去重 {len(all_jobs)} 筆)')
        time.sleep(0.5)

    return all_jobs
