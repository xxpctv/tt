# -*- coding: utf-8 -*-
"""
豪堪短剧 
协议：百度好看短剧（sv.baidu.com）四接口全链路实测 200
  - 首页/分类/搜索: POST /haokan/ui-feed/playletShelfFeed (osbranch=a0 [+tag_id/+search_word])
  - 详情:          POST /haokan/ui-video/playlet/rec/detail (playlet_id=vid=剧集id)
  - 播放:          POST /appui/api?osbranch=a0 body=video/relate=<urlencoded form> -> cur_video.video_src 直链
兼容：OK影视 / 影视仓（TVBox Python 引擎）
"""
import json
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider:
        pass

_UA = ('Mozilla/5.0 (Linux; Android 11; M2012K10C Build/RP1A.200720.011) '
       'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/107.0.0.0 Safari/537.36')

_FEED = 'https://sv.baidu.com/haokan/ui-feed/playletShelfFeed'
_DETAIL = 'https://sv.baidu.com/haokan/ui-video/playlet/rec/detail'
_RELATE = 'https://sv.baidu.com/appui/api'

_PLAY_FORM = ('method=post&vid=%s&immersive_mode=v4_5&tplname=feed_small_video'
              '&tag=playlet_talos&tab=detail&external_from=&is_dp_video=0'
              '&immersive_square_type=3&video_set_id=%s&play_screen_type=1')


def _post(url, params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, headers={
        'User-Agent': _UA, 'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode('utf-8', 'replace')
    except Exception:
        return ''


def _post_body(url, body):
    req = urllib.request.Request(url, data=body.encode(), headers={
        'User-Agent': _UA, 'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode('utf-8', 'replace')
    except Exception:
        return ''


def _feed_list(obj):
    """data.playlet_feed_tags.list -> OK影视 列表项"""
    out = []
    try:
        tags = obj['data']['playlet_feed_tags']['list']
    except Exception:
        return out
    for it in tags or []:
        out.append({
            'vod_id': str(it.get('playlet_id', '')),
            'vod_name': it.get('playlet_title', ''),
            'vod_pic': it.get('playlet_poster', ''),
            'vod_remarks': it.get('episodes_num_text', ''),
            'vod_content': it.get('description', ''),
        })
    return out


class Spider(_BaseSpider):
    name = '豪堪短剧'
    siteKey = 'HHkk'

    def init(self, extend=''):
        return ''

    # ================= 首页 =================
    def homeContent(self, filter):
        body = _post(_FEED, {'osbranch': 'a0'})
        try:
            obj = json.loads(body)
        except Exception:
            return {'class': [], 'list': []}
        classes = []
        try:
            for t in obj['data'].get('playlet_tags') or []:
                classes.append({'type_id': str(t.get('tag_id')), 'type_name': t.get('name', '')})
        except Exception:
            pass
        return {'class': classes, 'list': _feed_list(obj)}

    # ================= 分类 =================
    def categoryContent(self, tid, pg, filter, extend):
        body = _post(_FEED, {'osbranch': 'a0', 'tag_id': str(tid)})
        try:
            obj = json.loads(body)
        except Exception:
            obj = {}
        return {'page': int(pg or 1), 'pagecount': 9999, 'limit': 90, 'total': 9999, 'list': _feed_list(obj)}

    # ================= 详情 =================
    def detailContent(self, ids):
        vid = str(ids[0])
        body = _post(_DETAIL, {'playlet_id': vid, 'vid': vid})
        try:
            d = json.loads(body).get('data', {})
        except Exception:
            d = {}
        vid_list = d.get('vid_list') or []
        vids = [str(v) for v in vid_list if v]
        eps = []
        for i, v in enumerate(vids, 1):
            eps.append('第%s集$%s|%s' % (i, v, vid))
        vod = {
            'vod_id': vid,
            'vod_name': d.get('playlet_title') or vid,
            'vod_pic': d.get('playlet_poster') or '',
            'type_name': d.get('tag_text') or '',
            'vod_remarks': ('%s集' % d.get('episodes_num')) if d.get('episodes_num') else '',
            'vod_content': d.get('description') or '',
            'vod_play_from': '百度短剧',
            'vod_play_url': '#'.join(eps),
        }
        return {'list': [vod]}

    # ================= 搜索 =================
    def searchContent(self, key, quick=True, pg=1):
        # OK影视 5.1.6 传 3 参(key, quick, page)；2 参会被 TypeError 静默跳过
        body = _post(_FEED, {'osbranch': 'a0', 'search_word': key})
        try:
            obj = json.loads(body)
        except Exception:
            obj = {}
        # 标题过滤：服务端为 标题+简介+标签 模糊搜索，只保留标题含关键词
        return {'list': [v for v in _feed_list(obj)
                         if not key or (key in (v.get('vod_name') or ''))]}

    # 兼容别名：OK影视 快搜入口
    def quickSearch(self, key, quick=True, pg=1):
        return self.searchContent(key, True, pg)

    # ================= 播放（id=vid|playlet_id） =================
    def playerContent(self, flag, id, vipFlags):
        parts = str(id).split('|')
        v = parts[0]
        sid = parts[1] if len(parts) > 1 else v
        body = _post_body(_RELATE + '?osbranch=a0',
                          'video/relate=' + urllib.parse.quote_plus(_PLAY_FORM % (v, sid)))
        url = ''
        try:
            rel = json.loads(body).get('video/relate') or {}
            url = ((rel.get('data') or {}).get('cur_video') or {}).get('video_src', '')
        except Exception:
            pass
        if not url:
            url = id
        return {'parse': 0, 'playUrl': url, 'header': {'User-Agent': _UA}}


class HHkkAmns(Spider):
    """OK影视 api=csp_HHkkAmns 别名类"""
    pass


def main():
    s = Spider()
    h = s.homeContent(False)
    print('首页分类:', [c['type_name'] for c in h['class']][:5])
    print('首页列表条数:', len(h['list']), '首项:', h['list'][0]['vod_name'] if h['list'] else '-')
    if h['class']:
        c = s.categoryContent(h['class'][0]['type_id'], 1, None, None)
        print('分类[%s]条数:' % h['class'][0]['type_name'], len(c['list']))
    d = s.detailContent([h['list'][0]['vod_id']]) if h['list'] else {'list': []}
    if d['list']:
        vod = d['list'][0]
        print('详情:', vod['vod_name'], vod['vod_remarks'], '集数:', len(vod['vod_play_url'].split('#')))
        ep0 = vod['vod_play_url'].split('#')[0]
        eid = ep0.split('$')[1]
        p = s.playerContent('', eid, [])
        print('播放:', p['playUrl'][:100])


if __name__ == '__main__':
    main()
