# -*- coding: utf-8 -*-
# 剧下饭直播 TVBox Python 爬虫 - 独立直播源
# 从 剧下饭4K.py 提取隐藏直播分类(22023) 独立成站：
#   分类: GET  /api/v1/video/liveVideo          -> 直播分组列表
#   详情: POST /api/v1/video/videoDetails       -> 频道线路/集
#   播放: POST /api/v1/player/analysisUrl       -> sourceCode+playerCode 解析秒播地址
# 鉴权: timestamp + 排序拼接 + datasign(AES-256-ECB 加密) 签名
# 站点: http://manian.juxiafan.com/ (内置 8 个备用域名自动轮换)

from __future__ import annotations

import json
import time
from base64 import b64encode
from urllib.request import Request, urlopen
from urllib.parse import quote_plus

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    _BaseSpider = object

BASE_URLS = [
    "http://manian.juxiafan.com",
    "http://195.225.24.128:6213",
    "http://jugaoqing.com",
    "http://jumianfei.com",
    "http://juyongjiu.com",
    "http://kuailezhuiju2.com",
    "http://zhuiju666.com",
    "http://194.147.100.155:7744",
]
AES_KEY = b"kZ6fT8oF6oM8eX6lF7eH2rJ3pW7gW0kC"
UA = "okhttp/4.12.0"

LIVE_TYPE_ID = 22023                 # 直播分类(服务端不下发, 手动补进分类栏)

# ======================= AES-256-ECB =======================

def _build_sbox():
    sbox = [0] * 256
    p = q = 1
    while True:
        p = p ^ ((p << 1) ^ (0x1B if p & 0x80 else 0)) & 0xFF
        q ^= q << 1
        q ^= q << 2
        q ^= q << 4
        q ^= 0x09 if (q & 0x80) else 0
        q &= 0xFF
        xformed = q ^ ((q << 1) | (q >> 7)) & 0xFF
        xformed = (xformed ^ ((q << 2) | (q >> 6))) & 0xFF
        xformed = (xformed ^ ((q << 3) | (q >> 5))) & 0xFF
        xformed = (xformed ^ ((q << 4) | (q >> 4))) & 0xFF
        sbox[p] = xformed ^ 0x63
        if p == 1:
            break
    sbox[0] = 0x63
    return sbox

_SBOX = _build_sbox()
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36, 0x6C, 0xD8, 0xAB, 0x4D]

def _xtime(a):
    return ((a << 1) ^ (0x1B if a & 0x80 else 0)) & 0xFF

_COL2 = [_xtime(i) for i in range(256)]
_COL3 = [_xtime(i) ^ i for i in range(256)]

