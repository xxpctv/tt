# -*- coding: utf-8 -*-
"""
围观短剧 
协议：config(RSA-2048) -> session(ECDH P-256) -> HMAC-SHA256 签名 -> 短剧 API
兼容：OK影视 / 影视仓（TVBox Python 引擎）
"""
import base64
import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider:
        pass

# ============ secp256r1 纯标准库实现（EC 密钥对 + ECDH）============
_P = 0xffffffff00000001000000000000000000000000ffffffffffffffffffffffff
_N = 0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551
_Gx = 0x6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296
_Gy = 0x4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5


def _inv(a, m=_P):
    return pow(a, -1, m)


def _add(p, q):
    if p is None:
        return q
    if q is None:
        return p
    x1, y1 = p
    x2, y2 = q
    if x1 == x2 and (y1 + y2) % _P == 0:
        return None
    if p == q:
        lam = (3 * x1 * x1 - 3) * _inv(2 * y1) % _P
    else:
        lam = (y2 - y1) * _inv(x2 - x1) % _P
    x3 = (lam * lam - x1 - x2) % _P
    return (x3, (lam * (x1 - x3) - y1) % _P)


def _mul(k, p):
    r = None
    while k:
        if k & 1:
            r = _add(r, p)
        p = _add(p, p)
        k >>= 1
    return r


# ============ RSA-2048 PKCS#1 v1.5 + X.509 DER 解析 ============
def _der_len(der, i):
    l = der[i]
    i += 1
    if l & 0x80:
        n = l & 0x7F
        l = int.from_bytes(der[i:i + n], 'big')
        i += n
    return l, i


def _parse_rsa_pub(der):
    assert der[0] == 0x30
    seq_len, i = _der_len(der, 1)
    end = i + seq_len
    while i < end:
        t = der[i]
        if t == 0x03:
            break
        l, i = _der_len(der, i + 1)
        i += l
    bs_len, i = _der_len(der, i + 1)
    i += 1
    rsa_len, i = _der_len(der, i + 1)
    rsa_end = i + rsa_len
    n_len, i = _der_len(der, i + 1)
    n = int.from_bytes(der[i:i + n_len], 'big')
    i += n_len
    e_len, i = _der_len(der, i + 1)
    e = int.from_bytes(der[i:i + e_len], 'big')
    return n, e


def _ec_pub_x509(pub):
    """EC 公钥 -> X.509 SubjectPublicKeyInfo DER（与 Java getEncoded() 一致，91 字节）"""
    x, y = pub
    point = b'\x04' + x.to_bytes(32, 'big') + y.to_bytes(32, 'big')
    alg = bytes([0x30, 0x13, 0x06, 0x07, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x02, 0x01,
                 0x06, 0x08, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x03, 0x01, 0x07])
    body = alg + b'\x03\x42\x00' + point
    return bytes([0x30, len(body)]) + body


def _rsa_pkcs1(m, n, e):
    k = (n.bit_length() + 7) // 8
    ps = b'\xff' * (k - len(m) - 3)
    em = b'\x00\x02' + ps + b'\x00' + m
    return pow(int.from_bytes(em, 'big'), e, n).to_bytes(k, 'big')


# ============ 客户端参数（与 Wgdj.smali 静态 map 一致，真实设备值）============
_BASE = 'https://api.drama.9ddm.com'
_UA = 'okhttp/5.1.0'
_ANDROID_ID = '9062f49a5a08391a'
_DEVICE_ID = 'https://api.drama.9ddm.coma' + hashlib.md5(_ANDROID_ID.encode()).hexdigest()
_REAL = {
    'version_code': '2001', 'version_name': '2.0.01',
    'channel': 'blackshark', 'device_name': 'SKW-A0', 'device_type': 'phone',
    'is_first_day': 'true', 'is_first_24h': 'true', 'app_launch_way': 'icon',
    'default_homepage': 'drama_library', 'device_owning_firm': 'blackshark',
    'screen_height': '2272', 'screen_width': '1080', 'density': '2.75',
    'av': 'v1', 'font_scale': 'default', 'os_type': '1',
}
_ORDER = ['version_code', 'version_name', 'channel', 'device_name', 'device_type',
          'is_first_day', 'is_first_24h', 'app_launch_way', 'default_homepage',
          'device_owning_firm', 'screen_height', 'screen_width', 'density',
          'av', 'font_scale', 'os_type']


