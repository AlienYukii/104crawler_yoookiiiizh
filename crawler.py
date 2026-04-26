import time
import urllib.parse
from curl_cffi import requests as cf_requests
from datetime import datetime, timezone, timedelta

AREA_CODES = {
    '台北市': '6001001000',
    '新北市': '6001002000',
    '桃園市': '6001008000',
    '新竹市': '6001007000',
    '新竹縣': '6001006000',
}

SEARCH_PAGE = 'https://www.104.com.tw/jobs/search/'
API_URL     = 'https://www.104.com.tw/jobs/search/api/jobs'
TAIPEI_TZ   = timezone(timedelta(hours=8))


def today_taipei() -> str:
    # 格式與 104 API 回傳的 appearDate (YYYYMMDD) 一致
    return datetime.now(TAIPEI_TZ).strftime('%Y%m%d')


def _build_area_param(area_names: list[str]) -> str:
    return ','.join(AREA_CODES[a] for a in area_names if a in AREA_CODES)


def _make_session() -> cf_requests.Session:
    """模擬真實 Chrome 指紋，先訪問首頁取得 Cloudflare Cookie。"""
    session = cf_requests.Session(impersonate='chrome124')
    try:
        session.get(SEARCH_PAGE, timeout=15)
    except Exception:
        pass
    time.sleep(1)
    return session


def _fetch_page(session: cf_requests.Session, keyword: str, area_param: str, page: int) -> list[dict]:
    qs = urllib.parse.urlencode({
        'area':     area_param,
        'asc':      0,
        'keyword':  keyword,
        'mode':     's',
        'order':    15,
        'page':     page,
        'pagesize': 20,
    }, encoding='utf-8')
    url = f'{API_URL}?{qs}'
    kw_qs = urllib.parse.urlencode({'keyword': keyword}, encoding='utf-8')
    headers = {
        'Referer': f'https://www.104.com.tw/jobs/search/?{kw_qs}',
        'Accept':  'application/json, text/plain, */*',
    }
    try:
        resp = session.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        if 'application/json' not in resp.headers.get('content-type', ''):
            print(f'  [!] 非 JSON 回應 keyword={keyword} page={page}')
            return []
        return resp.json().get('data', []) or []
    except Exception as e:
        print(f'  [!] 請求失敗 keyword={keyword} page={page}: {e}')
        return []


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

    session   = _make_session()
    seen_ids: set[str] = set()
    all_jobs:  list[dict] = []

    for keyword in keywords:
        print(f'[*] 搜尋: {keyword}')
        kw_count = 0

        for pg in range(1, max_pages + 1):
            raw_list = _fetch_page(session, keyword, area_param, pg)
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

            if today_only and not page_had_today:
                break

            time.sleep(1)

        print(f'    → 今日新增 {kw_count} 筆 (累計去重 {len(all_jobs)} 筆)')
        time.sleep(0.5)

    return all_jobs
