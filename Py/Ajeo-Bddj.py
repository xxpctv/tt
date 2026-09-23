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


def _list_body(kind, page, themes=None):
    # 2026-09-17 抓包实锤（原版 aowu-业务版 csp_BddjAmns 真实请求，252KB flow）：
    # extRequest.flow_tabid='13'（嵌套字符串）；page='channel_video_landing'（固定字符串，非页码）；
    # 页码=refreshIndex 递增；theme 字段【恒为空串】，筛选值全部进 themes 数组：
    #   [{"kind":"综合","names":[tab名]}, {"kind":"受众","names":["男频"]},
    #    {"kind":"题材","names":["甜宠"]}, {"kind":"集数","names":["1-30集"]},
    #    {"kind":"状态","names":["完结"]}, {"kind":"付费","names":["免费"]}]
    # 未选维度不出现；kind 顺序 = 综合→状态→集数→受众→题材→付费
    # timestamp/version 同毫秒，version=md5(ms+'v2')
    ms = _ts()
    if not themes:
        themes = [{'kind': '综合', 'names': [kind]}]
    return {'data': json.dumps({'data': {
        'extRequest': {'flow_tabid': '13'},
        'from': 'feed',
        'page': 'channel_video_landing',
        'pd': 'feed',
        'refreshIndex': int(page or 1),
        'cursor': '',
        'theme': '',
        'timestamp': ms,
        'version': _ver(ms),
        'themes': themes}}, ensure_ascii=False)}


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
    siteKey = 'Bddj'

    def init(self, extend=''):
        return ''

    # ================= 首页 =================
    def homeContent(self, filter):
        # 原版分类（aowu-业务版 csp_BddjAmns 截图实锤）：
        # 顶部分类 = 新剧/限免/精选/独播（"首页"是 OK影视 壳自带固定 tab，非 py 返回）；
        # 筛选 = 受众/题材/集数/状态/付费；默认加载"新剧"tab（对齐原版 homeContent 请求）
        _FILTERS = [
            {'key': '受众', 'name': '受众',
             'value': [{'n': '男频', 'v': '男频'}, {'n': '女频', 'v': '女频'}]},
            {'key': '题材', 'name': '题材',
             'value': [{'n': t, 'v': t} for t in (
                 '神医', '连续剧', '都市', '现代言情', '异能', '逆袭', '甜宠', '总裁',
                 '萌宝', '战神', '宫斗宅斗', '神豪', '虐恋', '闪婚', '玄幻', '穿越重生', '年代')]},
            {'key': '集数', 'name': '集数',
             'value': [{'n': t, 'v': t} for t in ('1-30集', '30-60集', '60-90集', '90集以上')]},
            {'key': '状态', 'name': '状态',
             'value': [{'n': '完结', 'v': '完结'}, {'n': '更新', 'v': '更新'}]},
            {'key': '付费', 'name': '付费',
             'value': [{'n': '免费', 'v': '免费'}, {'n': '付费', 'v': '付费'}]},
        ]
        classes = [{'type_id': t, 'type_name': t}
                   for t in ('新剧', '限免', '精选', '独播')]
        filters = {c['type_id']: _FILTERS for c in classes}
        body = _post(_LIST, _list_body('新剧', 1))
        try:
            obj = json.loads(body)
        except Exception:
            obj = {}
        return {'class': classes, 'filters': filters, 'list': _items(obj)}

    def categoryContent(self, tid, pg, filter, extend):
        # OK影视 契约：filter 是布尔开关，筛选值在 extend（OK影视 传 JSON 字符串）
        # 原版实锤（2026-09-17 抓包）：theme 字段恒为空串，筛选值全部进 themes 数组，
        #   kind 顺序 = 综合→状态→集数→受众→题材→付费；未选维度不出现
        themes = [{'kind': '综合', 'names': [str(tid)]}]
        if extend and not isinstance(extend, dict):
            try:
                extend = json.loads(str(extend))
            except Exception:
                extend = None
        if extend and isinstance(extend, dict):
            for k in ('状态', '集数', '受众', '题材', '付费'):
                v = extend.get(k)
                if v:
                    themes.append({'kind': k, 'names': [str(v)]})
        body = _post(_LIST, _list_body(str(tid), pg, themes))
        try:
            obj = json.loads(body)
        except Exception:
            obj = {}
        return {'page': int(pg or 1), 'pagecount': 9999, 'limit': 90,
                'total': 9999, 'list': _items(obj)}

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
    def searchContent(self, key, quick=True, pg=1):
        # OK影视 5.1.6 传 3 参(key, quick, page)；2 参会被 TypeError 静默跳过
        # 注意：tab_id/flow_tabid/tab_type/sub_template 等字段会导致服务端
        # 报 "hasn't attribute"（code=3008278639）—— 只传基础字段
        ms = _ts()
        # 注意：playlets/search 用一层 data（data=<业务对象>），
        # 不要像 playlets/list 那样两层 data 包装（否则服务端 has't attribute）
        body = {'data': json.dumps({
            'query': str(key), 'page': int(pg or 1), 'title': [], 'attribute': ['title'],
            'fe_page_type': 'search', 'service': 'bdbox', 'timestamp': ms,
            'version': _ver(ms)}, ensure_ascii=False)}
        resp = _post(_SEARCH, body)
        try:
            obj = json.loads(resp)
        except Exception:
            return {'list': []}
        out = []
        try:
            items = obj['data']['itemList']
        except Exception:
            items = []
        for it in items or []:
            nid = str(it.get('nid', ''))
            vid = nid.split('_')[-1] if nid else ''
            title = it.get('title', '')
            out.append({
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': it.get('img', ''),
                'vod_remarks': ('%s集' % it.get('collNum')) if it.get('collNum') else '',
            })
        # 标题过滤：只保留标题含关键词（规则：不搜简介）
        return {'list': [v for v in out if not key or (key in (v.get('vod_name') or ''))]}

    # ================= 播放 =================
    def playerContent(self, id, flag, vipFlags):
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