def _http(url, data=None, headers=None, method=None, timeout=20):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='replace')


class Spider(_BaseSpider):
    name = '围观短剧'
    siteKey = 'Wgdj'

    def __init__(self):
        self.sid = ''
        self.hk = ''

    # ---- OK影视 会调 init(extend) ----
    def init(self, extend=''):
        return ''

    # ================= 会话（懒初始化，失败自动重试） =================
    def _ensure_session(self):
        if self.sid:
            return True
        try:
            # 1. config 拿 RSA-2048 公钥
            qs = urllib.parse.urlencode(_REAL)
            resp = json.loads(_http(
                _BASE + '/drama/config/indexV2?' + qs,
                data=json.dumps({'coldStartCount': 1, 'cpu': 'mt6893',
                                 'deviceId': _DEVICE_ID, 'hasPlayRecord': False,
                                 'memory': 11.26, 'userId': 0}).encode(),
                headers={'User-Agent': _UA, 'Content-Type': 'application/json; charset=UTF-8'}))
            cs = base64.b64decode(resp['data']['cs'])
            n, e = _parse_rsa_pub(cs)
            # 2. 本地 EC 密钥对 -> X.509 -> RSA 加密 -> session/create
            d = int.from_bytes(__import__('os').urandom(32), 'big') % (_N - 1) + 1
            pub = _mul(d, (_Gx, _Gy))
            pub_b64 = base64.b64encode(_ec_pub_x509(pub)).decode()
            enc = base64.b64encode(_rsa_pkcs1(pub_b64.encode(), n, e)).decode()
            enc_url = urllib.parse.quote(enc, safe='')
            ts = str(int(time.time() * 1000))
            nonce = hashlib.md5(ts.encode()).hexdigest().lower()
            pm = {k: _REAL[k] for k in _ORDER}
            pm['deviceId'] = _DEVICE_ID
            pm['timestamp'] = ts
            pm['nonce'] = nonce
            pm['encryptedClientPublicKey'] = enc_url
            url = _BASE + '/drama/session/create?' + '&'.join('%s=%s' % (k, v) for k, v in pm.items())
            s = json.loads(_http(url, data=b'', headers={'User-Agent': _UA}, method='POST'))
            self.sid = s['data']['sessionId']
            # 3. ECDH 共享密钥 -> HMAC key（X 坐标 32B 的 Base64）
            pt = base64.b64decode(s['data']['serverEphemeralPublicKey'])
            xi = pt.find(b'\x04')
            x = int.from_bytes(pt[xi + 1:xi + 33], 'big')
            y = int.from_bytes(pt[xi + 33:xi + 65], 'big')
            sh = _mul(d, (x, y))
            self.hk = base64.b64encode(sh[0].to_bytes(32, 'big')).decode()
            return True
        except Exception:
            self.sid = ''
            return False

    def _sign(self, pm, t, nn):
        s = ''.join(k + str(pm[k]) for k in sorted(pm.keys())) + t + nn
        return hmac.new(self.hk.encode(), s.encode(), hashlib.sha256).hexdigest().lower()

    def _get(self, path, biz=None):
        if not self._ensure_session():
            return {}
        t2 = str(int(time.time() * 1000))
        nn2 = hashlib.md5(t2.encode()).hexdigest().lower()
        full = dict(_REAL)
        if biz:
            full.update(biz)
        sig = self._sign(full, t2, nn2)
        h = {'User-Agent': _UA, 'x-session-id': self.sid, 'x-sign': sig,
             'x-timestamp': t2, 'x-nonce': nn2}
        url = _BASE + path + '?' + urllib.parse.urlencode(full)
        try:
            return json.loads(_http(url, headers=h))
        except Exception:
            return {}

    def _post(self, path, biz):
        if not self._ensure_session():
            return {}
        t2 = str(int(time.time() * 1000))
        nn2 = hashlib.md5(t2.encode()).hexdigest().lower()
        full = dict(_REAL)
        for _k, _v in biz.items():
            if isinstance(_v, (list, dict)):
                full[_k] = json.dumps(_v, ensure_ascii=False)
            else:
                full[_k] = _v
        sig = self._sign(full, t2, nn2)
        h = {'User-Agent': _UA, 'x-session-id': self.sid, 'x-sign': sig,
             'x-timestamp': t2, 'x-nonce': nn2, 'Content-Type': 'application/json'}
        url = _BASE + path + '?' + urllib.parse.urlencode(full)
        try:
            return json.loads(_http(url, data=json.dumps(biz).encode(), headers=h, method='POST'))
        except Exception:
            return {}

    # ================= 首页（对齐原版：class=shortPlayTypes 顶部 tab + 全维度 filter；过滤项名中文） =================
    def homeContent(self, filter):
        o = self._get('/drama/home/shortVideoTags')
        spt = o.get('shortPlayTypes') or ['真人剧', 'AI剧', '漫剧']
        cls = [{'type_id': t, 'type_name': t} for t in spt]

        def _flt(key, name, vals):
            return {'key': key, 'name': name,
                    'value': [{'n': '全部', 'v': ''}] +
                             [{'n': str(v), 'v': str(v)} for v in (vals or [])]}

        f = {}
        for c in cls:
            f[c['type_id']] = [
                _flt('audiences', '受众', o.get('audiences') or ['男频', '女频']),
                _flt('episodeCounts', '集数', o.get('episodeCounts') or ['1-30集', '30集以上', '60集以上', '90集以上']),
                _flt('orders', '排序', o.get('orders') or ['最热', '最新', '首发', '最多收藏', '7天内上新']),
                _flt('ages', '年代', o.get('ages') or ['00后', '90后', '80后', '70后', '60后']),
                _flt('tags', '题材', o.get('tags') or ['逆袭', '都市']),
            ]
        lst = []
        try:
            o2 = self._post('/drama/home/searchV2',
                            {'page': '1', 'pageSize': '20', 'audience': '全部', 'order': '最新'})
            lst = self._parse_list(o2)
        except Exception:
            lst = []
        return {'class': cls, 'filters': f, 'list': lst}

    
    # ================= 分类列表（tid=shortPlayType 序号；filter 组合查询，audiences→audience 对齐原版参数） =================
    def categoryContent(self, tid, pg, filter, extend):
        # OK影视/影视仓 标准签名：filter 是布尔开关，筛选值在 extend（OK影视 传 JSON 字符串）
        if extend and not isinstance(extend, dict):
            try:
                extend = json.loads(str(extend))
            except Exception:
                extend = None
        # 原版 body 结构（Wgdj smali categoryContent 全量解密）：
        # page=parseInt(pg) pageSize=30 shortPlayType=tid(中文名)
        # audience=extend.audiences(默认全部) order=extend.orders(默认最新)
        # searchWord=extend.searchWord(默认'') subject=extend.tags(默认全部)
        # sessionHistory=[]  age=extend.ages(仅 extend 含 ages 时)
        body = {
            'audience': '全部',
            'order': '最新',
            'page': str(pg),
            'pageSize': '30',
            'shortPlayType': str(tid),
            'searchWord': '',
            'subject': '全部',
            'sessionHistory': [],
        }
        if extend and isinstance(extend, dict):
            for k, v in extend.items():
                if not v:
                    continue
                k = str(k)
                if k == 'audiences':
                    body['audience'] = str(v)
                elif k == 'orders':
                    body['order'] = str(v)
                elif k == 'tags':
                    body['subject'] = str(v)
                elif k == 'ages':
                    body['age'] = str(v)      # 服务端无响应，但原版如此
                elif k == 'episodeCounts':
                    continue                   # 原版不传该参数（服务端无响应）
                elif k == 'searchWord':
                    body['searchWord'] = str(v)
                else:
                    body[k] = str(v)
        o = self._post('/drama/home/searchV2', body)
        return {'list': self._parse_list(o)}

    def searchContent(self, key, quick=True, pg=1):
        body = {'searchWord': key, 'page': str(pg), 'pageSize': '30'}
        o = self._post('/drama/home/searchV2', body)
        # 标题过滤：服务端为 标题+简介+标签 模糊搜索，只保留标题含关键词
        return {'list': [v for v in self._parse_list(o)
                         if not key or (key in (v.get('vod_name') or ''))]}

    def _parse_list(self, o):
        out = []
        data = o.get('data') or []
        if not isinstance(data, list):
            return out
        for it in data:
            vid = str(it.get('oneId') or it.get('id') or '')
            if not vid:
                continue
            out.append({
                'vod_id': vid,
                'vod_name': it.get('title') or '',
                'vod_pic': it.get('vertPoster') or it.get('horzPoster') or '',
                'vod_remarks': (it.get('episodeCount') and ('%s集' % it.get('episodeCount'))) or '',
                'vod_content': it.get('description') or '',
            })
        return out

    # ================= 详情（多清晰度多线路） =================
    def detailContent(self, ids):
        vid = str(ids[0]) if ids else ''
        if not vid:
            return {'list': []}
        o = self._get('/drama/home/shortVideoDetail',
                      {'oneId': vid, 'page': '2', 'pageSize': '50',
                       'userId': '0', 'queryAll': 'true'})
        eps = o.get('data') or []
        if not isinstance(eps, list) or not eps:
            return {'list': [{'vod_id': vid, 'vod_name': vid}]}
        # 清晰度列表取第一集（videoClarityList 每个含 name/url）
        ep0 = eps[0]
        clarity = [v.get('name') or '默认' for v in (ep0.get('videoClarityList') or [])] or ['默认']
        # 每集按清晰度收集 url（缺档则用该集最高可用）
        urls_by_clarity = {c: [] for c in clarity}
        for ep in eps:
            vcl = ep.get('videoClarityList') or []
            by_name = {v.get('name'): v.get('url') for v in vcl}
            for c in clarity:
                u = by_name.get(c) or (vcl[0].get('url') if vcl else '')
                urls_by_clarity[c].append(u)
        # 集数标题：第X集（接口 ep.title 是剧名，不能用）
        ep_titles = []
        for i in range(len(eps)):
            ep_titles.append('第%s集' % (i + 1))
        play_from = '$$$'.join(clarity)
        play_url = '$$$'.join(
            '#'.join('%s$%s' % (ep_titles[i], urls_by_clarity[c][i]) for i in range(len(eps)))
            for c in clarity
        )
        tag = o.get('shortPlayTag') or ep0.get('shortPlayTag') or ''
        if isinstance(tag, list):
            tag = '/'.join(str(t) for t in tag)
        vod = {
            'vod_id': vid,
            'vod_name': o.get('title') or ep0.get('title') or vid,
            'vod_pic': o.get('vertPoster') or ep0.get('vertPoster') or '',
            'type_name': tag or '',
            'vod_content': o.get('description') or '',
            'vod_play_from': play_from,
            'vod_play_url': play_url,
        }
        return {'list': [vod]}

    # ================= 播放（id 已是带签名直链） =================
    def playerContent(self, flag, id, vipFlags):
        return {'parse': 0, 'playUrl': id,
                'header': {'User-Agent': 'okhttp/5.1.0'}}


class WgdjAmns(Spider):
    """OK影视 api=csp_WgdjAmns 别名类（继承 Wgdj 全部逻辑）"""
    pass


def main():
    s = Spider()
    s.init()
    s._ensure_session()
    print('session:', (s.sid[:20] + '...') if s.sid else '(空)')
    if s.sid:
        print(json.dumps(s.homeContent(False), ensure_ascii=False)[:200])
        print(json.dumps(s.categoryContent('逆袭', '1', None, None), ensure_ascii=False)[:300])
        print(json.dumps(s.detailContent(['110000070549386775']), ensure_ascii=False)[:300])


if __name__ == '__main__':
    main()
