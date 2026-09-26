# -*- coding: utf-8 -*-
"""
文明听书（csp_TStzgAmns）独立 Python 版
协议：2026-09-26 frida 反射驱动原版 TStzg（awdatabase 原版 dex）全链路抓包实锤
  配置:  GET http://117.72.112.234:8090/config/tingchina2025.txt  -> 首行业务域名
         GET http://117.72.112.234:8090/config/token.txt          -> search_token=xxx
  分类:  GET {base}category                              -> data:[{id,name}]
  列表:  GET {base}categoryList?categoryId&page&size=10  -> data:{count,list[]}
  搜索:  GET {base}appSearch?client=babala-android&search=&app_token=  -> data.bookData[]
  详情:  GET {base}book?bookId=        -> data.bookData[]
         GET {base}chapter?bookId=&sort=asc&page=1&size=9999 -> data.list[]
  播放:  GET {base}AppGetChapterUrl2023?bookId&chapterId&timeStamp&uid=&addItParapet=
         addItParapet = md5( md5(ts+KEY) + KEY )         -> src 直链 m4a
全明文 JSON，无需 jar/native，不依赖 aowuapp 签名服务器。
搜索规则：只匹配书名/主播（不搜简介），关键词整体包含不拆分。
兼容：OK影视 / 影视仓（TVBox Python 引擎，入口类必须名为 Spider）
"""
import re
import json
import time
import gzip
import hashlib
import urllib.request
import urllib.parse

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider:
        pass

BASE = 'https://app.365ting.com/listen/Apitzg2025/'
UA = 'TingShiJie/1.8.8 (m.i275.com)'
PLAY_UA = 'listen/1.9.2 (Linux;Android 13) ExoPlayerLib/2.8.4'
KEY = 'J9gSpfUlzYxE8Hn5IXiGaD2jVMrwAm0K'
HOST_URL = 'http://117.72.112.234:8090/config/tingchina2025.txt'
TOKEN_URL = 'http://117.72.112.234:8090/config/token.txt'
DEFAULT_SEARCH_TOKEN = 'abcSEARCH-2025'
TIMEOUT = 15


def _http_get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA,
                                               'Accept-Encoding': 'gzip'})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read()
        if (r.headers.get('Content-Encoding') or '').lower() == 'gzip':
            raw = gzip.decompress(raw)
        return raw.decode('utf-8', 'ignore')


