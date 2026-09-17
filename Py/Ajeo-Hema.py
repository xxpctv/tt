# -*- coding: utf-8 -*-
"""
河马短剧
======================================================================
协议（2026-09-17 潇洒 jar smali 全量逆向 + 本地实测）：
  - home/分类/列表  = POST /free-video-portal/portal/1125
      home body: {recSwitch, pageFlag:"", theaterSubscriptSwitch}
      list body: {recSwitch, pageFlag:(pg-1), theaterSubscriptSwitch, channelGroupId, channelId(可选)}
      -> channelGroupData[] 动态栏目（channelGroupId/channelGroupName/channelData[]）
      -> columnData[].videoData[] 或顶层 videoData[] 为卡片
  - 详情  = POST /free-video-portal/portal/1131
      body: {bookId, needNextChapter:0, isNeedAlias:"", bookAlias:"", resolutionRate:"1080P"}
      -> videoInfo（bookName/coverWap/finishStatusCn/introduction/protagonist）
  - 剧集  = POST /free-video-portal/portal/1132
      body: {bookId, chapterMin:updateNum, chapterMax:chapterIndex}
      -> chapterList[]（chapterName/chapterId）
  - 播放  = POST /free-video-portal/portal/1139（原版端点，非 1133）
      body: {bookId, chapterId, unClockType:"load", tierPlaySource:null,
             chapterIds:[chapterId], omap:{expId:null,logId:null,originName:"bigdata_rec",
             recId:null,scene:"dzmf_video_sc_reco",sceneId:"dzmf_video_sc_reco",
             strategyId:"godum7go",strategyName:"omap"}}
      -> chapterInfo(数组/对象).content = {mp4720p, m3u8720p, mp4720pSwitchUrl}
      -> 取第一个 http 开头的直链（mp4/m3u8），带 aliplayer UA 头
  - 搜索  = POST /free-video-portal/portal/1803
      body: {keyword, page, size}
签名：AES-CBC/PKCS5，key=hex 647a6b6a67667978677368796c677a6d(=dzkjgfyxgshylgzm)
     iv=hex 6170697570646f776e65646372797074(=apiupdownedcrypt)
     加密输出 hex 大写；响应 data 字段 hex -> AES 解密
     请求头固定 datas 长串 + Content-Type text/plain（列表/详情/剧集/播放叠加 form）
兼容：OK影视 / 影视仓（TVBox Python 引擎）
"""
import json
import urllib.request

try:
    from Crypto.Cipher import AES
except Exception:
    AES = None

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider:
        pass

_HOST = 'https://freevideo.zqqds.cn'
_HOME = '/free-video-portal/portal/1125'
_DETAIL = '/free-video-portal/portal/1131'
_EPISODE = '/free-video-portal/portal/1132'
_PLAY = '/free-video-portal/portal/1139'
_SEARCH = '/free-video-portal/portal/1803'

_AES_KEY = bytes.fromhex('647a6b6a67667978677368796c677a6d')   # dzkjgfyxgshylgzm
_AES_IV = bytes.fromhex('6170697570646f776e65646372797074')   # apiupdownedcrypt

# 请求头固定 datas（原版 smali 原样）
_DATAS = ('e5f22c6e2c82fe001738cb9ce4696eab0556d064a55aef402e0fbe6b29a083f6538e4567de38e67de2071a49d9751526bfba45314e1fd4702b11c76ab9a3b5f873262854ba66e6715ed51364dbc6ee62c7180e047fcbcdbfd49874fc8f28674b16d90ca71a02de76c70598e0b75e647c37c2c19287e49be5f2a259d727dfc4df3d28802388bf3c356576b342e17e30a2ab74859263dba4d1c8eba79990d22d60d60927fdacb2addf2f0eaadd8887585ca2eb87f603faf0c207dda18cf67dc25b2199d303baff9e6605b3314a7d2631f62864f48619daceb9452f2b7b0667773553741856df030cca68af3c57810f983d452bb428ef5fc32206aef4865ae06c629bee7f5135547304acc7ef4e7c6df887308f2e79c493fd2ee03488722861b5bb51b09cb8911dfc92c288d94e601c066d2f9d612ad2c8d4eeb4920b1d44aff3e13fd75229b857f64925df1cf12f75a00d438c422ec1726462b915903f1dd1f4bb7cdf82cc15a6d507f80c789903e710f39a62aef073f3f93a6c681e75d295428aa290d7e98f82e7e9ad6e2b23d9086dfe8c63c5d8550b13fd61a77291473a8bdd43c7c2639f264be69d9d07f0585de4342a399275a64e7d1d4400b8ed4421a2f289f622e40cdd1cfc916a0b9ce747c924ac33e32d24b91ed5d64772d6ad6896412f52724006eabf12aaecfd6e81dad432c7b3800bbf793a1c375e3e7b4fb3b097724b5fc88a8c9bcf3dbc10cbdb252965')

