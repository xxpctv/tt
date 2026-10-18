#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TVBox Python Spider - 橘汁视频 (独立源)
从「红果短剧.py」拆出的橘汁线路, 独立成一个点播源。

能力:
  - 分类: 动漫 / 短剧 / 漫剧 (橘汁官网真实分类)
  - 详情: 多线路 (一部剧常有十几路蓝光, 自动按线路分组, 全集线路排前)
  - 搜索: 关键词不拆分; 只匹配【标题/剧名】(剔除只命中简介/详情的结果)
  - 播放: 实时签名换链 (换链URL带 token 有时效, 故播放时才换);
          换链失败自动重新登录再试一次。

依赖: pycryptodome (Crypto)  ——  纯标准库无法完成 RSA/AES 签名。
"""

import base64
import json
import random
import re
import ssl
import string
import sys
import time
import urllib.parse
import urllib.request

try:
    if '..' not in sys.path:
        sys.path.append('..')
    from base.spider import Spider as _BaseSpider
except Exception:
    _BaseSpider = object

from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5, AES
from Crypto.Util.Padding import pad

# ==================== 常量 ====================
HOST = 'https://juziapp.hzhcbkj.cn'
UA = 'okhttp/3.12.1'
VC = '3024'
PKG = 'com.mxj.wylcjbxyx'
_NATIVE_K = b'ed5fdsgucxumegqa'
_SAFE = b'OC1A06E197EF10CF3F6058CA7A803B5E'
_SAFECODE = 'OW1WBLFZCLJ0WTNJQMRSZ2DYSGNBPT0='
_RSA2_N = bytes.fromhex(
    'a9f44938c0895002dc059ee05196c162a30dadafee1439c88678d29b63b9cbef'
    '87ad52a51be9fbe939238784511f69695fc14a4e075ef1dc910bdcda35f677e3'
    '09e558ad83e3949720a2a5161ffb5f21f140416bedc4120194a6b3921c3c7770'
    'a1cac5a679646290aaa406c551638a2a34fba3e2c8e6e99ba5b74538238a6b45')
UDID = 'ABEB9828C0CBCBB9'
USER = 'tv_abeb9828c0'
PASS = 'da06655827ef97e37c38f33d2ab1'

# 分类: (type_id, 名称); 真实 typeId 23动漫/24短剧/26漫剧
CATS = [('23', '动漫'), ('24', '短剧'), ('26', '漫剧')]

# 播放时只会返回网页(非媒体)、需要外部解析的源 -> 排序降权到最后
_WEB_SRC = ('qq', 'youku', 'mgtv', 'bilibili', 'iqiyi', 'letv', 'sohu')

# 实测可直接通过 videoUsableUrl 换出真实 m3u8 的自建/搬运源 (优先展示)
_SRC_GOOD = {
    'zijianm3u8', 'qsvip', 'qingshan', 'vod_1080', 'PAN1', 'zy1080_01',
    'shvip', 'newxfyun', 'pylg', 'KZNB', 'JD4K', 'bfzym3u8',
}
# 部分可换链 (随剧/时间不同)
_SRC_MID = {'fym3u8'}
# 注意: 'IMDB' 是橘汁私有加密源, 换链接口只回显加密ID, 第三方无法解析 -> 殿后

_MEDIA_RE = re.compile(
    r'(?i).*\.(m3u8|mp4|flv|mkv|ts|mov|mpd)(\?.*)?$')

# ==================== 全局状态 ====================
_token = '4bbbca33e1ac443009d2f1422d4edc9e'
try:
    _rsa2 = RSA.construct((int.from_bytes(_RSA2_N, 'big'), 65537))
except Exception:
    _rsa2 = None


# ==================== protobuf 编解码 ====================
def _varint(n):
    b = b''
    while True:
        x = n & 0x7f
        n >>= 7
        if n:
            b += bytes([x | 0x80])
        else:
            return b + bytes([x])


def _f(num, wire, payload):
    t = _varint((num << 3) | wire)
    if wire == 2:
        return t + _varint(len(payload)) + payload
    return t + payload


def _pb(buf):
    out = []
    i = 0
    n = len(buf)
    while i < n:
        b = buf[i]
        fn, wt = b >> 3, b & 7
        i += 1
        if wt == 0:
            v = 0
            sh = 0
            while i < n:
                x = buf[i]
                i += 1
                v |= (x & 0x7f) << sh
                sh += 7
                if not x & 0x80:
                    break
            out.append((fn, wt, v))
        elif wt == 2:
            ln = 0
            sh = 0
            while i < n:
                x = buf[i]
                i += 1
                ln |= (x & 0x7f) << sh
                sh += 7
                if not x & 0x80:
                    break
            out.append((fn, wt, buf[i:i + ln]))
            i += ln
        elif wt == 5:
            out.append((fn, wt, buf[i:i + 4]))
            i += 4
        elif wt == 1:
            out.append((fn, wt, buf[i:i + 8]))
            i += 8
        else:
            i += 1
    return out


def _rnd(k):
    ch = string.ascii_letters + string.digits
    return ''.join(random.sample(list(ch), k - 1)) + '='


def _http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    ctx = ssl._create_unverified_context()
    return urllib.request.urlopen(req, timeout=20, context=ctx).read()


# ==================== 签名 / 登录 ====================
def _login():
    global _token
    try:
        body = json.dumps({'username': USER, 'password': PASS,
                           'udid': UDID}).encode()
        try:
            _http(HOST + '/api/ex/v3/user/register', body, {
                'User-Agent': UA, 'Content-Type': 'application/json'})
        except Exception:
            pass
        d = _http(HOST + '/api/ex/v3/user/login', body, {
            'User-Agent': UA, 'Content-Type': 'application/json'})
        data = json.loads(d).get('data') or {}
        _token = (data.get('token') or
                  (data.get('user') or {}).get('token') or '')
    except Exception:
        _token = ''


def _hdr():
    ts = int(time.time() * 1000)
    rnd = _rnd(16)
    if _rsa2 is not None:
        sig = base64.b64encode(PKCS1_v1_5.new(_rsa2).encrypt(
            (str(ts) + rnd + VC).encode())).decode()
    else:
        sig = ''
    ao = base64.b64encode(AES.new(_SAFE, AES.MODE_ECB).encrypt(
        pad((str(ts) + rnd).encode(), 16))).decode()
    J = {'country': 'CN', 'vName': '3.0.2.4', 'cpuId': '', 'young': 0,
         'facturer': 'OnePlus', 'pkg': PKG, 'uuid': UDID,
         'resolution': '1080x2256', 'mac': '02%3A00%3A00%3A00%3A00%3A00',
         'sig': sig, 'abid': '7470', 'model': 'PJX110', 'plat': 'android',
         'udid': UDID, 'dpi': '480', 'net': '1', 'lang': 'zh',
         'random_str': rnd, 'brand': 'OnePlus', 'timestamp': ts,
         'density': '3.0', 'appName': '%E6%A9%98%E6%B1%81',
         'cpu': 'arm64-v8a', 'chid': '10000', 'carrier': '%E8%81%94%E9%80%9A',
         'sig2': ao[:8], 'v': 1, 'sig3': ao[8:], 'tenantId': '*',
         '_vOsCode': '36', 'vOs': '16', 'vApp': VC, 'device': 0,
         'androidID': UDID}
    blob = json.dumps(J, separators=(',', ':'), ensure_ascii=False).encode()
    pd_hex = AES.new(_NATIVE_K, AES.MODE_CBC, _NATIVE_K).encrypt(
        pad(blob, 16)).hex()
    h = {'User-Agent': UA, 'Accept': 'application/x-protobuf',
         'Cache-Control': 'no-cache',
         'publicParams': json.dumps({'paramsData': pd_hex},
                                    separators=(',', ':'))}
    if _token:
        h['token'] = _token
    return h


def _secure(mapkv):
    ts = int(time.time() * 1000)
    rnd8 = _rnd(8)
    plain = (mapkv + str(ts)).encode()
    ct = AES.new(_SAFECODE.encode(), AES.MODE_ECB).encrypt(
        pad(plain, 16))
    b64 = base64.b64encode(ct).decode()
    return (_f(1, 2, (rnd8 + b64[:12]).encode()) +
            _f(2, 2, b64[12:].encode()) +
            _f(3, 2, _rnd(20).encode()) +
            _f(4, 0, _varint(ts)) +
            _f(5, 2, rnd8.encode()))


# ==================== 列表 / 搜索 ====================
def _proto_post(path, qs):
    hh = _hdr()
    hh['Content-Type'] = 'application/x-protobuf'
    hh['Accept'] = 'application/x-protobuf'
    return _http(HOST + path, _secure(qs), hh)


def _pic_from(v):
    cands = [x.decode('utf-8', 'replace')
             for _, w, x in _pb(v)
             if w == 2 and x.startswith(b'http')]
    if not cands:
        return ''
    return next((u for u in cands if u.startswith('https')), cands[0])


def category_list(tid, page):
    """分类列表 -> [卡片] (vod_id 为纯数字)"""
    out = []
    try:
        qs = 'page=%d&pagesize=24&typeId1=%s' % (page, tid)
        d = _proto_post('/api/proto/v5/drama/category', qs)
        top = _pb(d)
        code = [v for fn, wt, v in top if fn == 1 and wt == 0]
        if (code[0] if code else 0) != 200:
            return out
        data = [v for fn, wt, v in top if fn == 3 and wt == 2][0]
        for fn, wt, v in _pb(data):
            if fn != 1 or wt != 2:
                continue
            info = {'vod_id': '', 'vod_name': '', 'vod_pic': '', 'vod_remarks': ''}
            for f2, w2, v2 in _pb(v):
                if f2 == 3 and w2 == 0:
                    info['vod_id'] = str(v2)
                elif f2 == 5 and w2 == 2:
                    info['vod_name'] = v2.decode('utf-8', 'replace')
                elif f2 == 2 and w2 == 2:
                    info['vod_pic'] = _pic_from(v2)
                elif f2 == 13 and w2 == 2:
                    info['vod_remarks'] = v2.decode('utf-8', 'replace')
            if info['vod_id'] and info['vod_name']:
                out.append(info)
    except Exception:
        pass
    return out


def search(key, page):
    """搜索 -> [卡片] (vod_id 纯数字)"""
    out = []
    try:
        qs = 'page=%s&pagesize=24&searchKeys=%s' % (page or 1, key)
        d = _proto_post('/api/proto/v5/drama/search', qs)
        top = _pb(d)
        code = [v for fn, wt, v in top if fn == 1 and wt == 0]
        if (code[0] if code else 0) != 200:
            return out
        datas = [v for fn, wt, v in top if fn == 3 and wt == 2]
        if not datas:
            return out
        for fn, wt, v in _pb(datas[0]):
            if wt != 2 or fn == 0 or fn > 100:
                continue
            info = {'vod_id': '', 'vod_name': '', 'vod_pic': '', 'vod_remarks': ''}
            for f3_, w3_, v3_ in _pb(v):
                if w3_ != 2 and not (f3_ == 3 and w3_ == 0):
                    continue
                if f3_ == 3 and w3_ == 0:
                    info['vod_id'] = str(v3_)
                elif f3_ == 5 and w3_ == 2:
                    info['vod_name'] = v3_.decode('utf-8', 'replace')
                elif f3_ == 2 and w3_ == 2:
                    info['vod_pic'] = _pic_from(v3_)
                elif f3_ == 13 and w3_ == 2:
                    info['vod_remarks'] = v3_.decode('utf-8', 'replace')
            if info['vod_id'] and info['vod_name']:
                out.append(info)
    except Exception:
        pass
    return out


# ==================== 详情 (多线路) ====================
def vod_detail(vid):
    """详情 -> dict; 选集按线路(f10, 否则 f9)分组, 全集线路排前。"""
    res = {'vod_id': str(vid), 'vod_name': '', 'vod_pic': '',
           'vod_content': '', 'vod_actor': '', 'vod_area': '',
           'order': [], 'lines': {}}
    try:
        d = _proto_post('/api/proto/v5/drama/getDetail', 'id=' + str(vid))
        top = _pb(d)
        data = [v for fn, wt, v in top if fn == 3 and wt == 2][0]
        dd = _pb(data)
        for fn, wt, v in dd:
            if fn == 0 or fn > 100:
                break
            if fn == 9 and wt == 2 and not res['vod_name']:
                res['vod_name'] = v.decode('utf-8', 'replace')
            elif fn == 1 and wt == 2 and not res['vod_area']:
                res['vod_area'] = v.decode('utf-8', 'replace')
            elif fn == 16 and wt == 2 and not res['vod_actor']:
                res['vod_actor'] = v.decode('utf-8', 'replace').lstrip(' ,')
            elif fn == 25 and wt == 2 and not res['vod_actor']:
                res['vod_actor'] = v.decode('utf-8', 'replace')
            elif fn == 6 and wt == 2 and not res['vod_content']:
                res['vod_content'] = re.sub(
                    r'<[^>]+>', '', v.decode('utf-8', 'replace'))
            elif fn == 2 and wt == 2 and not res['vod_pic']:
                res['vod_pic'] = _pic_from(v)
        # 扫描选集 (0xEA01), 按线路分组
        n = len(data)
        pos = 0
        lines = {}
        while True:
            j = data.find(b'\xea\x01', pos)
            if j < 0:
                break
            k = j + 2
            ln = 0
            sh = 0
            while k < n and data[k] & 0x80:
                ln |= (data[k] & 0x7f) << sh
                sh += 7
                k += 1
            ln |= (data[k] & 0x7f) << sh
            k += 1
            if ln <= 0 or k + ln > n:
                pos = j + 1
                continue
            entry = data[k:k + ln]
            pos = k + ln
            title = pth = src = line = ''
            for f3_, w3_, v3_ in _pb(entry):
                if w3_ != 2:
                    continue
                if f3_ in (2, 3):
                    title = v3_.decode('utf-8', 'replace')
                elif f3_ == 4:
                    pth = v3_.decode('utf-8', 'replace')
                elif f3_ == 9:
                    src = v3_.decode('utf-8', 'replace')
                elif f3_ == 10:
                    line = v3_.decode('utf-8', 'replace')
            if not pth:
                continue
            mm = re.match(r'^第?0*(\d{1,4})[集话期](?:完结)?$', title)
            if mm:
                title = mm.group(1)
            line = line or src or '正片'
            # 播放参数: 直链媒体直接用; 加密ID走 base64(换链)
            if _MEDIA_RE.match(pth):
                ep_arg = pth
            else:
                ep_arg = base64.b64encode(json.dumps(
                    {'vodPlayFrom': src, 'playUrl': pth},
                    separators=(',', ':')).encode()).decode()
            lines.setdefault(line, {'src': src, 'items': []})
            lines[line]['items'].append(
                '%s$%s' % (title or '正片', ep_arg))
        # 线路排序: 可换链源(自建/搬运)优先, 部分可换链次之, 私有/网页源殿后;
        # 同档内集数多者优先, 再按线路名
        def _grp(src):
            if src in _SRC_GOOD:
                return 0
            if src in _SRC_MID:
                return 1
            return 2

        def lk(nm):
            src = lines[nm]['src']
            return (_grp(src), -len(lines[nm]['items']), nm)
        order = sorted(lines.keys(), key=lk)
        res['order'] = order
        res['lines'] = lines
    except Exception:
        pass
    return res


# ==================== Spider ====================
class Spider(_BaseSpider):
    def getName(self):
        return "橘汁视频"

    def init(self, cfg=""):
        pass

    def getDependence(self):
        return []

    def download(self, path, url):
        try:
            urllib.request.urlretrieve(url, path)
        except Exception:
            pass

    @staticmethod
    def _title_hit(key, name):
        """完整关键词命中【标题/剧名】才算; 不拆分。
        橘汁是剧名精确搜索, 服务端已按标题召回, 这里再做一次完整词包含校验。"""
        key = (key or "").strip()
        if not key:
            return True
        return key in (name or "")

    # ---------- 首页 ----------
    def homeContent(self, filter=True):
        classes = [{"type_name": nm, "type_id": tid} for tid, nm in CATS]
        return {"class": classes, "filters": {}, "list": []}

    def homeVideoContent(self):
        try:
            return {"list": category_list('24', 1)}
        except Exception:
            return {"list": []}

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg=1, filter=1, extend=None):
        try:
            page = int(pg)
        except (TypeError, ValueError):
            page = 1
        result = {"list": [], "page": page, "pagecount": page,
                  "limit": 24, "total": 0}
        try:
            items = category_list(str(tid), page)
            if items:
                result["list"] = items
                result["total"] = (page - 1) * 24 + len(items)
                result["pagecount"] = page + 1 if len(items) >= 24 else page
        except Exception:
            pass
        return result

    # ---------- 详情 ----------
    def detailContent(self, ids):
        result = {"list": []}
        try:
            ids_list = ids if isinstance(ids, list) else [ids]
            vid = str(ids_list[0]) if ids_list else ""
            if not vid:
                return result
            r = vod_detail(vid)
            order = r["order"]
            lines = r["lines"]
            if order:
                play_from = '$$$'.join(order)
                play_url = '$$$'.join('#'.join(lines[ln]['items'])
                                      for ln in order)
            else:
                play_from = '橘汁'
                play_url = '暂无片源$http://'
            detail = {
                "vod_id": r["vod_id"],
                "vod_name": r["vod_name"],
                "vod_pic": r["vod_pic"],
                "vod_content": r["vod_content"],
                "vod_remarks": "",
                "vod_year": "",
                "vod_area": r["vod_area"],
                "vod_actor": r["vod_actor"],
                "vod_tag": "",
                "vod_play_from": play_from,
                "vod_play_url": play_url,
            }
            result["list"] = [detail]
        except Exception:
            pass
        return result

    # ---------- 搜索 ----------
    def searchContent(self, key, quick=False, pg=1):
        try:
            page = int(pg)
        except (TypeError, ValueError):
            page = 1
        try:
            items = search(key, page)
            # 不拆词: 只保留完整关键词命中标题/剧名的结果
            items = [v for v in items if self._title_hit(key, v.get("vod_name"))]
            return {"list": items, "page": page, "pagecount": page + 1}
        except Exception:
            return {"list": []}

    # ---------- 播放 ----------
    def _do_play(self, pf, pu):
        try:
            hh = _hdr()
            hh['Content-Type'] = 'application/x-protobuf'
            hh['Accept'] = 'application/x-protobuf'
            qs = 'vodPlayFrom=%s&playUrl=%s' % (
                urllib.parse.quote(pf), urllib.parse.quote(pu, safe=''))
            d = _http(HOST + '/api/proto/v5/videoUsableUrl',
                      _secure(qs), hh)
            top = _pb(d)
            code = [v for fn, wt, v in top if fn == 1 and wt == 0]
            if (code[0] if code else 0) != 200:
                return ''
            data = [v for fn, wt, v in top if fn == 3 and wt == 2]
            if not data:
                return ''
            mm = re.search(rb'https?://[\x21-\x7e]+', data[0])
            if not mm:
                return ''
            url = mm.group(0).decode('utf-8', 'replace')
            # 必须是媒体直链 (换链有时只回显加密ID或给网页)
            if _MEDIA_RE.match(url):
                return url
            # 部分CDN m3u8无扩展名但路径含 /hls/ /video/: 放行 m3u8 形态
            if re.search(r'/(hls|m3u8|video|tos|play)/', url, re.I) and \
                    not url.endswith(('.html', '.shtml')):
                return url
            return ''
        except Exception:
            return ''

    def playerContent(self, flag, id, vipFlags=None):
        result = {
            "parse": 0,
            "playUrl": "",
            "url": "",
            "header": json.dumps({"User-Agent": UA}, ensure_ascii=False),
        }
        try:
            raw = str(id).split("#")[0]
            # 直链媒体: 直接播放
            if raw.startswith("http") and _MEDIA_RE.match(raw):
                result["url"] = raw
                return result
            # 加密ID: base64 JSON, 实时换链
            jm = json.loads(base64.b64decode(raw))
            pf = jm.get("vodPlayFrom", "")
            pu = jm.get("playUrl", "")
            if not pf or not pu:
                return result
            url = self._do_play(pf, pu)
            if not url:
                # token 可能过期: 重新登录后再换一次
                _login()
                url = self._do_play(pf, pu)
            if url:
                result["url"] = url
        except Exception:
            pass
        return result

    # ---------- get 别名 ----------
    def getHomeContent(self, filter=True):
        return self.homeContent(filter)

    def getHomeVideoContent(self):
        return self.homeVideoContent()

    def getCategoryContent(self, tid, pg=1, filter=1, extend=None):
        return self.categoryContent(tid, pg, filter, extend)

    def getDetailContent(self, array):
        return self.detailContent(array)

    def getSearchContent(self, key, quick=False, pg=1):
        return self.searchContent(key, quick, pg)

    def getPlayerContent(self, flag, id, vipFlags=None):
        return self.playerContent(flag, id, vipFlags)