def _expand_key(key):
    nk = len(key) // 4
    nr = nk + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        temp = list(w[i - 1])
        if i % nk == 0:
            temp = temp[1:] + temp[:1]
            temp = [_SBOX[b] for b in temp]
            temp[0] ^= _RCON[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            temp = [_SBOX[b] for b in temp]
        w.append([w[i - nk][j] ^ temp[j] for j in range(4)])
    return w, nr

def _encrypt_block(block, w, nr):
    def _rk(r):
        return [x for word in w[r * 4:(r * 4) + 4] for x in word]
    s = list(block)
    rk0 = _rk(0)
    for j in range(16):
        s[j] ^= rk0[j]
    for r in range(1, nr):
        s = [_SBOX[b] for b in s]
        s = [s[0], s[5], s[10], s[15],
             s[4], s[9], s[14], s[3],
             s[8], s[13], s[2], s[7],
             s[12], s[1], s[6], s[11]]
        t = [0] * 16
        for c in range(4):
            i = c * 4
            a0, a1, a2, a3 = s[i], s[i + 1], s[i + 2], s[i + 3]
            t[i] = _COL2[a0] ^ _COL3[a1] ^ a2 ^ a3
            t[i + 1] = a0 ^ _COL2[a1] ^ _COL3[a2] ^ a3
            t[i + 2] = a0 ^ a1 ^ _COL2[a2] ^ _COL3[a3]
            t[i + 3] = _COL3[a0] ^ a1 ^ a2 ^ _COL2[a3]
        s = t
        rk = _rk(r)
        s = [s[j] ^ rk[j] for j in range(16)]
    s = [_SBOX[b] for b in s]
    s = [s[0], s[5], s[10], s[15],
         s[4], s[9], s[14], s[3],
         s[8], s[13], s[2], s[7],
         s[12], s[1], s[6], s[11]]
    rk = _rk(nr)
    s = [s[j] ^ rk[j] for j in range(16)]
    return bytes(s)

def _aes256_ecb_encrypt(plain, key):
    w, nr = _expand_key(key)
    out = bytearray()
    for i in range(0, len(plain), 16):
        out += _encrypt_block(bytes(plain[i:i + 16]), w, nr)
    return bytes(out)

def _aes_encrypt(plaintext, key=AES_KEY):
    """PKCS7 填充 + AES-256-ECB -> base64 (多后端, 输出一致)"""
    data = plaintext.encode("utf-8") if isinstance(plaintext, str) else plaintext
    pad = 16 - len(data) % 16
    data = data + bytes([pad]) * pad
    try:
        from Crypto.Cipher import AES
        return b64encode(AES.new(key, AES.MODE_ECB).encrypt(data)).decode()
    except Exception:
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher as _C
            from cryptography.hazmat.primitives.ciphers.algorithms import AES as _AES
            from cryptography.hazmat.primitives.ciphers.modes import ECB as _ECB
            from cryptography.hazmat.backends import default_backend as _B
            enc = _C(_AES(key), _ECB(), backend=_B()).encryptor()
            return b64encode(enc.update(data) + enc.finalize()).decode()
        except Exception:
            return b64encode(_aes256_ecb_encrypt(data, key)).decode()

# ======================= HTTP / 签名 =======================

def _http(method, url, body=None, content_type=None, timeout=12):
    headers = {"User-Agent": UA}
    data = None
    if body is not None:
        data = body.encode("utf-8") if isinstance(body, str) else body
        headers["Content-Length"] = str(len(data))
    if content_type:
        headers["Content-Type"] = content_type
    req = Request(url, data=data, headers=headers, method=method)
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")

def _sign(concat):
    return _aes_encrypt(concat)

def _fix_host(host):
    if host is None or (isinstance(host, str) and host.strip() == ""):
        host = BASE_URLS[0]
    return str(host).rstrip("/")

def _post(host, path, body=None, content_type=None):
    urls = []
    h = _fix_host(host)
    if h not in urls:
        urls.append(h)
    for b in BASE_URLS:
        if b not in urls:
            urls.append(b)
    last = "{}"
    for u in urls:
        try:
            last = _http("POST", u + path, body, content_type)
            if '"code"' in last:
                return last
        except Exception:
            continue
    return last

def _get(url, timeout=12):
    try:
        return _http("GET", url, timeout=timeout)
    except Exception:
        return "{}"

def _post_form(host, path, params):
    ts = str(int(time.time()))
    params["timestamp"] = ts
    items = sorted(params.items())
    concat = "&".join(k + "=" + quote_plus(str(v)) for k, v in items)
    ds = _sign(concat)
    form = "&".join(k + "=" + quote_plus(str(v)) for k, v in items)
    form += "&datasign=" + quote_plus(ds)
    return _post(host, path, form, "application/x-www-form-urlencoded")

# ======================= 直播业务 (返回 dict) =======================

def _live_category(host, pg):
    """直播分组列表: GET /api/v1/video/liveVideo (服务端不下发到分类接口)"""
    lst = []
    try:
        r = _get(_fix_host(host) + "/api/v1/video/liveVideo")
        data = (json.loads(r).get("data") or {})
        for v in data.get("list") or []:
            if not v.get("id"):
                continue
            lst.append({
                "vod_id": str(v.get("id")),
                "vod_name": v.get("name") or "",
                "vod_pic": v.get("videoPic") or "",
                "vod_remarks": v.get("remarks") or ("直播" if v.get("typeId") else ""),
            })
    except Exception:
        pass
    return {"page": 1, "pagecount": 1, "limit": len(lst), "total": len(lst), "list": lst}

def _fetch_detail(host, vid):
    resp = _post_form(host, "/api/v1/video/videoDetails", {"id": str(vid)})
    try:
        return json.loads(resp).get("data") or {}
    except Exception:
        return {}

def _detail(host, vid):
    data = _fetch_detail(host, vid)
    if not data:
        return {"list": []}
    sources = data.get("playerSource") or []
    from_names, from_urllists = [], []
    seen = {}
    for src in sources:
        eps = src.get("episodes") or []
        if not eps:
            continue
        name = src.get("sourceName") or "剧下饭直播"
        if name in seen:          # 同名线路加序号区分
            seen[name] += 1
            name = name + str(seen[name])
        else:
            seen[name] = 1
        segs = []
        for i, ep in enumerate(eps, 1):
            ep_name = (ep.get("episodeName") or "") or ("第" + str(i) + "集")
            ep_name = ep_name.replace("$", "_").replace("#", "_")
            segs.append(ep_name + "$" + str(vid) + "_" + str(i))
        from_names.append(name)
        from_urllists.append("#".join(segs))
    if not from_urllists:
        return {"list": []}
    play_from = "$$$".join(from_names)     # 多线路: 名字用 $$$ 分隔
    play_url = "$$$".join(from_urllists)   # 线路内集数用 # 分隔
    return {"list": [{
        "vod_id": str(data.get("id") or vid),
        "vod_name": data.get("name") or "",
        "vod_pic": data.get("videoPic") or "",
        "vod_actor": data.get("actor") or "",
        "vod_director": data.get("director") or "",
        "vod_remarks": data.get("remarks") or "",
        "vod_content": data.get("content") or "",
        "vod_year": data.get("year") or "",
        "vod_area": data.get("area") or "",
        "vod_play_from": play_from,
        "vod_play_url": play_url,
    }]}

def _analysis_url(host, source_code, pc):
    """调用服务端 /api/v1/player/analysisUrl 把加密 playerCode 解析成真实播放地址。
    直播(sourceCode=zhibo/difang/huya)由此返回秒播地址。解析成功返回 URL, 失败空串。"""
    if not source_code or not pc:
        return ""
    try:
        r = _post_form(host, "/api/v1/player/analysisUrl", {"from": source_code, "code": pc})
        u = (json.loads(r).get("data") or "")
        if str(u).startswith("http"):
            return str(u)
    except Exception:
        pass
    return ""

def _play(host, flag, pid):
    try:
        vid, ep = pid.rsplit("_", 1)
        ep = int(ep)
    except Exception:
        return {"parse": 0, "url": pid, "header": {"User-Agent": UA}}
    data = _fetch_detail(host, vid)
    sources = data.get("playerSource") or []
    flag_s = str(flag or "").strip()
    # 优先用户当前选中的线路, 其余线路作为备选
    ordered = [src for src in sources if str(src.get("sourceName") or "").strip() == flag_s]
    for src in sources:
        if src not in ordered:
            ordered.append(src)
    for src in ordered:
        eps = src.get("episodes") or []
        if not eps or ep > len(eps):
            continue
        pc = (eps[ep - 1] or {}).get("playerCode") or ""
        parse_url = src.get("parseUrl") or ""
        source_code = src.get("sourceCode") or ""
        if parse_url and pc:
            j = _get(parse_url + pc)
            try:
                u = json.loads(j).get("url") or ""
            except Exception:
                u = ""
            if u:
                return {"parse": 0, "url": u, "header": {"User-Agent": UA}}
        # 直播/加密码: 优先走服务端 analysisUrl 秒播解析 (zb-xxx / 数字房间号 / co_xxx)
        if pc and not str(pc).startswith("http"):
            u = _analysis_url(host, source_code, pc)
            if u:
                headers = {"User-Agent": UA}
                if source_code == "huya":
                    headers["Referer"] = "https://www.huya.com/"
                return {"parse": 0, "url": u, "header": headers}
            # 解析失败: 仍把 code 原样返回, 交由播放器自行尝试
            return {"parse": 0, "url": pc, "header": {"User-Agent": UA}}
        elif pc:
            return {"parse": 0, "url": pc, "header": {"User-Agent": UA}}
    return {"parse": 0, "url": "", "header": {"User-Agent": UA}}

# ======================= 类式接口 (class Spider) =======================

class Spider(_BaseSpider):
    """OK影视/TVBox 类式规范: 各方法返回 dict, 完整引擎契约。
    单分类"直播"(22023), 详情/播放走剧下饭服务端秒播解析。"""

    def __init__(self, *args, **kwargs):
        self._host = BASE_URLS[0]
        if kwargs.get("host"):
            self._host = _fix_host(kwargs["host"])
        if kwargs.get("extend") is not None:
            self.init(kwargs["extend"])

    def init(self, extend=""):
        if extend:
            s = str(extend).strip()
            if s.startswith("http"):
                self._host = _fix_host(s)
            elif s.startswith("base="):
                self._host = _fix_host(s[5:])

    def getName(self):
        return "剧下饭直播"

    def getDependence(self):
        return []

    def homeContent(self, filter=False):
        return {"class": [{"type_id": str(LIVE_TYPE_ID), "type_name": "直播"}],
                "filters": {}, "list": []}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg="1", filter=True, extend=""):
        return _live_category(self._host, pg)

    def detailContent(self, ids, flags=None):
        if not ids:
            return {"list": []}
        return _detail(self._host, ids[0])

    def searchContent(self, key, quick=False, pg="1"):
        # 直播源无搜索接口
        return {"page": 1, "pagecount": 1, "limit": 0, "total": 0, "list": []}

    def playerContent(self, flag, ids, vipFlags=None):
        return _play(self._host, flag, ids)

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return False

    def localProxy(self, param):
        return {"list": [], "parse": 0, "url": ""}

    def liveContent(self, url):
        # 直播分组为点播型透传(详情+播放), 不走 m3u
        return {"list": []}

    def action(self, action):
        return {}

    def destroy(self):
        pass


