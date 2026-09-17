# -*- coding: utf-8 -*-
"""
牛牛短剧 Niuniu 独立版（聚合短剧.js 提取，tianjinzhitongdaohe.com 系）
请求链：
  - 访客token:  GET https://new.tianjinzhitongdaohe.com/api/v1/app/user/visitorInfo
                headers: deviceid/token=''/client=app/devicetype=Android/UA okhttp/4.12.0 -> data.token
  - 广告token:  POST https://csj-sp.csjdeveloper.com/csj_sp/api/v1/user/login?siteid=5627189
                body = AES-ECB(form串, 'dafdb3d2a5c343d6')
                headers: X-Salt=786774955F X-Nonce=VX1KKGtoBDCi1fB1 X-Timestamp=t
                         X-Signature=HMAC-SHA256(t+nonce+body明文, 'aceaa47f96b4875d446b2e1d97e03bbb')
                resp = AES-ECB解密 -> data.access_token
  - 列表:  POST /api/v1/app/screen/screenMovie {"condition":{"typeId":"S1","classify"},pageNum,pageSize:24} -> data.records
  - 详情:  POST /api/v1/app/play/movieDesc {"id","typeId":"S1"} -> data{name,cover,classify,score,introduce,totalEpisode}
           POST /api/v1/app/play/movieDetails {"id","source":0,"typeId":"S1","userId":"546932"} -> data{url,episodeList,thirdPlayId}
  - 搜索:  POST /api/v1/app/search/searchMovie {"condition":{"typeId":"S1","value"},pageNum,pageSize:20} -> data.records
  - 播放:  2段: POST movieDetails {id:videoId,episodeId} -> data.url
           3段(free/lock): POST csj-sp shortplay/detail 或 pay/ad_unlock + shortplay/detail
           body=AES-ECB(form串,'ce49b18dd4e0a4d8') 签名同 login（X-Salt=FD8188A8D5 X-Nonce=X9UknYKtLa3DmtjC X-Access-Token）
           url = base64Decode(list[0].video_model.video_list.video_1.main_url)
签名：AES-ECB/PKCS7 + HMAC-SHA256(hex) + X-Salt/X-Nonce/X-Timestamp/X-Signature/X-Access-Token
兼容：OK影视 / 影视仓（TVBox Python 引擎）
"""
import base64
import hashlib
import hmac
import json
import time
import uuid
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

_HOST = 'https://new.tianjinzhitongdaohe.com'
_CSJ = 'https://csj-sp.csjdeveloper.com/csj_sp'
_LIST = '/api/v1/app/screen/screenMovie'
_DETAIL = '/api/v1/app/play/movieDetails'
_DESC = '/api/v1/app/play/movieDesc'
_SEARCH = '/api/v1/app/search/searchMovie'
_VISITOR = '/api/v1/app/user/visitorInfo'
_LOGIN = _CSJ + '/api/v1/user/login?siteid=5627189'
_DETAIL2 = _CSJ + '/api/v1/shortplay/detail?siteid=5627189'
_UNLOCK = _CSJ + '/api/v1/pay/ad_unlock?siteid=5627189'

_HMAC_KEY = 'aceaa47f96b4875d446b2e1d97e03bbb'
_ECB_KEY_LOGIN = 'dafdb3d2a5c343d6'   # login 加密密钥
_ECB_KEY = 'ce49b18dd4e0a4d8'         # detail2/unlock 加密密钥
_SALT_LOGIN = '786774955F'
_NONCE_LOGIN = 'VX1KKGtoBDCi1fB1'
_SALT = 'FD8188A8D5'
_NONCE = 'X9UknYKtLa3DmtjC'

