# -*- coding: utf-8 -*-
"""
拜拜短剧 
协议：百度短剧（mbd.baidu.com / sv.baidu.com）全链路黑盒实测
  - 首页/分类: POST /feedapi/v1/videoserver/playlets/list  (query: service=bdbox)
    body: data={"data":{kind,names,flow_tabid,from,page,pd,channel_video_landing,
                        refreshIndex,cursor,theme,timestamp,version,themes}}
    version = md5(<毫秒时间戳> + "v2")  小写 hex   <-- 关键签名，缺失即 invalid version
    响应: data.items[] -> collId / title / img / updateStatus / themeTag / firstVideoId
  - 详情:     POST /haokan/ui-video/playlet/rec/detail
    data: {playlet_id: <collId>, vid: <collId>, is_collection: '1'}
    响应: data.playlet_title / playlet_poster / description / vid_list[] (全部集数 vid)
  - 播放:     POST /appui/api?osbranch=a0
    body: video/relate=<urlencoded form>
    form: method=post&vid=<集vid>&immersive_mode=v4_5&tplname=feed_small_video&tag=playlet_talos
          &tab=detail&external_from=&is_dp_video=0&immersive_square_type=3&video_set_id=<vid>&play_screen_type=1
    响应: json['video/relate']['data']['cur_video']['video_src'] 直链 MP4
兼容：OK影视 / 影视仓（TVBox Python 引擎）
"""
import json
import time
import hashlib
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider:
        pass

_UA = ('Dalvik/2.1.0 (Linux; U; Android 11; M2012K10C Build/RP1A.200720.011) '
       'Talos/1.8.13 SP-engine/3.47.0 bd_dvt/0 baiduboxapp/15.21.0.10 (Baidu; P1 11)')

_LIST = 'https://mbd.baidu.com/feedapi/v1/videoserver/playlets/list'
_SEARCH = 'https://mbd.baidu.com/feedapi/v1/videoserver/playlets/search'
_DETAIL = 'https://sv.baidu.com/haokan/ui-video/playlet/rec/detail'
_RELATE = 'https://sv.baidu.com/appui/api'


def _ts():
    return int(time.time() * 1000)


def _ver(ms):
    return hashlib.md5(('%dv2' % ms).encode()).hexdigest()


def _post(url, data, query='service=bdbox'):
    url = url + ('?' + query if query else '')
    payload = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=payload, headers={
        'User-Agent': _UA,
        'Accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode('utf-8', 'replace')
    except Exception:
        return ''


def _list_body(kind, page):
    ms = _ts()
    return {'data': json.dumps({'data': {
        'kind': kind, 'names': '1', 'flow_tabid': 13, 'from': 'feed', 'page': int(page or 1),
        'pd': 'feed', 'channel_video_landing': '', 'refreshIndex': 1, 'cursor': '',
        'theme': 'themes', 'timestamp': ms, 'version': _ver(ms)}}, ensure_ascii=False)}


def _items(obj):
    """data.items -> OK影视 列表项"""
    out = []
    try:
        items = obj['data']['items']
    except Exception:
        return out
    for it in items or []:
        out.append({
            'vod_id': str(it.get('collId', '')),
            'vod_name': it.get('title', ''),
            'vod_pic': it.get('img', ''),
            'vod_remarks': it.get('updateStatus', ''),
            'vod_content': it.get('themeTag', ''),
        })
    return out


class Spider(_BaseSpider):
    name = '拜拜短剧'

    def init(self, extend=''):
        return ''

    # ================= 首页 =================
    def homeContent(self, filter):
        body = _post(_LIST, _list_body('综合', 1))
        try:
            obj = json.loads(body)
        except Exception:
            return {'class': [], 'list': []}
        classes = []
        seen = set()
        try:
            for it in obj['data']['items']:
                tag = it.get('themeTag') or ''
                if tag and tag not in seen:
                    seen.add(tag)
                    classes.append({'type_id': tag, 'type_name': tag})
        except Exception:
            pass
        if not classes:
            classes = [{'type_id': '综合', 'type_name': '综合'}]
        return {'class': classes, 'list': _items(obj)}

    # ================= 分类 =================
    def categoryContent(self, tid, pg, filter, extend):
        body = _post(_LIST, _list_body(str(tid), pg))
        try:
            obj = json.loads(body)
        except Exception:
            obj = {}
        return {'page': int(pg or 1), 'pagecount': 9999, 'limit': 90,
                'total': 9999, 'list': _items(obj)}

    # ================= 详情 =================
    def detailContent(self, ids):
        coll = str(ids[0]) if isinstance(ids, (list, tuple)) and ids else str(ids)
        body = _post(_DETAIL, {'playlet_id': coll, 'vid': coll, 'is_collection': '1'},
                     query='')
        try:
            d = json.loads(body).get('data', {})
        except Exception:
            d = {}
        vids = [str(v) for v in (d.get('vid_list') or []) if v]
        eps = []
        for i, v in enumerate(vids, 1):
            eps.append('第%s集$%s' % (i, v))
        if not eps:
            eps.append('第1集$%s' % coll)
        epn = d.get('episodes_num') or ('%s' % len(vids) if vids else '')
        vod = {
            'vod_id': coll,
            'vod_name': d.get('playlet_title') or coll,
            'vod_pic': d.get('playlet_poster') or '',
            'type_name': d.get('tag_text') or '',
            'vod_remarks': ('%s集' % epn) if epn else '',
            'vod_content': d.get('description') or '',
            'vod_play_from': '拜拜短剧',
            'vod_play_url': '#'.join(eps),
        }
        return {'list': [vod]}

    # ================= 搜索 =================
    def searchContent(self, key, quick):
        ms = _ts()
        body = {'data': json.dumps({'data': {
            'query': str(key), 'page': 1, 'title': [], 'attribute': ['title'],
            'fe_page_type': 'search', 'service': 'bdbox', 'timestamp': ms,
            'version': _ver(ms)}}, ensure_ascii=False)}
        resp = _post(_SEARCH, body)
        try:
            obj = json.loads(resp)
        except Exception:
            return {'list': []}
        return {'list': _items(obj)}

    # ================= 播放 =================
    def playerContent(self, flag, id, vipFlags):
        vid = str(id)
        form = ('method=post&vid=%s&immersive_mode=v4_5&tplname=feed_small_video'
                '&tag=playlet_talos&tab=detail&external_from=&is_dp_video=0'
                '&immersive_square_type=3&video_set_id=%s&play_screen_type=1'
                % (vid, vid))
        req = urllib.request.Request(_RELATE + '?osbranch=a0',
                                     data=('video/relate=' + urllib.parse.quote(form)).encode(),
                                     headers={'User-Agent': _UA,
                                              'Content-Type': 'application/x-www-form-urlencoded'})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                j = json.loads(r.read().decode('utf-8', 'replace'))
        except Exception:
            return {}
        cur = {}
        try:
            cur = j['video/relate']['data']['cur_video']
        except Exception:
            pass
        url = cur.get('video_src') or ''
        return {'parse': 0, 'playUrl': url, 'header': {'User-Agent': _UA}}


class BddjAmns(Spider):
    """OK影视 api=csp_BddjAmns 别名类"""
    pass
