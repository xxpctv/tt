# -*- coding: utf-8 -*-
"""
西饭短剧
请求链（host: https://xifan-api-cn.youlishipin.com）：
  - 列表:  GET /xifan/drama/portalPage?reqType=aggregationPage&offset=(pg-1)*30&categoryId&categoryNames&version=2001001&androidVersionCode=28&requestId={ts}aa498144140ef297&appId=drama&teenMode=false&userBaseMode=false&{session}
           -> result.elements[].contents[].duanjuVo{duanjuId,source,title,coverImageUrl,total,desc}
  - 详情:  GET /xifan/drama/getDuanjuInfo?duanjuId&source -> result{title,coverImageUrl,desc,updateStatus,total,episodeList[]{index,playUrl}}
  - 搜索:  GET /xifan/search/getSearchList?keyword&pageIndex&version=2001001&androidVersionCode=28&requestId={ts}ea3a14bc0317d76f&appId=drama&teenMode=false&userBaseMode=false&{session}
           -> result.elements[].contents[].duanjuVo
签名：无算法签名；session/feedssession 为固定预置参数（聚合短剧.js L394 原样）
兼容：OK影视 / 影视仓（TVBox Python 引擎）
"""
import json
import time
import urllib.parse
import urllib.request
import re

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider:
        pass

_HOST = 'https://xifan-api-cn.youlishipin.com'
_LIST = '/xifan/drama/portalPage'
_DETAIL = '/xifan/drama/getDuanjuInfo'
_SEARCH = '/xifan/search/getSearchList'

_HEADERS = {
    'User-Agent': 'okhttp/4.10.0',
    'Content-Type': 'application/x-www-form-urlencoded',
}

# 聚合短剧.js L394 原样（session 参数，勿改动）
_XIFAN_SESSION = ('session=eyJpbmZvIjp7InVpZCI6IiIsInJ0IjoiMTc0MDY2ODk4NiIsInVuIjoiT1BHX2U5ODQ4NTgzZmM4ZjQzZTJhZjc5ZTcxNjRmZTE5Y2JjIiwiZnQiOiIxNzQwNjY4OTg2In19'
                  '&feedssession=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1dHlwIjowLCJidWlkIjoxNjM0MDU3ODE4OTgxNDk5OTA0LCJhdWQiOiJkcmFtYSIsInZlciI6MiwicmF0IjoxNzQwNjY4OTg2LCJ1bm0iOiJPUEdfZTk4NDg1ODNmYzhmNDNlMmFmNzllNzE2NGZlMTljYmMiLCJpZCI6ImVhZGE1NmEyZWEzYTE0YmMwMzE3ZDc2ZmVjODJjNzc3IiwiZXhwIjoxNzQxMjczNzg2LCJkYyI6ImJqaHQifQ.IwuI0gK077RF4G10JRxgxx4GCG502vR8Z0W9EV4kd-c')

_CLASSES = [
    ('68', '都市'), ('68', '青春'), ('81', '现代言情'), ('81', '豪门'),
    ('80', '大女主'), ('79', '逆袭'), ('79', '打脸虐渣'), ('81', '穿越'),
]
# 聚合 js 原始定义：68@都市、68@青春、81@现代言情、81@豪门、80@大女主、79@逆袭、79@打脸虐渣、81@穿越
_CLASS_RAW = [
    ('68@都市', '都市'), ('68@青春', '青春'), ('81@现代言情', '现代言情'), ('81@豪门', '豪门'),
    ('80@大女主', '大女主'), ('79@逆袭', '逆袭'), ('79@打脸虐渣', '打脸虐渣'), ('81@穿越', '穿越'),
]


def _get(url):
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
        return json.loads(raw.decode('utf-8', 'replace'))
    except Exception:
        return {}


def _actor_of(it):
    """从搜索/列表项提取演员字符串（响应无演员字段时返回空）"""
    for k in ('actor', 'actors', 'star', 'stars', 'starring', 'performer', 'protagonist', 'actorList'):
        v = it.get(k)
        if v:
            if isinstance(v, list):
                return ' '.join(str(x) for x in v)
            return str(v)
    return ''


