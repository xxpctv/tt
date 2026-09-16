# -*- coding: utf-8 -*-
"""
豆瓣推荐 Douban 独立版
协议：frodo.douban.com 移动接口（GET + apikey，无签名）
兼容：OK影视 / 影视仓（TVBox Python 引擎）
说明：frodo 对非 Android 客户端栈（python urllib / curl）风控 invalid_request_997；
      本版网络层优先走 Chaquopy Java HttpURLConnection（Android TLS 栈），
      与 jar 版 OkHttp 同栈可过风控；本机（无 Chaquopy）自动回退 urllib 便于调试。
"""
import json
import urllib.parse

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider:
        pass

BASE = 'https://frodo.douban.com/api/v2'
KEY = '0ac44ae016490db2204ce0a042db2916'
# 原版 jar 日志实锤：Edge 浏览器 UA + api.douban.com Referer（图片防盗链 @ 拼接同源）
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0'
REF = 'https://api.douban.com/'
IMG_HEAD = '@Referer=' + REF + '@User-Agent=' + UA

# 首页分类 -> (type_id, 名称, 路径)  —— type_id 直接用路径（原版 tid=hot_gaia）
CLASSES = [
    ('hot_gaia', '热门电影', '/movie/hot_gaia'),
    ('tv_hot', '热播剧集', '/tv/hot_gaia'),
    ('show_hot', '热播综艺', '/tv/show_hot'),
    ('rank_list_movie', '电影榜单', '/rank_list_movie'),
    ('rank_list_tv', '电视剧榜单', '/rank_list_tv'),
]


def _http_java(url, timeout=15):
    """Chaquopy Java HttpURLConnection（Android TLS 栈，可过 frodo 997）"""
    from java.net import URL, HttpURLConnection
    from java.io import ByteArrayOutputStream
    conn = URL(url).openConnection()
    conn.setRequestMethod('GET')
    conn.setRequestProperty('User-Agent', UA)
    conn.setRequestProperty('Referer', REF)
    conn.setRequestProperty('Connection', 'Keep-Alive')
    conn.setConnectTimeout(timeout * 1000)
    conn.setReadTimeout(timeout * 1000)
    code = conn.getResponseCode()
    if code != 200:
        raise IOError('HTTP %d' % code)
    ins = conn.getInputStream()
    bos = ByteArrayOutputStream()
    buf = bytearray(8192)
    while True:
        n = ins.read(buf, 0, len(buf))
        if n < 0:
            break
        bos.write(buf, 0, n)
    ins.close()
    conn.disconnect()
    return bos.toString('UTF-8')


def _http_urllib(url, timeout=15):
    import urllib.request
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Referer': REF,
        'Connection': 'Keep-Alive',
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='replace')


_HTTP = _http_java  # 默认 Java 栈；无 Chaquopy 环境由调用方回退


def _get(path, extra=None):
    url = BASE + path + '?apikey=' + KEY
    if extra:
        url += '&' + urllib.parse.urlencode(extra)
    errs = []
    for fn in (_HTTP, _http_urllib):
        try:
            return json.loads(fn(url))
        except Exception as e:
            errs.append('%s: %s' % (getattr(fn, '__name__', fn), e))
    print('Douban _get 失败:', '; '.join(errs))
    return {}


class Spider(_BaseSpider):
    name = '豆瓣推荐'

    def init(self, extend=''):
        return ''

    def homeContent(self, filter):
        cls = [{'type_id': cid, 'type_name': name} for cid, name, _p in CLASSES]
        return {'class': cls}

    def categoryContent(self, tid, pg, filter, extend):
        path = None
        for cid, _n, p in CLASSES:
            if cid == tid:
                path = p
                break
        if not path:
            return {'list': []}
        o = _get(path, {'start': str((int(pg) - 1) * 20), 'count': '20'})
        return {'list': _parse_items(o)}

    def detailContent(self, ids):
        sid = str(ids[0]) if ids else ''
        if not sid:
            return {'list': []}
        if sid.startswith('msearch:'):
            sid = sid.split(':', 1)[1]
        o = _get('/subject/' + sid)
        title = o.get('title') or sid
        pic = ''
        pic_objs = (o.get('pic') or {}).get('normal') or (o.get('pic') or {}).get('large') or ''
        if isinstance(pic_objs, str):
            pic = pic_objs
        elif isinstance(pic_objs, dict):
            pic = pic_objs.get('url') or ''
        if pic:
            pic += IMG_HEAD
        rating = ''
        rv = (o.get('rating') or {}).get('value')
        if rv:
            rating = '评分：%s' % rv
        vod = {
            'vod_id': 'msearch:' + sid,
            'vod_name': title,
            'vod_pic': pic,
            'type_name': o.get('genres') and ','.join(o.get('genres')[:3]) or '',
            'vod_year': str(o.get('year') or ''),
            'vod_actor': o.get('actors') and ','.join(
                [a.get('name', '') for a in (o.get('actors') or [])][:6]) or '',
            'vod_director': o.get('directors') and ','.join(
                [a.get('name', '') for a in (o.get('directors') or [])][:3]) or '',
            'vod_content': (o.get('intro') or '') + ('\n' + rating if rating else ''),
            'vod_play_from': '豆瓣',
            'vod_play_url': '',
        }
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        return {'parse': 0, 'playUrl': ''}

    def searchContent(self, key, quick, pg=1):
        o = _get('/search', {'q': key, 'start': str((int(pg) - 1) * 20), 'count': '20'})
        subs = o.get('subjects') or []
        return {'list': _parse_subjects(subs)}


def _parse_items(o):
    out = []
    items = None
    for k in ('subject_collection_items', 'items', 'subjects', 'data', 'list'):
        if isinstance(o.get(k), list):
            items = o[k]
            break
    if items is None and isinstance(o, list):
        items = o
    for it in (items or []):
        sid = str(it.get('id') or '')
        if not sid:
            continue
        pic = ''
        p = it.get('pic') or {}
        if isinstance(p, dict):
            pic = p.get('normal') or p.get('large') or p.get('url') or ''
            if isinstance(pic, dict):
                pic = pic.get('url') or ''
        elif isinstance(p, str):
            pic = p
        if pic:
            pic += IMG_HEAD
        rating = ''
        rv = (it.get('rating') or {}).get('value')
        if rv:
            rating = '评分：%s' % rv
        out.append({
            'vod_id': 'msearch:' + sid,
            'vod_name': it.get('title') or '',
            'vod_pic': pic,
            'vod_remarks': rating,
        })
    return out


def _parse_subjects(subs):
    out = []
    for it in (subs or []):
        sid = str(it.get('id') or '')
        if not sid:
            continue
        pic = ''
        p = it.get('pic') or {}
        if isinstance(p, dict):
            pic = p.get('normal') or p.get('large') or ''
            if isinstance(pic, dict):
                pic = pic.get('url') or ''
        if pic:
            pic += IMG_HEAD
        out.append({
            'vod_id': 'msearch:' + sid,
            'vod_name': it.get('title') or '',
            'vod_pic': pic,
            'vod_remarks': '评分：%s' % ((it.get('rating') or {}).get('value') or ''),
        })
    return out


def main():
    s = Spider()
    print(json.dumps(s.homeContent(False), ensure_ascii=False)[:300])


if __name__ == '__main__':
    main()