# 聚合短剧.js 牛牛播放/解锁固定设备参数
_DEV = {
    'clientVersion': 'v5.2.5',
    'uuid': '6IDYUSASPQY5BBVACWQW3LLTPV4V7DE26UOCX5TZTVUGX4VUJNXQ01',
    'resolution': '1080*2320',
    'openudid': '82f4175d577a2939',
    'dt': '22021211RC',
    'os_api': '31',
    'install_id': '1496879012031075',
    'sdk_version': '1.1.3.0',
    'siteid': '5627189',
    'dev_log_aid': '667431',
    'oaid': 'abec0dfff623201b',
    'sha1': '46121F77CE2FCAD3DBC3B9EC8A24908C1A8AD6D9',
    'device_brand': 'Redmi',
    'package_name': 'com.niuniu.ztdh.app',
    'vod_version': '1.10.21.6-tob',
    'os_version': '12',
}

_CLASSES = [
    ('现言', '现言'), ('古言', '古言'), ('历史', '历史'), ('都市', '都市'), ('活动', '活动'),
    ('逆袭', '逆袭'), ('豪门', '豪门'), ('现代言情', '现代言情'), ('战神', '战神'), ('甜宠', '甜宠'),
    ('穿越', '穿越'), ('古装', '古装'), ('虐心', '虐心'), ('神医', '神医'), ('赘婿', '赘婿'),
    ('亲情', '亲情'), ('复仇', '复仇'), ('玄幻', '玄幻'), ('古代言情', '古代言情'), ('热血', '热血'),
    ('动作', '动作'), ('喜剧', '喜剧'), ('悬疑', '悬疑'), ('军事', '军事'), ('二次元', '二次元'),
    ('未来', '未来'), ('快速穿越', '快速穿越'), ('烧脑', '烧脑'), ('治愈', '治愈'), ('其他剧情', '其他剧情'),
]


def _pad(b):
    n = 16 - (len(b) % 16)
    return b + bytes([n]) * n


def aes_encrypt_ecb(text, key_str):
    """AES-ECB/PKCS7 -> Base64（对应 CryptoJS toString）"""
    if AES is None:
        raise RuntimeError('缺少 pycryptodome')
    key = key_str.encode('utf-8')
    c = AES.new(key, AES.MODE_ECB)
    return base64.b64encode(c.encrypt(_pad(text.encode('utf-8')))).decode()


def aes_decrypt_ecb(cipher_b64, key_str):
    if AES is None:
        raise RuntimeError('缺少 pycryptodome')
    key = key_str.encode('utf-8')
    c = AES.new(key, AES.MODE_ECB)
    out = c.decrypt(base64.b64decode(cipher_b64))
    if out and out[-1] < 16:
        out = out[:-out[-1]]
    return out.decode('utf-8', 'replace')


def _hmac_hex(data, key):
    return hmac.new(key.encode('utf-8'), data.encode('utf-8'), hashlib.sha256).hexdigest()


def b64_decode(s):
    try:
        return base64.b64decode(s).decode('utf-8', 'replace')
    except Exception:
        return ''


