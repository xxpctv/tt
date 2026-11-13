# -*- coding: utf-8 -*-
import re
import sys
import json
import requests
import urllib3
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    def init(self, extend=""):
        self.extend = extend
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 13)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.guipian360.org/",
            "Connection": "keep-alive",
        })
        self.session.verify = False

    def getName(self):
        return "鬼片360"

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def localProxy(self, param):
        return None

    host = 'https://www.guipian360.org'

    classes_config = [
        {"type_id": "1", "type_name": "鬼片大全"},
        {"type_id": "6", "type_name": "大陆鬼片"},
        {"type_id": "9", "type_name": "港台鬼片"},
        {"type_id": "8", "type_name": "林正英鬼片"},
        {"type_id": "7", "type_name": "日韩鬼片"},
        {"type_id": "11", "type_name": "欧美鬼片"},
        {"type_id": "10", "type_name": "泰国鬼片"},
        {"type_id": "3", "type_name": "恐怖片"},
        {"type_id": "2", "type_name": "电视剧"}
    ]

    def _get(self, url):
        return self.session.get(url, timeout=15)

    def extract_videos(self, html):
        vod_list = []
        blocks = re.findall(r'<[^>]+class="[^"]*u-movie[^"]*"[\s\S]*?</(?:article|div|li)>', html)
        for block in blocks:
            href_m = re.search(r'href="([^"]+)"', block)
            title_m = re.search(r'title="([^"]+)"', block)
            if not title_m:
                title_m = re.search(r'alt="([^"]+)"', block)
            if not title_m:
                title_m = re.search(r'<h2>([^<]+)</h2>', block)
            pic_m = re.search(r'data-original="([^"]+)"', block)
            if not pic_m:
                pic_m = re.search(r'src="([^"]+)"', block)
            remark_m = re.search(r'class="zhuangtai"[^>]*>(?:<span>)?([^<]+)', block)

            if href_m and title_m:
                href = href_m.group(1)
                id_m = re.search(r'/(\d+)\.html', href)
                if not id_m:
                    continue
                vod_id = id_m.group(1)
                vod_name = title_m.group(1).split('/')[0].strip().replace('《', '').replace('》', '')
                pic = pic_m.group(1) if pic_m else ""
                if pic.startswith('/'):
                    pic = self.host + pic
                remarks = remark_m.group(1).strip() if remark_m else ""
                vod_list.append({
                    "vod_id": vod_id,
                    "vod_name": vod_name,
                    "vod_pic": pic,
                    "vod_remarks": remarks
                })
        return vod_list

    def homeContent(self, filter):
        html = self._get(self.host).text
        return {"class": self.classes_config, "list": self.extract_videos(html)}

    def homeVideoContent(self):
        html = self._get(self.host).text
        return {"list": self.extract_videos(html)}

    def categoryContent(self, tid, pg, filter, extend):
        page_num = int(pg) if str(pg).isdigit() else 1
        url = f"{self.host}/list/{tid}_{page_num}.html" if page_num > 1 else f"{self.host}/list/{tid}.html"
        html = self._get(url).text
        vlist = self.extract_videos(html)
        page_count = 99
        pg_m = re.search(r'href="/list/\d+_(\d+)\.html"[^>]*>\.\.', html)
        if pg_m:
            page_count = int(pg_m.group(1))
        return {"list": vlist, "page": page_num, "pagecount": page_count, "limit": 20, "total": 9999}

    # 本地过滤要抓的分类列表页：9 个分类第 1 页 + 鬼片大全/电视剧第 2 页
    _LOCAL_URLS = [
        "/list/1_1.html", "/list/1_2.html", "/list/2_1.html", "/list/2_2.html",
        "/list/6_1.html", "/list/9_1.html", "/list/8_1.html", "/list/7_1.html",
        "/list/11_1.html", "/list/10_1.html", "/list/3_1.html",
    ]

    def searchContent(self, key, quick, pg="1"):
        """站点在线（Dalvik UA 才能过，浏览器 UA 一律 403），分类/详情/播放均正常，
        但 /search.php 的 searchword 关键词搜索被图片验证码 entangle（include/vdimgck.php）
        拦截，py 端过不了验证码，所以搜索改为「列表页本地过滤」：
        并发抓 9 个分类第 1 页 + 鬼片大全/电视剧第 2 页（约 460 条），按片名整串匹配。
        已知边界：
          1) 列表页条目只有片名，不含演员/导演，所以只能按片名搜（搜"林正英"搜不到片）；
          2) 全库约 6 万条、单类最多 736 页，这里只覆盖最新入库的约 460 条，老片搜不到；
          3) pg>1 直接返回空，避免同一批结果在每页重复出现。
        """
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        if page > 1:
            return {"list": [], "page": page, "pagecount": 1, "limit": 0, "total": 0}
        kw = re.sub(r"\s+", "", key or "").lower()
        if not kw:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}
        try:
            with ThreadPoolExecutor(max_workers=6) as ex:
                bodies = list(ex.map(self._fetch_list, self._LOCAL_URLS))
        except Exception as e:
            print(f"鬼片之家 search error: {e}")
            return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}
        items, seen = [], set()
        for html in bodies:
            for it in self.extract_videos(html or ""):
                vid = it.get("vod_id")
                if vid in seen:
                    continue
                seen.add(vid)
                for f in ("vod_name", "vod_sub", "vod_actor", "vod_director"):
                    if kw in re.sub(r"\s+", "", str(it.get(f, "") or "")).lower():
                        items.append(it)
                        break
        return {"list": items, "page": 1, "pagecount": 1,
                "limit": len(items), "total": len(items)}

    def _fetch_list(self, path):
        try:
            return self._get(f"{self.host}{path}").text
        except Exception:
            return ""

    def detailContent(self, ids):
        vod_id = ids[0]
        html = self._get(f"{self.host}/nv/{vod_id}.html").text
        soup = BeautifulSoup(html, 'html.parser')

        tabs = [a.text.strip() for a in soup.select('#tv_tab li a')]
        if not tabs:
            tabs = ["默认播放线路"]
        lists = soup.select('#tv_tab .list')
        play_urls = []
        for lst in lists:
            sub_urls = []
            for a in lst.select('ul.abc li a'):
                name = a.text.strip()
                href = a.get('href', '')
                vid_m = re.search(r'/play/(.*?)\.html', href)
                if vid_m:
                    sub_urls.append(f"{name}${vid_m.group(1)}")
            play_urls.append("#".join(sub_urls))
        if len(play_urls) < len(tabs):
            play_urls += [""] * (len(tabs) - len(play_urls))

        name_m = re.search(r'<h1[^>]*>(.*?)</h1>', html)
        vod_name = name_m.group(1).split('/')[0].strip().replace('《', '').replace('》', '') if name_m else ''
        if not vod_name:
            title_m = re.search(r'<title>(.*?)</title>', html)
            if title_m:
                vod_name = title_m.group(1).split('-')[0].strip().replace('《', '').replace('》', '')
        if not vod_name:
            vod_name = '未知影片'

        def get_meta(pattern, default=""):
            m = re.search(pattern, html)
            return m.group(1).strip() if m else default

        pic_m = re.search(r'<img[^>]+data-original="([^"]+)"', html)
        if not pic_m:
            pic_m = re.search(r'<img[^>]+src="([^"]+)"[^>]*class="lazy"', html)
        vod_pic = pic_m.group(1) if pic_m else ""
        if vod_pic.startswith('/'):
            vod_pic = self.host + vod_pic

        vod_content_m = re.search(r'<p class="jianjie-p"[^>]*>([\s\S]*?)</p>', html)
        vod_content = re.sub(r'<.*?>', '', vod_content_m.group(1)).strip() if vod_content_m else "暂无该影片的相关简介。"

        return {"list": [{
            "vod_id": vod_id, "vod_name": vod_name, "vod_pic": vod_pic, "vod_content": vod_content,
            "vod_director": get_meta(r'<span>导演：</span>(.*?)</li>', "未知"),
            "vod_actor": get_meta(r'<span>主演：</span>(.*?)</li>', "未知"),
            "vod_year": get_meta(r'<strong>(\d{4})年</strong>', "近期"),
            "vod_area": get_meta(r'地区：</span><a[^>]*>(.*?)</a>', "未知"),
            "vod_play_from": "$$$".join(tabs),
            "vod_play_url": "$$$".join(play_urls)
        }]}

    def playerContent(self, flag, id, vipFlags):
        play_url = f"{self.host}/play/{id}.html"
        html = self._get(play_url).text
        if 'var now="' not in html:
            play_url = f"{self.host}/play/{id}-0-0.html"
            html = self._get(play_url).text
        m3u8_m = re.search(r'var now="([^"]+)"', html)
        if m3u8_m:
            return {"parse": 0, "url": m3u8_m.group(1), "header": {"User-Agent": "Dalvik/2.1.0 (Linux; U; Android 13)", "Referer": self.host + "/"}}
        return {"parse": 1, "url": play_url, "header": {"User-Agent": "Dalvik/2.1.0 (Linux; U; Android 13)", "Referer": self.host + "/"}}
