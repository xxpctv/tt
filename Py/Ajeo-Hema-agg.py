# -*- coding: utf-8 -*-
"""
河马短剧 Hema 独立版（聚合短剧.js 提取，freevideo.zqqds.cn 体系）
请求链（全部 POST https://freevideo.zqqds.cn/free-video-portal/portal/{ep}）：
  - 1121 列表   body = AES-CBC-hex({recSwitch,channelId,tagIds,cnxhFlag,playListFlag,watchRecords})
  - 1131 详情   body = AES-CBC-hex({bookId})
  - 1132 剧集   body = AES-CBC-hex({bookId,chapterMin,chapterMax})
  - 1133 播放   body = AES-CBC-hex({bookId,chapterId,unClockType,confirmPay,autoPayFlag,omap})
  - 1803 搜索   body = AES-CBC-hex({keyword,page,size})
  响应: {data: AES-CBC-hex(JSON)}  -> 解密后解析
签名：AES-CBC/PKCS5，key=dzkjgfyxgshylgzm iv=apiupdownedcrypt（输出 hex 大写）；
     请求头带固定 datas 串 + Content-Type text/plain（列表/详情/剧集/播放加 form）
     与 Ajeo-Hema.py（aowu 盒马 2122 体系 + HMAC sign）同服务器不同实现，可互为备用
兼容：OK影视 / 影视仓（TVBox Python 引擎）
"""
import json
import urllib.parse
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
_LIST = '/free-video-portal/portal/1121'
_DETAIL = '/free-video-portal/portal/1131'
_EPISODE = '/free-video-portal/portal/1132'
_PLAY = '/free-video-portal/portal/1133'
_SEARCH = '/free-video-portal/portal/1803'

_AES_KEY = bytes.fromhex('647a6b6a67667978677368796c677a6d')   # dzkjgfyxgshylgzm
_AES_IV = bytes.fromhex('6170697570646f776e65646372797074')   # apiupdownedcrypt

# 请求头固定 datas（聚合短剧.js 原样）
_DATAS = ('e5f22c6e2c82fe001738cb9ce4696eab0556d064a55aef402e0fbe6b29a083f6538e4567de38e67de2071a49d9751526bfba45314e1fd4702b11c76ab9a3b5f873262854ba66e6715ed51364dbc6ee62c7180e047fcbcdbfd49874fc8f28674b16d90ca71a02de76c70598e0b75e647c37c2c19287e49be5f2a259d727dfc4df3d28802388bf3c356576b342e17e30a2ab74859263dba4d1c8eba79990d22d60d60927fdacb2addf2f0eaadd8887585ca2eb87f603faf0c207dda18cf67dc25b2199d303baff9e6605b3314a7d2631f62864f48619daceb9452f2b7b0667773553741856df030cca68af3c57810f983d452bb428ef5fc32206aef4865ae06c629bee7f5135547304acc7ef4e7c6df887308f2e79c493fd2ee03488722861b5bb51b09cb8911dfc92c288d94e601c066d2f9d612ad2c8d4eeb4920b1d44aff3e13fd75229b857f64925df1cf12f75a00d438c422ec1726462b915903f1dd1f4bb7cdf82cc15a6d507f80c789903e710f39a62aef073f3f93a6c681e75d295428aa290d7e98f82e7e9ad6e2b23d9086dfe8c63c5d8550b13fd61a77291473a8bdd43c7c2639f264be69d9d07f0585de4342a399275a64e7d1d4400b8ed4421a2f289f622e40cdd1cfc916a0b9ce747c924ac33e32d24b91ed5d64772d6ad6896412f52724006eabf12aaecfd6e81dad432c7b3800bbf793a1c375e3e7b4fb3b097724b5fc88a8c9bcf3dbc10cbdb252965')

_CLASSES = [
    ('308', '推荐'), ('309', '新剧'), ('310', '逆袭'), ('311', '恋爱'),
    ('312', '强者回归'), ('313', '豪门恩怨'), ('314', '古装'), ('315', '重生'),
    ('316', '萌宝'), ('317', '复仇'), ('318', '神医'), ('319', '高手下山'),
    ('320', '超能悬疑'), ('321', '传承觉醒'), ('322', '神豪'), ('323', '民国'),
]