class Spider(_BaseSpider):
    name = '西饭短剧'
    siteKey = 'Xifan'

    def init(self, extend=''):
        return ''

    def homeContent(self, filter):
        return {'class': [{'type_id': i, 'type_name': n} for i, n in _CLASS_RAW]}

    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid or '68@都市')
        if '@' in tid:
            cat_id, cat_name = tid.split('@', 1)
        else:
            cat_id, cat_name = tid, ''
        ts = str(int(time.time()))
        offset = (int(pg or 1) - 1) * 30
        url = ('%s%s?reqType=aggregationPage&offset=%s&categoryId=%s&categoryNames=%s'
               '&version=2001001&androidVersionCode=28&requestId=%saa498144140ef297'
               '&appId=drama&teenMode=false&userBaseMode=false&%s'
               ) % (_HOST, _LIST, offset, urllib.parse.quote(cat_id), urllib.parse.quote(cat_name),
                    ts, _XIFAN_SESSION)
        j = _get(url)
        items = []
        for soup in (j.get('result') or {}).get('elements') or []:
            for vod in soup.get('contents') or []:
                dj = vod.get('duanjuVo') or {}
                items.append(dj)
        lst = []
        for dj in items:
            lst.append({
                'vod_id': '%s#%s' % (dj.get('duanjuId') or '', dj.get('source') or ''),
                'vod_name': dj.get('title') or '',
                'vod_pic': dj.get('coverImageUrl') or '',
                'vod_remarks': '西饭短剧 | %s集' % (dj.get('total') or ''),
                'vod_content': dj.get('desc') or '',
            })
        return {'list': lst, 'page': pg, 'pagecount': int(pg or 1) + 1}

    def detailContent(self, ids):
        did = str(ids[0] if isinstance(ids, list) else ids)
        if '#' in did:
            duanju_id, source = did.split('#', 1)
        else:
            duanju_id, source = did, ''
        url = '%s%s?duanjuId=%s&source=%s' % (_HOST, _DETAIL, urllib.parse.quote(duanju_id), urllib.parse.quote(source))
        j = _get(url)
        d = j.get('result') or {}
        eps = []
        for ep in d.get('episodeList') or []:
            u = ep.get('playUrl')
            if u:  # 缺失集（missEpisode）无 playUrl，跳过
                eps.append('%s$%s' % (ep.get('index'), u))
        vod = {
            'vod_id': did,
            'vod_name': d.get('title') or '',
            'vod_pic': d.get('coverImageUrl') or '',
            'vod_content': d.get('desc') or '',
            'vod_remarks': '%s集 %s' % (d.get('total') or 0, '已完结' if d.get('updateStatus') == 'over' else '连载中'),
            'vod_play_from': '西饭短剧',
            'vod_play_url': '#'.join(eps) or '暂无播放地址$0',
        }
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        return {'parse': 0, 'url': id}

    def searchContent(self, key, quick=True, pg=1):
        k = str(key or '').strip()
        ts = str(int(time.time()))
        url = ('%s%s?keyword=%s&pageIndex=%s&version=2001001&androidVersionCode=28'
               '&requestId=%sea3a14bc0317d76f&appId=drama&teenMode=false&userBaseMode=false&%s'
               ) % (_HOST, _SEARCH, urllib.parse.quote(k), pg, ts, _XIFAN_SESSION)
        j = _get(url)
        items = []
        for soup in (j.get('result') or {}).get('elements') or []:
            for vod in soup.get('contents') or []:
                items.append(vod.get('duanjuVo') or {})
        lst = []
        for dj in items:
            title = re.sub(r'<[^>]+>', '', str(dj.get('title') or '')).strip()
            # 搜索范围：标题 或 演员 包含关键词（不匹配简介/详情）
            actor = _actor_of(dj)
            if k and k not in title and k not in actor:
                continue
            lst.append({
                'vod_id': '%s#%s' % (dj.get('duanjuId') or '', dj.get('source') or ''),
                'vod_name': title,
                'vod_pic': dj.get('coverImageUrl') or '',
                'vod_remarks': '西饭短剧 | %s集' % (dj.get('total') or ''),
                'vod_content': '',
            })
        return {'list': lst}

    # 兼容别名
    def quickSearch(self, key):
        return self.searchContent(key, True)

    def search(self, key):
        return self.searchContent(key, True)