# ======================= 模块级双入口（drpy site 模式 / 旧内核兼容） =======================

_SINGLETON = None


def _get_singleton():
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = Spider()
    return _SINGLETON


def homeContent(filter=False):
    return _get_singleton().homeContent(filter)


def homeVideoContent():
    return _get_singleton().homeVideoContent()


def categoryContent(tid, pg="1", filter=True, extend=""):
    return _get_singleton().categoryContent(tid, pg, filter, extend)


def detailContent(ids, flags=None):
    return _get_singleton().detailContent(ids, flags)


def searchContent(key, quick=False, pg="1"):
    return _get_singleton().searchContent(key, quick, pg)


def playerContent(flag, ids, vipFlags=None):
    return _get_singleton().playerContent(flag, ids, vipFlags)


def liveContent(url):
    return _get_singleton().liveContent(url)


def localProxy(params):
    return _get_singleton().localProxy(params)


# 类名别名（部分内核按小写 spider 约定取类）
spider = Spider


# ======================= 本地自测 =======================

if __name__ == "__main__":
    def show(label, s, n=260):
        txt = json.dumps(s, ensure_ascii=False) if not isinstance(s, str) else s
        print("== " + label + " ==")
        print(txt if len(txt) <= n else txt[:n])
        print()

    sp = Spider()
    show("Spider.homeContent", sp.homeContent(False))
    show("Spider.categoryContent(live)", sp.categoryContent("22023", "1", False, ""))
