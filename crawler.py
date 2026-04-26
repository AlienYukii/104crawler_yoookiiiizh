import time
import urllib.parse
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

AREA_CODES = {
    '台北市': '6001001000',
    '新北市': '6001002000',
    '桃園市': '6001008000',
    '新竹市': '6001007000',
    '新竹縣': '6001006000',
}

API_PATH    = '/jobs/search/api/jobs'
TAIPEI_TZ   = timezone(timedelta(hours=8))


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

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage'],
        )
        context = browser.new_context(
            locale='zh-TW',
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            ),
        )
        page = context.new_page()

        print('[*] 初始化瀏覽器，訪問 104 首頁...')
        try:
            page.goto('https://www.104.com.tw/jobs/search/',
                      wait_until='networkidle', timeout=30000)
        except Exception as e:
            print(f'  [!] 首頁載入超時（繼續執行）: {e}')
        time.sleep(2)

        for keyword in keywords:
            print(f'[*] 搜尋: {keyword}')
            kw_count = 0
            kw_enc = urllib.parse.quote(keyword, safe='')

            for pg in range(1, max_pages + 1):
                url = (
                    f'https://www.104.com.tw/jobs/search/?'
                    f'keyword={kw_enc}&area={area_param}'
                    f'&order=15&asc=0&page={pg}&mode=s'
                )

                raw_list: list[dict] = []

                def _on_resp(response, _raw=raw_list):
                    if API_PATH in response.url:
                        print(f'    [DEBUG] API hit status={response.status} url={response.url[:80]}')
                        try:
                            data = response.json()
                            items = data.get('data', []) or []
                            print(f'    [DEBUG] API returned {len(items)} items')
                            _raw.extend(items)
                        except Exception as ex:
                            print(f'    [DEBUG] JSON parse error: {ex}')

                page.on('response', _on_resp)
                try:
                    page.goto(url, wait_until='networkidle', timeout=25000)
                    print(f'    [DEBUG] page title: {page.title()[:60]!r}')
                    time.sleep(1)
                except Exception as e:
                    print(f'  [!] 頁面載入失敗 keyword={keyword} page={pg}: {e}')
                finally:
                    page.remove_listener('response', _on_resp)

                if not raw_list:
                    print(f'    [DEBUG] no API response captured, stopping at page {pg}')
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

        browser.close()

    return all_jobs