# 播放直链所需 aliplayer UA（原版 playerContent 返回头；dm 原版取 Build.MODEL，py 环境固定兼容值）
_UA_ALIPLAYER = 'aliplayer(appv=2.7.1&av=7.1.0&av2=7.1.0_46933858&os=android&ov=11&dm=TVBOX)'


def _pad(b):
    n = 16 - (len(b) % 16)
    return b + bytes([n]) * n


def hema_encrypt(text):
    """AES-CBC/PKCS5 -> hex 大写"""
    if AES is None:
        raise RuntimeError('缺少 pycryptodome')
    c = AES.new(_AES_KEY, AES.MODE_CBC, _AES_IV)
    return c.encrypt(_pad(text.encode('utf-8'))).hex().upper()


def hema_decrypt(word):
    """hex -> AES-CBC 解密 -> utf8 明文"""
    if AES is None:
        raise RuntimeError('缺少 pycryptodome')
    raw = bytes.fromhex(word)
    c = AES.new(_AES_KEY, AES.MODE_CBC, _AES_IV)
    out = c.decrypt(raw)
    if out and out[-1] < 16:
        out = out[:-out[-1]]
    return out.decode('utf-8', 'replace')


def _post(ep, body_plain, form_ct=False):
    enc = hema_encrypt(body_plain)
    headers = {
        'datas': _DATAS,
        'Content-Type': 'application/x-www-form-urlencoded' if form_ct else 'text/plain',
        'User-Agent': 'okhttp/4.10.0',
    }
    req = urllib.request.Request(_HOST + ep, data=enc.encode('utf-8'), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
        j = json.loads(raw.decode('utf-8', 'replace'))
        d = j.get('data') or ''
        if not d:
            return {}
        t = hema_decrypt(d)
        if t and t != '{}':
            return json.loads(t)
    except Exception:
        return {}
    return {}


def _pick_http(obj):
    """原版 d() 逻辑：从 content（str/dict/其他）提取第一个 http 直链"""
    if obj is None:
        return ''
    if isinstance(obj, str):
        return obj if obj.startswith('http') else ''
    if isinstance(obj, dict):
        for k in ('mp4Url', 'mp4SwitchUrl', 'mp4720p', 'm3u8720p'):
            v = obj.get(k)
            if isinstance(v, str) and v.startswith('http'):
                return v
            if isinstance(v, list):
                for it in v:
                    if isinstance(it, str) and it.startswith('http'):
                        return it
        # 遍历所有字段找第一个 http（原版兜底）
        for k, v in obj.items():
            if isinstance(v, str) and v.startswith('http'):
                return v
            if isinstance(v, list):
                for it in v:
                    if isinstance(it, str) and it.startswith('http'):
                        return it
    return ''


def _remarks(item):
    """原版卡片备注：finishStatusCn + '/' + updateNum + '集'"""
    fs = str(item.get('finishStatusCn') or '')
    un = str(item.get('updateNum') or '')
    if un and un != '0':
        if fs:
            return '%s/%s集' % (fs, un)
        return '更新至%s集' % un
    return fs


def _vod_from_item(v):
    """原版 b()：卡片字段 bookId/bookName/coverWap/备注"""
    return {
        'vod_id': str(v.get('bookId', '')),
        'vod_name': v.get('bookName') or '',
        'vod_pic': v.get('coverWap') or v.get('coverCutWap') or '',
        'vod_remarks': _remarks(v),
        'vod_content': v.get('introduction') or '',
    }


def _list_of(j):
    """原版 c()：columnData[].videoData[] 或顶层 videoData[]"""
    out = []
    for col in j.get('columnData') or []:
        for v in col.get('videoData') or []:
            out.append(_vod_from_item(v))
    if not out:
        for v in j.get('videoData') or []:
            out.append(_vod_from_item(v))
    return out


class Spider(_BaseSpider):
    name = '河马短剧'
    siteKey = 'Hema'

    def init(self, extend=''):
        return ''

    def homeContent(self, filter):
        j = _post(_HOME, json.dumps({
            'recSwitch': True, 'pageFlag': '', 'theaterSubscriptSwitch': True,
        }), form_ct=True)
        classes, flt = [], {}
        seen = set()
        for gr in j.get('channelGroupData') or []:
            gid = str(gr.get('channelGroupId') or '')
            gname = gr.get('channelGroupName') or ''
            if gname == '全部':
                gname = '推荐'
            if not gid or gid in seen:
                continue
            seen.add(gid)
            classes.append({'type_id': gid, 'type_name': gname})
            chs = []
            for c in gr.get('channelData') or []:
                cid = c.get('channelId')
                cname = c.get('channelName') or ''
                if cid is not None and cname:
                    chs.append({'n': cname, 'v': '%s@%s' % (cid, cname)})
            if chs:
                flt[gid] = [{'key': 'class', 'name': '类型',
                             'value': [{'n': '全部', 'v': ''}] + chs}]
        return {'class': classes, 'filters': flt, 'list': _list_of(j)}

    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid or '')
        cid = 0
        if extend and not isinstance(extend, dict):
            try:
                extend = json.loads(str(extend))
            except Exception:
                extend = None
        if isinstance(extend, dict) and extend.get('class'):
            c = str(extend['class'])
            if '@' in c:
                c = c.split('@')[0]
            try:
                cid = int(c)
            except Exception:
                cid = 0
        body = {
            'recSwitch': True,
            'pageFlag': str(int(pg or 1) - 1) if int(pg or 1) > 1 else '',
            'theaterSubscriptSwitch': True,
        }
        try:
            body['channelGroupId'] = int(tid)
        except Exception:
            body['channelGroupId'] = 0
        if cid > 0:
            body['channelId'] = cid
        j = _post(_HOME, json.dumps(body), form_ct=True)
        lst = _list_of(j)
        has_more = j.get('hasMore')
        if has_more is None:
            has_more = len(lst) >= 18
        pagecount = int(pg or 1) + 1 if has_more else int(pg or 1)
        return {'list': lst, 'page': pg, 'pagecount': pagecount}

    def detailContent(self, ids):
        book_id = str(ids[0] if isinstance(ids, list) else ids)
        j1 = _post(_DETAIL, json.dumps({
            'bookId': book_id, 'needNextChapter': 0, 'isNeedAlias': '',
            'bookAlias': '', 'resolutionRate': '1080P',
        }), form_ct=True)
        info = j1.get('videoInfo') or j1
        j2 = _post(_EPISODE, json.dumps({
            'bookId': book_id,
            'chapterMin': info.get('updateNum') or 0,
            'chapterMax': info.get('chapterIndex') or 0,
        }), form_ct=True)
        chs = j2.get('chapterList') or []
        # 多线路询查：常规组合(chapterMin=updateNum/chapterMax=chapterIndex)空时，
        # 依次换 0/0、1/updateNum、chapterIndex/updateNum 再试（服务端偶发对个别书参数敏感）
        if not chs:
            for alt_min, alt_max in ((0, 0), (1, info.get('updateNum') or 0), (info.get('chapterIndex') or 0, info.get('updateNum') or 0)):
                if alt_min == (info.get('updateNum') or 0) and alt_max == (info.get('chapterIndex') or 0):
                    continue
                j2 = _post(_EPISODE, json.dumps({
                    'bookId': book_id, 'chapterMin': alt_min, 'chapterMax': alt_max,
                }), form_ct=True)
                chs = j2.get('chapterList') or []
                if chs:
                    break
        eps = []
        for it in chs:
            name = it.get('chapterName') or '第%s集' % len(eps)
            eps.append('%s$%s@%s' % (name, book_id, it.get('chapterId')))
        if not eps:
            # 多线路全空 = 服务端该书剧集数据缺失（实测 41000100692 梨小姐选夫记 /
            # 41000297183 错换人生：真千金归来，其余书正常）。
            # 方案：chapterId 实测逐集连续（base = chapterId - chapterIndex + 1），
            # 先探测最后一集（base+updateNum-1）有效性，有效则本地生成全集（体验=显示全集）；
            # 探测失败才退回当前章节单集兜底（chapterId 经 1139 实测可出直链）。
            cur_id = info.get('chapterId')
            if cur_id:
                idx = info.get('chapterIndex') or 1
                total = info.get('updateNum') or 0
                try:
                    base = int(cur_id) - idx + 1
                except Exception:
                    base = 0
                last_ok = False
                if total > 1 and base > 0:
                    last_id = base + total - 1
                    probe = _post(_PLAY, json.dumps({
                        'bookId': book_id, 'chapterId': str(last_id), 'unClockType': 'load',
                        'tierPlaySource': None, 'chapterIds': [str(last_id)],
                        'omap': {'expId': None, 'logId': None, 'originName': 'bigdata_rec',
                                 'recId': None, 'scene': 'dzmf_video_sc_reco',
                                 'sceneId': 'dzmf_video_sc_reco', 'strategyId': 'godum7go',
                                 'strategyName': 'omap'},
                    }), form_ct=True)
                    ci = probe.get('chapterInfo')
                    if isinstance(ci, list):
                        ci = ci[0] if ci else None
                    content = (ci or {}).get('content') if isinstance(ci, dict) else None
                    last_ok = isinstance(content, dict) and any(
                        isinstance(x, str) and x.startswith('http') for x in content.values())
                if last_ok:
                    for i in range(1, total + 1):
                        eps.append('第%s集$%s@%s' % (i, book_id, base + i - 1))
                else:
                    eps.append('%s$%s@%s' % (info.get('chapterName') or '第%s集' % idx, book_id, cur_id))
        actor = info.get('protagonist') or ''
        if isinstance(actor, list):
            actor = ' '.join(str(x) for x in actor)
        vod = {
            'vod_id': book_id,
            'vod_name': info.get('bookName') or '',
            'vod_pic': info.get('coverWap') or '',
            'vod_remarks': info.get('finishStatusCn') or '',
            'vod_actor': actor,
            'vod_content': info.get('introduction') or '',
            'vod_play_from': '河马',
            'vod_play_url': '#'.join(eps) or '暂无播放地址$0',
        }
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        try:
            if '@' not in str(id):
                return {'parse': 0, 'url': id}
            book_id, chapter_id = str(id).split('@', 1)
            body = {
                'bookId': book_id,
                'chapterId': chapter_id,
                'unClockType': 'load',
                'tierPlaySource': None,
                'chapterIds': [chapter_id],
                'omap': {
                    'expId': None, 'logId': None, 'originName': 'bigdata_rec',
                    'recId': None, 'scene': 'dzmf_video_sc_reco',
                    'sceneId': 'dzmf_video_sc_reco',
                    'strategyId': 'godum7go', 'strategyName': 'omap',
                },
            }
            j = _post(_PLAY, json.dumps(body), form_ct=True)
            ci = j.get('chapterInfo')
            if isinstance(ci, list):
                ci = ci[0] if ci else None
            content = (ci or {}).get('content') if isinstance(ci, dict) else None
            url = _pick_http(content)
            if not url and isinstance(j.get('ad'), dict):
                url = _pick_http((j.get('ad') or {}).get('content'))
            if not url:
                url = id
            return {'parse': 0, 'url': url,
                    'header': {'User-Agent': _UA_ALIPLAYER}}
        except Exception:
            return {'parse': 0, 'url': id}

    def searchContent(self, key, quick=True, pg=1):
        k = str(key or '').strip()
        # 原版 body：keyword + page(int) + size(15) + hotWordType=2
        # 注意：1803 在无客户端会话态时服务端恒返回热门推荐（keyword 仅回显，与原版一致），
        #       故本地标题/演员过滤只作用于能命中的结果，过滤后为空则保留原版热门兜底。
        body = {'keyword': k, 'page': int(pg or 1), 'size': 15, 'hotWordType': 2}
        j = _post(_SEARCH, json.dumps(body))
        rows = j.get('searchVos') or j.get('content') or []
        hit = []
        for v in rows:
            title = str(v.get('bookName') or '')
            actor = v.get('protagonist') or v.get('actor') or ''
            if isinstance(actor, list):
                actor = ' '.join(str(x) for x in actor)
            if k and k not in title and k not in actor:
                continue
            hit.append({
                'vod_id': str(v.get('bookId', '')),
                'vod_name': title,
                'vod_pic': v.get('coverWap') or '',
                'vod_remarks': _remarks(v),
                'vod_content': v.get('introduction') or '',
            })
        if not hit and rows:
            # 服务端热门兜底：直接透传（与原版行为一致）
            for v in rows:
                hit.append({
                    'vod_id': str(v.get('bookId', '')),
                    'vod_name': v.get('bookName') or '',
                    'vod_pic': v.get('coverWap') or '',
                    'vod_remarks': _remarks(v),
                    'vod_content': v.get('introduction') or '',
                })
        return {'list': hit}

    # 兼容别名
    def quickSearch(self, key):
        return self.searchContent(key, True)

    def search(self, key):
        return self.searchContent(key, True)