class Spider(_BaseSpider):
    name = '牛牛短剧'
    siteKey = 'Niuniu'

    def __init__(self):
        self._device_id = ''
        self._token = ''
        self._access_token = ''
        self._inited = False

    def init(self, extend=''):
        if self._inited:
            return ''
        self._device_id = str(uuid.uuid4()).replace('-', '')
        # ① 访客 token
        try:
            req = urllib.request.Request(_HOST + _VISITOR, headers={
                'deviceid': self._device_id, 'token': '', 'User-Agent': 'okhttp/4.12.0',
                'client': 'app', 'devicetype': 'Android', 'Content-Type': 'application/json',
            })
            with urllib.request.urlopen(req, timeout=15) as r:
                j = json.loads(r.read().decode('utf-8', 'replace'))
            self._token = (j.get('data') or {}).get('token') or ''
        except Exception:
            self._token = ''
        # ② 广告解锁 token
        try:
            t = str(int(time.time()))
            body = ('ac=wifi&os=Android&vod_version=1.10.21.6-tob&os_version=9&type=1'
                    '&clientVersion=v5.2.5&uuid=Y4WNZ3SAWK7MAJMH7CXCDHJ4VMPVFRZQTBSIA4XTYO4AWEUHIK6Q01'
                    '&resolution=1280*2618&openudid=889edced38f1069b&dt=Pixel%%204'
                    '&sha1=46121F77CE2FCAD3DBC3B9EC8A24908C1A8AD6D9&os_api=28'
                    '&install_id=1549688030634536&device_brand=google&sdk_version=1.1.3.0'
                    '&package_name=com.niuniu.ztdh.app&siteid=5627189&dev_log_aid=667431&oaid=&timestamp=%s') % t
            sig = _hmac_hex(t + _NONCE_LOGIN + body, _HMAC_KEY)
            enc = aes_encrypt_ecb(body, _ECB_KEY_LOGIN)
            req = urllib.request.Request(_LOGIN, data=enc.encode('utf-8'), headers={
                'X-Salt': _SALT_LOGIN, 'X-Nonce': _NONCE_LOGIN, 'X-Timestamp': t,
                'X-Signature': sig, 'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'okhttp/4.10.0',
            })
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read().decode('utf-8', 'replace')
            acc = json.loads(aes_decrypt_ecb(raw, _ECB_KEY_LOGIN) or '{}')
            self._access_token = ((acc.get('data') or {}).get('access_token') or '')
        except Exception:
            self._access_token = ''
        self._inited = True
        return ''

    def _ensure_init(self):
        """惰性初始化：详情/播放/搜索依赖 token，首次调用前必须完成 init"""
        if not self._inited:
            self.init()

    def _headers(self, csj=False):
        h = {
            'Cache-Control': 'no-cache',
            'Content-Type': 'application/json;charset=UTF-8',
            'User-Agent': 'okhttp/4.12.0',
        }
        if self._token:
            h['token'] = self._token
        if self._device_id:
            h['deviceid'] = self._device_id
        return h

    def _post(self, url, body, headers):
        data = json.dumps(body).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode('utf-8', 'replace'))
        except Exception:
            return {}

    def _niuniu_post(self, url1, data1, index):
        """csj-sp 短剧详情/解锁：AES-ECB + HMAC 签名"""
        t = str(int(time.time()))
        body1 = (data1.replace('&lock_free=', '&lock_free=1')
                      .replace('&timestamp=', '&timestamp=' + t)
                      .replace('&count=', '&count=1')
                      .replace('&index=', '&index=' + str(index))
                      .replace('&lock_ad=', '&lock_ad=1')
                      .replace('&lock_index=', '&lock_index=' + str(index)))
        body2 = aes_encrypt_ecb(body1, _ECB_KEY)
        sig = _hmac_hex(t + _NONCE + body1, _HMAC_KEY)
        req = urllib.request.Request(url1, data=body2.encode('utf-8'), headers={
            'X-Salt': _SALT, 'X-Nonce': _NONCE, 'X-Timestamp': t,
            'X-Access-Token': self._access_token, 'X-Signature': sig,
            'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'okhttp/4.12.0',
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read().decode('utf-8', 'replace')
            return json.loads(aes_decrypt_ecb(raw, _ECB_KEY) or '{}')
        except Exception:
            return {}

    def homeContent(self, filter):
        return {'class': [{'type_id': i, 'type_name': n} for i, n in _CLASSES]}

    def categoryContent(self, tid, pg, filter, extend):
        self._ensure_init()
        cls = str(tid or '')
        if extend and not isinstance(extend, dict):
            try:
                extend = json.loads(str(extend))
            except Exception:
                extend = None
        if isinstance(extend, dict) and extend.get('area'):
            cls = str(extend['area'])
        body = {'condition': {'typeId': 'S1', 'classify': cls}, 'pageNum': int(pg or 1), 'pageSize': 24}
        j = self._post(_HOST + _LIST, body, self._headers())
        lst = []
        for it in (j.get('data') or {}).get('records') or []:
            lst.append({
                'vod_id': str(it.get('id', '')),
                'vod_name': it.get('name') or '',
                'vod_pic': it.get('cover') or '',
                'vod_remarks': '牛牛短剧 | %s集' % (it.get('totalEpisode') or ''),
                'vod_content': it.get('description') or '',
            })
        return {'list': lst, 'page': pg, 'pagecount': int(pg or 1) + 1}

    def detailContent(self, ids):
        self._ensure_init()
        did = str(ids[0] if isinstance(ids, list) else ids)
        j1 = self._post(_HOST + _DESC, {'id': did, 'typeId': 'S1'}, self._headers())
        desc = (j1.get('data') or {}) if j1 else {}
        j2 = self._post(_HOST + _DETAIL, {'id': did, 'source': 0, 'typeId': 'S1', 'userId': '546932'}, self._headers())
        info = (j2.get('data') or {}) if j2 else {}
        eps = []
        if info.get('url') and info.get('episodeList'):
            for ep in info.get('episodeList') or []:
                eps.append('%s$%s+%s' % (ep.get('episode'), did, ep.get('id')))
        elif info.get('thirdPlayId'):
            third = info.get('thirdPlayId')
            data1 = ('not_include=0&lock_free=1&type=1&clientVersion=v5.2.5&uuid=%s&resolution=%s'
                     '&openudid=%s&dt=%s&os_api=%s&install_id=%s&sdk_version=%s&siteid=%s&dev_log_aid=%s'
                     '&oaid=%s&timestamp=%s&direction=0&ac=mobile&os=Android&vod_version=%s&os_version=%s'
                     '&count=1&index=1&shortplay_id=%s&sha1=%s&device_brand=%s&package_name=%s'
                     ) % (_DEV['uuid'], _DEV['resolution'], _DEV['openudid'], _DEV['dt'], _DEV['os_api'],
                          _DEV['install_id'], _DEV['sdk_version'], _DEV['siteid'], _DEV['dev_log_aid'],
                          _DEV['oaid'], int(time.time()), _DEV['vod_version'], _DEV['os_version'],
                          third, _DEV['sha1'], _DEV['device_brand'], _DEV['package_name'])
            try:
                h1 = self._niuniu_post(_DETAIL2, data1, 1)
                for it in (h1.get('data') or {}).get('episode_right_list') or []:
                    lock = it.get('lock_type') or 'free'
                    eps.append('第%s集$%s+%s+%s' % (it.get('index'), it.get('index'), lock, third))
            except Exception:
                pass
        vod = {
            'vod_id': did,
            'vod_name': desc.get('name') or info.get('name') or '',
            'vod_pic': desc.get('cover') or info.get('cover') or '',
            'vod_content': '类型：%s\n评分：%s\n简介：%s' % (
                desc.get('classify') or '', desc.get('score') or '', desc.get('introduce') or ''),
            'vod_remarks': '共%s集' % (desc.get('totalEpisode') or info.get('totalEpisode') or 0),
            'vod_play_from': '牛牛短剧',
            'vod_play_url': '#'.join(eps) or '暂无播放地址$0',
        }
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        self._ensure_init()
        arr = str(id).split('+')
        try:
            if len(arr) == 2:
                ep = arr[0].strip('第集')
                if not ep:
                    import re
                    m = re.search(r'\d+', arr[0])
                    ep = m.group(0) if m else '1'
                video_id = arr[1]
                j = self._post(_HOST + _DETAIL,
                               {'id': video_id, 'source': 0, 'typeId': 'S1', 'userId': '546932', 'episodeId': ep},
                               self._headers())
                if j.get('code') == 200 and (j.get('data') or {}).get('url'):
                    return {'parse': 0, 'url': j['data']['url']}
            elif len(arr) == 3:
                index, lock_type, third = arr
                data1 = ('not_include=0&lock_free=1&type=1&clientVersion=v5.2.5&uuid=%s&resolution=%s'
                         '&openudid=%s&dt=%s&os_api=%s&install_id=%s&sdk_version=%s&siteid=%s&dev_log_aid=%s'
                         '&oaid=%s&timestamp=%s&direction=0&ac=mobile&os=Android&vod_version=%s&os_version=%s'
                         '&count=1&index=1&shortplay_id=%s&sha1=%s&device_brand=%s&package_name=%s'
                         ) % (_DEV['uuid'], _DEV['resolution'], _DEV['openudid'], _DEV['dt'], _DEV['os_api'],
                              _DEV['install_id'], _DEV['sdk_version'], _DEV['siteid'], _DEV['dev_log_aid'],
                              _DEV['oaid'], int(time.time()), _DEV['vod_version'], _DEV['os_version'],
                              third, _DEV['sha1'], _DEV['device_brand'], _DEV['package_name'])
                if lock_type != 'free':
                    unlock_data = ('ac=mobile&os=Android&vod_version=1.10.21.6-tob&os_version=12'
                                   '&lock_ad=3&lock_free=3&type=1&clientVersion=v5.2.5&uuid=%s&resolution=%s'
                                   '&openudid=%s&shortplay_id=%s&dt=%s&sha1=%s&lock_index=21&os_api=%s'
                                   '&install_id=%s&device_brand=%s&sdk_version=%s&package_name=%s&siteid=%s'
                                   '&dev_log_aid=%s&oaid=%s&timestamp=%s'
                                   ) % (_DEV['uuid'], _DEV['resolution'], _DEV['openudid'], third, _DEV['dt'],
                                        _DEV['sha1'], _DEV['os_api'], _DEV['install_id'], _DEV['device_brand'],
                                        _DEV['sdk_version'], _DEV['package_name'], _DEV['siteid'],
                                        _DEV['dev_log_aid'], _DEV['oaid'], int(time.time()))
                    self._niuniu_post(_UNLOCK, unlock_data, index)
                h = self._niuniu_post(_DETAIL2, data1, index)
                lst = (h.get('data') or {}).get('list') or []
                if lst:
                    main_url = ((((lst[0].get('video_model') or {}).get('video_list') or {}).get('video_1') or {}).get('main_url') or '')
                    u = b64_decode(main_url)
                    if u:
                        return {'parse': 0, 'url': u}
        except Exception:
            pass
        return {'parse': 0, 'url': id}

    def searchContent(self, key, quick=True, pg=1):
        self._ensure_init()
        k = str(key or '').strip()
        body = {'condition': {'typeId': 'S1', 'value': k}, 'pageNum': int(pg or 1), 'pageSize': 20}
        j = self._post(_HOST + _SEARCH, body, self._headers())
        lst = []
        for it in (j.get('data') or {}).get('records') or []:
            title = str(it.get('name') or '')
            # 搜索范围：标题 或 演员 包含关键词（不匹配简介/详情）
            actor = ''
            for ak in ('actor', 'actors', 'star', 'stars', 'starring', 'performer', 'protagonist', 'actorList'):
                v = it.get(ak)
                if v:
                    actor = ' '.join(str(x) for x in v) if isinstance(v, list) else str(v)
                    break
            if k and k not in title and k not in actor:
                continue
            lst.append({
                'vod_id': str(it.get('id', '')),
                'vod_name': title,
                'vod_pic': it.get('cover') or '',
                'vod_remarks': '牛牛短剧 | %s集' % (it.get('totalEpisode') or ''),
                'vod_content': '',
            })
        return {'list': lst}

    # 兼容别名
    def quickSearch(self, key):
        return self.searchContent(key, True)

    def search(self, key):
        return self.searchContent(key, True)