# 分类 -> 标签 ids
_TAG_IDS = {
    '308': '', '309': '', '310': '417,473,474,464', '311': '462,466', '312': '476',
    '313': '585,616', '314': '444,468', '315': '417,439,464,465', '316': '589',
    '317': '416,439,463,465', '318': '438', '319': '417,474,464',
    '320': '439,442,443,445,465,470', '321': '417,473,474,464',
    '322': '472,475,585', '323': '590',
}


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
    # 去 PKCS7 填充
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
    name = '河马短剧'
    siteKey = 'Hema'

    def init(self, extend=''):
        return ''

    def homeContent(self, filter):
        return {'class': [{'type_id': i, 'type_name': n} for i, n in _CLASSES]}

    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid or '308')
        if extend and not isinstance(extend, dict):
            try:
                extend = json.loads(str(extend))
            except Exception:
                extend = None
        if isinstance(extend, dict) and extend.get('area'):
            tid = str(extend['area'])
        body = {
            'recSwitch': True,
            'channelId': tid,
            'tagIds': _TAG_IDS.get(tid, ''),
            'cnxhFlag': (int(pg or 1) - 1),
            'playListFlag': True,
            'watchRecords': ['41000103722_572752006'],
        }
        j = _post(_LIST, json.dumps(body), form_ct=True)
        lst = []
        for arr in j.get('columnData') or []:
            for v in arr.get('videoData') or []:
                lst.append({
                    'vod_id': str(v.get('bookId', '')),
                    'vod_name': v.get('bookName') or '',
                    'vod_pic': v.get('coverWap') or v.get('coverCutWap') or '',
                    'vod_remarks': '河马短剧 | 更新%s集' % (v.get('updateNum') or 0),
                    'vod_content': v.get('introduction') or '',
                })
        return {'list': lst, 'page': pg, 'pagecount': int(pg or 1) + 1}

    def detailContent(self, ids):
        book_id = str(ids[0] if isinstance(ids, list) else ids)
        j1 = _post(_DETAIL, json.dumps({'bookId': book_id}), form_ct=True)
        info = j1.get('videoInfo') or {}
        j2 = _post(_EPISODE, json.dumps({
            'bookId': book_id,
            'chapterMin': info.get('updateNum') or 0,
            'chapterMax': info.get('chapterIndex') or 0,
        }), form_ct=True)
        chs = j2.get('chapterList') or []
        eps = []
        for it in chs:
            name = it.get('chapterName') or '第%s集' % len(eps)
            eps.append('%s$%s++%s++%s' % (name, it.get('chapterId'), it.get('chapterIndex'), book_id))
        vod = {
            'vod_id': book_id,
            'vod_name': info.get('bookName') or '',
            'vod_pic': info.get('coverWap') or '',
            'vod_remarks': info.get('finishStatusCn') or ('更新至%s集' % (info.get('updateNum') or 0)),
            'vod_content': info.get('introduction') or '',
            'vod_play_from': '河马短剧',
            'vod_play_url': '#'.join(eps) or '暂无播放地址$0',
        }
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        try:
            arr = str(id).split('++')
            chapter_id = arr[0]
            chapter_index = arr[1] if len(arr) > 1 else ''
            book_id = arr[2] if len(arr) > 2 else chapter_id
            body = {
                'bookId': book_id,
                'chapterId': chapter_id,
                'unClockType': 'pay',
                'confirmPay': 2,
                'autoPayFlag': True,
                'omap': {
                    'channelName': '精选',
                    'logId': '17a6500357709bb2547e1e122b438cfc',
                    'originName': '书城',
                    'recId': 'bigdata_rec',
                    'scene': 'nsc_727',
                    'sceneId': 'dzmf_video_sc_reco',
                    'strategyId': 'g6y6b5sq',
                },
            }
            j = _post(_PLAY, json.dumps(body), form_ct=True)
            if j.get('chaptersPayType') == '免费':
                url = (j.get('chapterInfo') or [{}])[0].get('content', {}).get('m3u8720p') or []
                if url:
                    return {'parse': 0, 'url': url}
            # 兜底第三方解析
            return {'parse': 0, 'url': 'https://api.cenguigui.cn/api/duanju/hema.php?book_id=%s&video_id=%s&type=mp4#isVideo=true#' % (book_id, chapter_id)}
        except Exception:
            return {'parse': 0, 'url': id}

    def searchContent(self, key, quick=True, pg=1):
        k = str(key or '').strip()
        body = {'keyword': k, 'page': str(pg or 1), 'size': '20'}
        j = _post(_SEARCH, json.dumps(body))
        lst = []
        for v in j.get('searchVos') or []:
            title = str(v.get('bookName') or '')
            # 搜索范围：标题 或 演员 包含关键词（不匹配简介/详情）
            actor = _actor_of(v)
            if k and k not in title and k not in actor:
                continue
            lst.append({
                'vod_id': str(v.get('bookId', '')),
                'vod_name': title,
                'vod_pic': v.get('coverWap') or '',
                'vod_remarks': '河马短剧 | 共%s集' % (v.get('updateNum') or 0),
                'vod_content': v.get('introduction') or '',
            })
        return {'list': lst}

    # 兼容别名
    def quickSearch(self, key):
        return self.searchContent(key, True)

    def search(self, key):
        return self.searchContent(key, True)
