# -*- coding: utf-8 -*-
# ============ 71us 模板 v7.5 / tingyou.fm (听友听书 有声小说) ============
# 站点: https://tingyou.fm  (SPA Nuxt, H5 未加密 API)
# API 基址: https://appp.fdhtbz.cn/api/h5/listening/
#   分类列表 GET  /category?sort={popular|updated|newest}&page=N[&cat=有声小说|评书][&status=0|1]
#   专辑详情 GET  /album/{id}
#   章节列表 GET  /chapters/{id}   (一次返回全部章节)
#   播放地址 POST /play  body={"album_id":"..","chapter_idx":N}  -> {"play_url":"https://...mp4"}
#   搜索     POST /search body={"keyword":"..","page":N}
# 代理回退: https://tingyou.fm/listening-api/{path}
# 定版: 71us模板v7.5 | 2026-10-09
# ★版本兼容铁律: 全文件禁3.9+API; 分隔符 $=名称/地址 | #=选集 | $$$=线路
import sys, re, json, time
from urllib.parse import quote, urlencode
import requests

sys.path.append('..')
try:
    from base.spider import Spider
except ImportError:
    class Spider:
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = requests.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r

# ============ ★ CONFIG ============
TEMPLATE_MODE = 'normal'
HOSTS = ['https://tingyou.fm']
API_HOSTS = [
    'https://tingyou.fm/listening-api',          # 边缘代理: 章节接口实测 0.7s, 直连 20~35s
    'https://appp.fdhtbz.cn/api/h5/listening',
]
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
# 一级分类: type_id 用 cat 参数; 空=全部
CATEGORIES = {
    '': '全部',
    '有声小说': '有声小说',
    '评书': '评书',
}
# 筛选: 排序 + 状态
FILTERS_RAW = {
    '': [
        {'key': 'sort', 'name': '排序', 'value': [
            {'n': '播放最多', 'v': 'popular'},
            {'n': '最近更新', 'v': 'updated'},
            {'n': '最新发布', 'v': 'newest'},
        ]},
        {'key': 'status', 'name': '状态', 'value': [
            {'n': '全部状态', 'v': ''},
            {'n': '连载中', 'v': '1'},
            {'n': '已完结', 'v': '0'},
        ]},
    ],
}
FILTER_YEARS = []
PK = ''
REFERER = 'https://tingyou.fm/'
PIC_REFERER = ''
IMG_PROXY = ''
IMG_HOST = ''
FD_ZONE = 0
PROBE = 0
PAGE_MINLEN = 100
SITE_KEY = 'tingyou'
VIDEO_EXTS = 'm3u8|mp4|flv|mkv|avi|ts|m4a|mp3|aac'
PLAY_TTL = 240        # 播放直链缓存 (实测 45s 后仍可复用, 取保守值)
CHAP_TTL = 600        # 章节表缓存 (单本 667KB, 反复进详情不再重下)
BAD_HOST_TTL = 60     # 失败主机短期黑名单, 避免每条请求都等超时
CACHE_MAX = 6         # 章节缓存最多保留的专辑数


def LOG(msg):
    try:
        print('[听友听书]', msg)
    except Exception:
        pass

# 脱敏
BLOCK_KW = [
    '幼女', '幼齿', '萝莉', '未成年', '小学生', '中学生', '儿童色情',
    '强奸', '轮奸', '迷奸', '兽交', '人兽',
]
BLOCK_VAR = []
BLOCK_CIDS = set()


def _blocked(text):
    if not text:
        return False
    t = str(text).lower()
    for k in BLOCK_KW:
        if k in t:
            return True
    return False