class Spider(_BaseSpider):
    name = '文明听书'
    siteKey = 'TStzg'

    def __init__(self):
        self._base = BASE
        self._search_token = DEFAULT_SEARCH_TOKEN

    def init(self, extend=''):
        # 业务域名（失败用默认）
        try:
            lines = (_http_get(HOST_URL) or '').strip().splitlines()
            if lines and lines[0].strip():
                self._base = lines[0].strip()
                if not self._base.endswith('/'):
                    self._base += '/'
        except Exception:
            pass
        # 搜索 token（失败用默认）
        try:
            m = re.search(r'search_token=([^\s\r\n]+)', _http_get(TOKEN_URL) or '')
            if m:
                self._search_token = m.group(1).strip()
        except Exception:
            pass
        return ''

    def _api(self, path, params=None):
        url = self._base + path
        if params:
            url += '?' + urllib.parse.urlencode(params)
        return json.loads(_http_get(url))

    # ================= 首页分类 =================
    def homeContent(self, filter):
        classes = []
        try:
            for it in (self._api('category').get('data') or []):
                tid = str(it.get('id') or '')
                name = it.get('name') or ''
                if tid and name:
                    classes.append({'type_id': tid, 'type_name': name.strip()})
        except Exception:
            pass
        return {'class': classes, 'filters': {}}

    # ================= 分类列表 =================
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        try:
            info = self._api('categoryList',
                             {'categoryId': tid, 'page': pg, 'size': 10}).get('data') or {}
            total = int(info.get('count') or 0)
            vods = [self._vod(it) for it in (info.get('list') or [])]
            vods = [v for v in vods if v]
            return {'page': pg, 'pagecount': max(1, (total + 9) // 10),
                    'limit': 10, 'total': total, 'list': vods}
        except Exception:
            return {'page': pg, 'pagecount': 1, 'limit': 10, 'total': 0, 'list': []}

    def _remarks(self, it):
        parts = []
        anchor = it.get('bookAnchor') or it.get('bookName') or ''
        if anchor:
            parts.append(str(anchor))
        heat = it.get('heat')
        if heat:
            parts.append(str(heat))
        cnt = it.get('count')
        # bookUpdateStatus: 1=完结，否则连载
        if it.get('bookUpdateStatus') == 1:
            parts.append('完结')
        elif cnt:
            parts.append('更新至%s' % cnt)
        return ' '.join(parts)

    def _vod(self, it):
        vid = str(it.get('id') or '')
        name = it.get('bookTitle') or ''
        if not vid or not name:
            return None
        return {
            'vod_id': vid,
            'vod_name': name,
            'vod_pic': it.get('bookImage') or '',
            'vod_remarks': self._remarks(it),
            'vod_actor': it.get('bookAnchor') or '',
            'vod_content': it.get('bookDesc') or '',
        }

    # ================= 搜索 =================
    def searchContent(self, key, quick=True, pg=1):
        try:
            data = self._api('appSearch', {
                'client': 'babala-android',
                'search': key,
                'app_token': self._search_token,
            }).get('data') or {}
            vods = [self._vod(it) for it in (data.get('bookData') or [])]
            vods = [v for v in vods if v]
            # 规则 2a/2b：只保留书名或主播包含完整关键词的结果，不搜简介，关键词不拆分
            k = str(key or '')
            if k:
                vods = [v for v in vods
                        if k in (v.get('vod_name') or '') or k in (v.get('vod_actor') or '')]
            return {'page': 1, 'pagecount': 1, 'limit': len(vods) or 20,
                    'total': len(vods), 'list': vods}
        except Exception:
            return {'page': 1, 'pagecount': 1, 'limit': 20, 'total': 0, 'list': []}

    # OK影视 快搜入口（appSearch 接口本身无分页，pagecount=1 不翻页）
    def quickSearch(self, key, quick=True, pg=1):
        return self.searchContent(key, True, pg)

    # ================= 详情 =================
    def detailContent(self, ids):
        vid = str(ids[0]) if ids else ''
        if not vid:
            return {'list': []}
        meta = {}
        try:
            d = self._api('book', {'bookId': vid}).get('data') or {}
            bd = d.get('bookData')
            if isinstance(bd, list):
                meta = bd[0] if bd else {}
            elif isinstance(bd, dict):
                meta = bd
        except Exception:
            pass
        chapters = []
        try:
            d = self._api('chapter', {
                'bookId': vid, 'sort': 'asc', 'page': 1, 'size': 9999,
            }).get('data') or {}
            chapters = d.get('list') or []
        except Exception:
            pass
        eps = []
        for ch in chapters:
            title = str(ch.get('title') or '')
            cid = str(ch.get('chapterId') or '')
            if title and cid:
                eps.append('%s$%s@%s' % (title, vid, cid))
        vod = {
            'vod_id': vid,
            'vod_name': meta.get('bookTitle') or '',
            'vod_pic': meta.get('bookImage') or '',
            'vod_actor': meta.get('bookAnchor') or '',
            'vod_content': meta.get('bookDesc') or '',
            'vod_play_from': '文明听书',
            'vod_play_url': '#'.join(eps),
        }
        return {'list': [vod]}

    # ================= 播放 =================
    def playerContent(self, flag, id, vipFlags):
        try:
            book_id, chapter_id = str(id).split('@', 1)
            ts = str(int(time.time() * 1000))
            s1 = hashlib.md5((ts + KEY).encode('utf-8')).hexdigest()
            parapet = hashlib.md5((s1 + KEY).encode('utf-8')).hexdigest()
            data = self._api('AppGetChapterUrl2023', {
                'bookId': book_id,
                'chapterId': chapter_id,
                'timeStamp': ts,
                'uid': '',
                'addItParapet': parapet,
            })
            src = data.get('src') or ''
            if not src:
                return {}
            return {'parse': 0, 'playUrl': '', 'url': src,
                    'header': {'User-Agent': PLAY_UA}}
        except Exception:
            return {}


# 兼容按 csp 名反射加载的引擎
TStzgAmns = Spider
