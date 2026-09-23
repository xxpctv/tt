# -*- coding: utf-8 -*-
"""Ajeo-TStzg 文明听书（csp_TStzgAmns）独立版
协议依据 aowu.jar 原版 TStzg 全链路实测复现：category/categoryList/appSearch/book/chapter/AppGetChapterUrl2023
本机 urllib 直连验证：分类 16 个、列表、详情两段（book 元数据 + chapter 章节）、播放 addItParapet 签名均 200 明文 JSON。
"""
import json
import re
import time
import urllib.request
import urllib.parse
import hashlib

BASE = 'https://app.365ting.com/listen/Apitzg2025/'
UA = 'TingShiJie/1.8.8 (m.i275.com)'
KEY = 'J9gSpfUlzYxE8Hn5IXiGaD2jVMrwAm0K'
TOKEN_URL = 'http://117.72.112.234:8090/config/token.txt'
HOST_URL = 'http://117.72.112.234:8090/config/tingchina2025.txt'
SEARCH_TOKEN = 'abcSEARCH-2025'
TIMEOUT = 15


class TStzgAmns:
    _base = BASE
    _headers = {}
    SEARCH_TOKEN = SEARCH_TOKEN

    def _http(self, url, params=None):
        if params:
            url = url + ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=self._headers)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read().decode('utf-8', 'ignore')

    def init(self, context, ext):
        try:
            text = self._http(HOST_URL)
            host = (text or '').strip().splitlines()
            if host:
                self._base = host[0].strip()
                if not self._base.endswith('/'):
                    self._base += '/'
        except Exception:
            pass
        try:
            text = self._http(TOKEN_URL)
            m = re.search(r'search_token=([^\r\n]+)', text or '')
            if m:
                self.SEARCH_TOKEN = m.group(1).strip()
        except Exception:
            pass
        self._headers = {'User-Agent': UA}

    def _get(self, path, params=None):
        return json.loads(self._http(self._base + path, params))

    def _build_filters(self):
        return {}

    def homeContent(self, filterable=False):
        try:
            data = self._get('category')
            arr = (data or {}).get('data') or []
            classes = []
            for it in arr:
                try:
                    tid = str(it.get('id'))
                    name = it.get('name') or ''
                    if tid and name:
                        classes.append({'type_id': tid, 'type_name': name})
                except Exception:
                    pass
            return json.dumps({'class': classes, 'filters': self._build_filters()}, ensure_ascii=False)
        except Exception:
            return json.dumps({'class': [], 'filters': self._build_filters()}, ensure_ascii=False)

    def categoryContent(self, tid, pg, filterable=False, extend=None):
        try:
            data = self._get('categoryList', {'categoryId': tid, 'page': int(pg), 'size': 10})
            info = (data or {}).get('data') or {}
            lst = info.get('list') or []
            total = int(info.get('count') or 0)
            page = int(info.get('page') or 1)
            pagecount = (total + 9) // 10
            vods = []
            for it in lst:
                v = self._extract_vod(it)
                if v:
                    vods.append(v)
            return json.dumps({'page': page, 'pagecount': pagecount, 'limit': 10, 'total': total, 'list': vods},
                              ensure_ascii=False)
        except Exception:
            return json.dumps({'page': 1, 'pagecount': 1, 'limit': 10, 'total': 0, 'list': []}, ensure_ascii=False)

    def _extract_vod(self, it):
        try:
            vid = str(it.get('id') or '')
            name = it.get('bookTitle') or ''
            if not vid or not name:
                return None
            pic = it.get('bookImage') or ''
            desc = it.get('bookDesc') or ''
            actor = it.get('bookAnchor') or ''
            remarks = ''
            cnt = it.get('count')
            if cnt:
                remarks = str(cnt) + '集'
            return {'vod_id': vid, 'vod_name': name, 'vod_pic': pic, 'vod_remarks': remarks,
                    'vod_actor': actor, 'vod_content': desc, 'vod_tag': ''}
        except Exception:
            return None

    def _search_match(self, kw, it):
        try:
            name = str(it.get('bookTitle') or '')
            actor = str(it.get('bookAnchor') or '')
            if kw in name or kw in actor:
                return True
        except Exception:
            pass
        return False

    def searchContent(self, key, quick=False, pg=1):
        try:
            data = self._get('appSearch', {'client': 'babala-android', 'search': key,
                                           'app_token': self.SEARCH_TOKEN})
            info = (data or {}).get('data') or {}
            lst = info.get('bookData') or []
            vods = []
            for it in lst:
                if not self._search_match(key, it):
                    continue
                v = self._extract_vod(it)
                if v:
                    vods.append(v)
            return json.dumps({'page': 1, 'pagecount': 1, 'limit': 20, 'total': len(vods), 'list': vods},
                              ensure_ascii=False)
        except Exception:
            return json.dumps({'page': 1, 'pagecount': 1, 'limit': 20, 'total': 0, 'list': []}, ensure_ascii=False)

    def detailContent(self, ids):
        try:
            vid = str(ids[0])
            book_data = {}
            try:
                data = self._get('book', {'bookId': vid})
                d = (data or {}).get('data') or {}
                book_data = d.get('bookData') or {}
                if isinstance(book_data, list) and book_data:
                    book_data = book_data[0]
            except Exception:
                pass
            name = book_data.get('bookTitle') or ''
            pic = book_data.get('bookImage') or ''
            desc = book_data.get('bookDesc') or ''
            actor = book_data.get('bookAnchor') or ''
            try:
                data = self._get('chapter', {'bookId': vid, 'sort': 'asc', 'page': '1', 'size': '9999'})
                d = (data or {}).get('data') or {}
                chapters = d.get('list') or []
            except Exception:
                chapters = []
            eps = []
            for ch in chapters:
                try:
                    title = str(ch.get('title') or '')
                    cid = str(ch.get('chapterId') or '')
                    if title and cid:
                        eps.append(title + '$' + vid + '@' + cid)
                except Exception:
                    pass
            vod = {'vod_id': vid, 'vod_name': name, 'vod_pic': pic, 'vod_content': desc, 'vod_actor': actor,
                   'vod_play_from': '免费分享', 'vod_play_url': '#'.join(eps)}
            return json.dumps({'list': [vod]}, ensure_ascii=False)
        except Exception:
            return json.dumps({'list': []}, ensure_ascii=False)

    def playerContent(self, ids, flags=None):
        try:
            book_id = str(ids[0])
            parts = ids[1].split('@')
            chapter_id = parts[-1] if parts else ''
            ts = str(int(time.time() * 1000))
            s1 = hashlib.md5((ts + KEY).encode('utf-8')).hexdigest()
            parapet = hashlib.md5((s1 + KEY).encode('utf-8')).hexdigest()
            data = self._get('AppGetChapterUrl2023',
                             {'bookId': book_id, 'chapterId': chapter_id, 'timeStamp': ts,
                              'addItParapet': parapet, 'uid': '0'})
            src = (data or {}).get('src') or ''
            if not src:
                return json.dumps({}, ensure_ascii=False)
            return json.dumps({'parse': 0, 'url': src,
                               'header': {'User-Agent': 'listen/1.9.2 (Linux;Android 13) ExoPlayerLib/2.8.4'}},
                              ensure_ascii=False)
        except Exception:
            return json.dumps({}, ensure_ascii=False)
