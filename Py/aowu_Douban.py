# -*- coding: utf-8 -*-
"""
豆瓣推荐 Douban 独立版（从 aowu.jar 逆向还原，不依赖原 jar / 作者服务器）
协议：frodo.douban.com 移动接口（GET + apikey，无签名）
兼容：OK影视 / 影视仓（TVBox Python 引擎）
注意：frodo 公开 apikey 受豆瓣风控（invalid_request_997），能否用取决于网络出口；
      若 997 说明该出口被风控，需换网络或用原版抓包对齐参数。
"""
import json
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider:
        pass

BASE = 'https://frodo.douban.com/api/v2'
KEY = '0ac44ae016490db2204ce0a042db2916'
UA = 'api-client/1 com.douban.frodo/7.19.0 (Android/10; GDPR; NO)'
REF = 'https://servicewechat.com/wx2f9b06c1de1ccfca/84/page-frame.html'

# 首页分类 -> (路径, 说明)
CLASSES = [
    ('movie_hot', '热门电影', '/movie/hot_gaia'),
    ('tv_hot', '热播剧集', '/tv/hot_gaia'),
    ('tv_show_hot', '热播综艺', '/tv/show_hot'),
    ('movie_rank', '电影榜单', '/rank_list_movie'),
    ('tv_rank', '电视剧榜单', '/rank_list_tv'),
]


def _http(url, timeout=15):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Referer': REF,
        'Connection': 'Keep-Alive',
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='replace')


def _get(path, extra=None):
    url = BASE + path + '?apikey=' + KEY
    if extra:
        url += '&' + urllib.parse.urlencode(extra)
    try:
        return json.loads(_http(url))
    except Exception:
        return {}


class Spider(_BaseSpider):
    name = '豆瓣推荐'

    def init(self, extend=''):
        return ''

    def homeContent(self, filter):
        cls = [{'type_id': cid, 'type_name': name} for cid, name, _p in CLASSES]
        return json.dumps({'class': cls}, ensure_ascii=False)

    def categoryContent(self, tid, pg, filter, extend):
        path = None
        for cid, _n, p in CLASSES:
            if cid == tid:
                path = p
                break
        if not path:
            return json.dumps({'list': []}, ensure_ascii=False)
        o = _get(path, {'start': str((int(pg) - 1) * 20), 'count': '20'})
        return json.dumps({'list': _parse_items(o)}, ensure_ascii=False)

    def detailContent(self, ids):
        sid = str(ids[0]) if ids else ''
        if not sid:
            return json.dumps({'list': []}, ensure_ascii=False)
        o = _get('/subject/' + sid)
        title = o.get('title') or sid
        pic = ''
        pic_objs = (o.get('pic') or {}).get('normal') or (o.get('pic') or {}).get('large') or ''
        if isinstance(pic_objs, str):
            pic = pic_objs
        elif isinstance(pic_objs, dict):
            pic = pic_objs.get('url') or ''
        rating = ''
        rv = (o.get('rating') or {}).get('value')
        if rv:
            rating = '评分：%s' % rv
        vod = {
            'vod_id': sid,
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
        return json.dumps({'list': [vod]}, ensure_ascii=False)

    def playerContent(self, flag, id, vipFlags):
        return json.dumps({'parse': 0, 'playUrl': ''}, ensure_ascii=False)

    def searchContent(self, key, quick, pg=1):
        o = _get('/search', {'q': key, 'start': str((int(pg) - 1) * 20), 'count': '20'})
        subs = o.get('subjects') or []
        return json.dumps({'list': _parse_subjects(subs)}, ensure_ascii=False)


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
        rating = ''
        rv = (it.get('rating') or {}).get('value')
        if rv:
            rating = '评分：%s' % rv
        out.append({
            'vod_id': sid,
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
        out.append({
            'vod_id': sid,
            'vod_name': it.get('title') or '',
            'vod_pic': pic,
            'vod_remarks': '评分：%s' % ((it.get('rating') or {}).get('value') or ''),
        })
    return out


def main():
    s = Spider()
    print(s.homeContent(False)[:200])


if __name__ == '__main__':
    main()