class Spider(Spider):
    def init(self, extend=''):
        self.base = HOSTS[0].rstrip('/')
        self.api_hosts = list(API_HOSTS)
        self.ua = UA
        self.pk = PK
        self.ref = REFERER or self.base
        self.types = dict(CATEGORIES)
        self.filters = {}
        self._pcm = {}
        self._session = None
        self._chap_cache = {}      # album_id -> (章节列表, 时间)
        self._play_cache = {}      # "album_idx" -> (直链, 时间)
        self._bad_host = {}        # 主机 -> 解禁时间戳
        self._build_filters()

    def _sess(self):
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                'User-Agent': self.ua,
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept': 'application/json, text/plain, */*',
                'Origin': self.base,
                'Referer': self.ref,
            })
        return self._session

    def _build_filters(self):
        # 每个一级分类共用同一套筛选
        for tid in self.types:
            self.filters[tid] = list(FILTERS_RAW.get('', []))

    def getName(self):
        return '听友听书'

    def isVideoFormat(self, url):
        if not url:
            return False
        return bool(re.search(r'\.(' + VIDEO_EXTS + r')(\?|$)', url, re.I))

    def manualVideoCheck(self):
        return False

    def homeContent(self, filter=True):
        classes = [{'type_id': k, 'type_name': v} for k, v in self.types.items()]
        result = {'class': classes}
        if filter and self.filters:
            result['filters'] = self.filters
        return result

    def homeVideoContent(self):
        # 首页推荐: 播放最多
        return self._list_page(cat='', sort='popular', page=1)

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if pg else 1
        sort = (extend or {}).get('sort') or 'popular'
        status = (extend or {}).get('status') or ''
        cat = tid if tid else ''
        return self._list_page(cat=cat, sort=sort, page=pg, status=status)

    def _list_page(self, cat='', sort='popular', page=1, status=''):
        params = {'sort': sort or 'popular', 'page': str(page)}
        if cat:
            params['cat'] = cat
        if status != '' and status is not None:
            params['status'] = str(status)
        qs = urlencode(params)
        data = self._api_get('category?' + qs)
        items = []
        pagecount = 1
        if isinstance(data, dict):
            pagecount = int(data.get('pages') or 1) or 1
            for it in (data.get('data') or []):
                if not isinstance(it, dict):
                    continue
                name = str(it.get('title') or '').strip()
                if not name or _blocked(name):
                    continue
                vid = str(it.get('id') or '')
                if not vid:
                    continue
                pic = str(it.get('cover_url') or '')
                st = it.get('status')
                cnt = it.get('count') or 0
                remarks = ''
                if st == 1:
                    remarks = '连载中'
                elif st == 0:
                    remarks = '已完结'
                if cnt:
                    remarks = (remarks + ' · ' if remarks else '') + '%s集' % cnt
                items.append({
                    'vod_id': vid,
                    'vod_name': name[:80],
                    'vod_pic': self._pic(pic),
                    'vod_remarks': remarks[:40],
                })
        return {
            'list': items,
            'page': page,
            'pagecount': max(pagecount, 1),
            'limit': 20,
            'total': pagecount * 20,
        }

    def detailContent(self, ids):
        vid = str(ids[0]) if ids else ''
        if not vid:
            return {'list': []}
        album = self._api_get('album/' + vid)
        if not isinstance(album, dict) or not album.get('id'):
            # 代理回退
            album = self._api_get('album/' + vid, prefer_proxy=True)
        if not isinstance(album, dict) or not album.get('id'):
            return {'list': []}

        title = str(album.get('title') or '').strip()
        if _blocked(title):
            return {'list': []}
        author = str(album.get('author') or '').strip()
        teller = str(album.get('teller') or '').strip()
        pic = str(album.get('cover_url') or '')
        synopsis = str(album.get('synopsis') or '').strip()
        typ = str(album.get('type') or '')
        cat = str(album.get('cat') or '')
        cnt = album.get('count') or 0
        st = album.get('status')
        status_txt = '连载中' if st == 1 else ('已完结' if st == 0 else '')
        type_name = '/'.join([x for x in [typ, cat] if x])

        # 章节
        chapters = self._fetch_chapters(vid)
        if chapters:      # 详情阶段预取首集直链, 点播放零请求
            try:
                self._playUrl(vid, int(chapters[0]['index']))
            except Exception as e:
                LOG('首集直链预取失败(忽略): %s' % e)
        play_from = '听友听书'
        play_urls = []
        for ch in chapters:
            idx = ch.get('index') or 0
            ctitle = str(ch.get('title') or ('第%s集' % idx)).strip()
            # vod_play_url: 名称$albumId_chapterIdx
            play_urls.append('%s$%s_%s' % (ctitle, vid, idx))
        play_url = '#'.join(play_urls) if play_urls else ''

        actor = teller
        if author and author != teller:
            actor = '%s / %s' % (author, teller) if teller else author
        # 清理污染
        for sep in ['_免费听书', '|免费', '免费收听']:
            if sep in actor:
                actor = actor.split(sep)[0].strip()

        vod = {
            'vod_id': vid,
            'vod_name': title[:100],
            'vod_pic': self._pic(pic),
            'type_name': type_name[:40],
            'vod_year': '',
            'vod_area': '',
            'vod_remarks': (status_txt + (' · %s集' % cnt if cnt else '')).strip(' ·'),
            'vod_actor': actor[:60],
            'vod_director': author[:40],
            'vod_content': synopsis[:500] if synopsis else '',
            'vod_play_from': play_from,
            'vod_play_url': play_url,
        }
        return {'list': [vod]}

    def _fetch_chapters(self, album_id):
        key = str(album_id)
        c = self._chap_cache.get(key)
        if c and time.time() - c[1] < CHAP_TTL:
            return c[0]
        data = self._api_get('chapters/' + key, timeout=15)
        if not isinstance(data, dict) or not data.get('chapters'):
            data = self._api_get('chapters/' + key, prefer_proxy=True, timeout=20)
        chs = []
        if isinstance(data, dict):
            for ch in (data.get('chapters') or []):
                if not isinstance(ch, dict):
                    continue
                idx = ch.get('index')
                if idx is None:
                    continue
                chs.append({
                    'id': ch.get('id'),
                    'index': int(idx),
                    'title': str(ch.get('title') or ('第%s集' % idx)),
                    'duration': ch.get('duration') or 0,
                })
        chs.sort(key=lambda x: x['index'])
        if chs:
            self._chap_cache[key] = (chs, time.time())
            while len(self._chap_cache) > CACHE_MAX:
                k = next(iter(self._chap_cache))
                if k == key:
                    break
                self._chap_cache.pop(k, None)
        return chs

    def _playUrl(self, album_id, idx):
        """播放直链: 命中缓存直接返回; 未命中才 POST 一次 /play (实测 0.2~0.9s)"""
        key = '%s_%s' % (album_id, idx)
        c = self._play_cache.get(key)
        if c and time.time() - c[1] < PLAY_TTL:
            return c[0]
        data = self._api_post('play', {'album_id': str(album_id), 'chapter_idx': int(idx)}, timeout=8)
        u = str((data or {}).get('play_url') or '').strip() if isinstance(data, dict) else ''
        if not u.startswith('http'):
            LOG('play 直链为空: %s' % key)
            return ''
        self._play_cache[key] = (u, time.time())
        if len(self._play_cache) > 64:
            self._play_cache.clear()
            self._play_cache[key] = (u, time.time())
        return u

    def searchContent(self, key, quick, pg='1'):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick, pg='1'):
        pg = int(pg) if pg else 1
        if not key or _blocked(key):
            return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 20, 'total': 0}
        body = {'keyword': key, 'page': pg}
        data = self._api_post('search', body)
        items = []
        has_more = False
        if isinstance(data, dict):
            has_more = bool(data.get('has_more'))
            for it in (data.get('results') or data.get('data') or []):
                if not isinstance(it, dict):
                    continue
                name = str(it.get('title') or '').strip()
                if not name or _blocked(name):
                    continue
                vid = str(it.get('id') or '')
                if not vid:
                    continue
                pic = str(it.get('cover_url') or '')
                st = it.get('status')
                cnt = it.get('count') or 0
                remarks = ''
                if st == 1:
                    remarks = '连载中'
                elif st == 0:
                    remarks = '已完结'
                if cnt:
                    remarks = (remarks + ' · ' if remarks else '') + '%s集' % cnt
                items.append({
                    'vod_id': vid,
                    'vod_name': name[:80],
                    'vod_pic': self._pic(pic),
                    'vod_remarks': remarks[:40],
                })
        pagecount = pg + 1 if has_more else pg
        return {
            'list': items,
            'page': pg,
            'pagecount': max(pagecount, 1),
            'limit': 20,
            'total': pagecount * 20,
        }

    def playerContent(self, flag, id, vipFlags):
        # id = albumId_chapterIdx; 直链由 /play 取得并缓存 (parse=0, 单条直链)
        url = ''
        try:
            parts = str(id).rsplit('_', 1)
            if len(parts) == 2 and parts[1].isdigit():
                album_id, chapter_idx = parts[0], int(parts[1])
            else:
                album_id, chapter_idx = str(id), 1
            url = self._playUrl(album_id, chapter_idx)
            if not url:
                LOG('playerContent 直链获取失败: %s' % id)
        except Exception as e:
            LOG('playerContent 异常 [%s]: %s' % (id, e))
        headers = {
            'User-Agent': self.ua,
            'Referer': self.ref,
            'Origin': self.base,
        }
        return {
            'parse': 0,
            'url': url,
            'header': headers,
        }

    # ========== HTTP ==========
    def _hosts(self, prefer_proxy=False):
        now = time.time()
        hosts = [h for h in self.api_hosts if self._bad_host.get(h, 0) < now]
        if not hosts:                       # 全部被拉黑时仍然全部重试, 避免永久不可用
            hosts = list(self.api_hosts)
        if prefer_proxy:
            hosts = hosts[::-1]
        return hosts

    def _mark_bad(self, host):
        self._bad_host[host] = time.time() + BAD_HOST_TTL

    def _api_get(self, path, prefer_proxy=False, timeout=10):
        for host in self._hosts(prefer_proxy):
            url = host.rstrip('/') + '/' + path.lstrip('/')
            try:
                r = self._sess().get(url, timeout=timeout)
            except Exception as e:
                self._mark_bad(host)
                LOG('GET 失败(拉黑%ds) %s: %s' % (BAD_HOST_TTL, host, str(e)[:60]))
                continue
            if r.status_code != 200:
                continue
            text = r.text.strip()
            if not text or text[0] not in '{[':
                continue
            try:
                return json.loads(text)
            except Exception:
                continue
        return {}

    def _api_post(self, path, body, timeout=10):
        for host in self._hosts():
            url = host.rstrip('/') + '/' + path.lstrip('/')
            try:
                r = self._sess().post(url, json=body, timeout=timeout, headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Origin': self.base,
                    'Referer': self.ref,
                })
            except Exception as e:
                self._mark_bad(host)
                LOG('POST 失败(拉黑%ds) %s: %s' % (BAD_HOST_TTL, host, str(e)[:60]))
                continue
            if r.status_code != 200:
                continue
            text = r.text.strip()
            if not text or text[0] not in '{[':
                continue
            try:
                return json.loads(text)
            except Exception:
                continue
        return {}

    def _pic(self, url):
        if not url:
            return ''
        if url.startswith('//'):
            url = 'https:' + url
        return url

    def localProxy(self, param):
        return ''

    def destroy(self):
        if self._session:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None
