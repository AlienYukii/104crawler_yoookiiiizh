import time
import urllib.parse
from datetime import datetime, timezone, timedelta

from curl_cffi import requests as cf_requests

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

# 嘗試多個版本，若前一個被擋就換下一個
_IMPERSONATE_VERSIONS = ['chrome131', 'chrome124', 'chrome110']


def today_taipei() -> str:
    return datetime.now(TAIPEI_TZ).strftime('%Y%m%d')


def _build_area_param(area_names: list[str]) -> str:
    return ','.join(AREA_CODES[a] for a in area_names if a in AREA_CODES)


def _make_session(version: str) -> cf_requests.Session:
    session = cf_requests.Session(impersonate=version)
    print(f'[*] 初始化 session (impersonate={version})，訪問 104 首頁...')
    try:
        r = session.get(SEARCH_PAGE, timeout=15)
        print(f'    首頁 status={r.status_code} content-type={r.headers.get("content-type","?")[:40]}')
    except Exception as e:
        print(f'  [!] 首頁初始化失敗: {e}')
    time.sleep(1)
    return session


def _fetch_page(session: cf_requests.Session, keyword: str, area_param: str, page: int) -> list[dict] | None:
    """
    回傳 list[dict] 表示成功，None 表示請求本身失敗（需換 impersonate 版本）。
    回傳 [] 表示無資料。
    """
    params = {
        'area':      area_param,
        'asc':       '0',
        'keyword':   keyword,
        'mode':      's',
        'order':     '15',
        'page':      str(page),
        'pagesize':  '20',
        'jobsource': '2018indexpoc',
    }
    kw_enc  = urllib.parse.quote(keyword, safe='')
    referer = f'https://www.104.com.tw/jobs/search/?keyword={kw_enc}&area={area_param}&order=15&asc=0&page={page}&mode=s'
    headers = {
        'Referer': referer,
        'Accept':  'application/json, text/plain, */*',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8',
    }
    try:
        resp = session.get(API_URL, params=params, headers=headers, timeout=20)
        ct = resp.headers.get('content-type', '')
        print(f'    [DEBUG] keyword={keyword} page={page} status={resp.status_code} ct={ct[:50]}')
        if resp.status_code != 200:
            print(f'    [DEBUG] response preview: {resp.text[:200]}')
            return None  # 被擋，通知上層換版本
        if 'application/json' not in ct:
            print(f'    [DEBUG] 非 JSON 回應，可能是 Cloudflare challenge: {resp.text[:300]}')
            return None
        data = resp.json()
        return data.get('data', []) or []
    except Exception as e:
        print(f'  [!] 請求失敗 keyword={keyword} page={page}: {e}')
        return None


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

    # 依序嘗試不同 Chrome 版本
    session = None
    for ver in _IMPERSONATE_VERSIONS:
        s = _make_session(ver)
        # 用第一個關鍵字的第一頁測試連線
        test = _fetch_page(s, keywords[0], area_param, 1)
        if test is not None:
            session = s
            print(f'[*] 使用 impersonate={ver} 成功')
            break
        print(f'[!] impersonate={ver} 被擋，嘗試下一版本...')
        time.sleep(2)

    if session is None:
        print('[!] 所有 curl_cffi 版本均被擋，無法爬取資料')
        return []

    # 正式爬取（第一個關鍵字第一頁已測試過，直接納入）
    for keyword in keywords:
        print(f'[*] 搜尋: {keyword}')
        kw_count = 0

        for pg in range(1, max_pages + 1):
            raw_list = _fetch_page(session, keyword, area_param, pg)
            if raw_list is None:
                print(f'  [!] 請求失敗，跳過 keyword={keyword}')
                break
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
