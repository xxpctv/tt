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
import re
import threading
import time
from base64 import b64encode
from urllib.request import Request, urlopen
from urllib.parse import quote, quote_plus, urljoin

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    _BaseSpider = object

# 诊断日志（OK影视 端写 cache/py/下饭diag.log，定位直播导航调用路径）
import os
_DIAG = os.environ.get("JXF_DIAG", "1")


def _diag(msg):
    try:
        if not _DIAG:
            return
        f = globals().get("__file__")
        if f:
            p = os.path.join(os.path.dirname(os.path.abspath(f)), "下饭diag.log")
        else:
            p = "/data/data/com.fongmi.android.tv/cache/py/下饭diag.log"
        with open(p, "a") as fp:
            fp.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:
        pass

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

# 静态 10 大类（与 liveVideo 服务端一致；避免 OK影视 直播导航多次调
# homeContent/分类映射时重复网络请求，咕噜式：分类栏直接用本表）
_CATEGORIES = [
    ("366473", "央视CCTV"), ("370134", "地方频道"), ("370855", "虎牙直播"),
    ("430703", "周星驰轮播专场"), ("432330", "林正英轮播专场"),
    ("433991", "古墓系列电影专场"), ("544873", "贺岁电影轮播"),
    ("545865", "电影解说频道"), ("586316", "成龙轮播专场"), ("586444", "漫威宇宙轮播"),
]
_CATEGORY_NAME2ID = {n: t for t, n in _CATEGORIES}

# ======================= liveContent m3u 缓存 (lives 直播组) =======================

_LIVE_CACHE = {}


def _live_cache_get(key):
    v = _LIVE_CACHE.get(key)
    if v and time.time() - v[0] < 1800:   # 30 分钟 TTL
        return v[1]
    return None


def _live_cache_set(key, m3u):
    _LIVE_CACHE[key] = (time.time(), m3u)

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


_EXP_CACHE = {}

# _play TTL 秒播缓存：pid → (ts, {"parse":0,"url":...,"header":...})
# OK影视 点播型分类卡片点击"台名"调 playerContent；同一台切换线路/暂停回放都会重复调，
# 60 秒内 token 未过期，直接返回缓存直链即可秒开。
_PLAY_CACHE = {}
_PLAY_TTL = 60


def _live_channel_sort_key(name):
    """频道内部排序键：CCTV 数字顺排，带 + 号的插在整数后面；其他频道按首个数字顺排；
    无数字的纯文字频道放最后。
    例：CCTV1综合 < CCTV2财经 < ... < CCTV5体育 < CCTV5+体育赛事 < CCTV6电影
    """
    m = re.search(r'CCTV\s*(\d+)(\+?)', name, re.IGNORECASE)
    if m:
        return (0, int(m.group(1)), 1 if m.group(2) else 0, name)
    m2 = re.search(r'(\d+)', name)
    if m2:
        return (1, int(m2.group(1)), 0, name)
    return (2, 0, 0, name)


def _live_category_expanded(host, pg, tid=None):
    """把 10 个大类（央视CCTV/地方频道/虎牙直播/电影轮播…）展开为具体台列表。
    返回每个台一个条目（vod_id=pid 形如 366473_1），供 OK影视 直播组/聚合器
    直接当频道显示与播放（与咕噜央视 categoryContent 返回台列表的做法一致）。
    tid 为具体大类 id 时只返回该大类的台；否则返回全部。"""
    ck = 'exp22023'
    cached = _EXP_CACHE.get(ck)
    if not (cached and time.time() - cached[0] < 1800):
        lst = _live_category(host, pg).get('list', [])
        items = []
        d_lock = threading.Lock()

        def _w(one):
            vid = str(one.get('vod_id') or '')
            if not vid:
                return
            try:
                d = _detail(host, vid)
                vod = (d.get('list') or [None])[0]
                if not vod:
                    return
                grp = one.get('vod_name') or '直播'
                pic = one.get('vod_pic') or vod.get('vod_pic') or ''
                for ep in (vod.get('vod_play_url') or '').split('#'):
                    if '$' not in ep:
                        continue
                    nm, pid = ep.split('$', 1)
                    disp = nm.replace('_', ' ') or nm
                    with d_lock:
                        items.append({"vod_id": pid, "vod_name": disp,
                                      "vod_pic": pic, "vod_remarks": grp})
            except Exception:
                pass

        ths = [threading.Thread(target=_w, args=(o,), daemon=True) for o in lst]
        for t in ths:
            t.start()
        end = time.time() + 15
        for t in ths:
            t.join(max(0.0, end - time.time()))
        _CAT_ORDER = {n: i for i, (_, n) in enumerate(_CATEGORIES)}
        items.sort(key=lambda x: (_CAT_ORDER.get(x.get('vod_remarks') or '', 999),
                                  _live_channel_sort_key(x.get('vod_name') or '')))
        _EXP_CACHE[ck] = (time.time(), items)
    items = [dict(i) for i in _EXP_CACHE[ck][1]]
    if tid and str(tid) not in ('22023', '1', ''):
        tid_s = str(tid)
        # 大类 id（366473）或大类名（央视CCTV）→ 过滤出该大类台；
        # 聚合器透传的源名/任意分类名（如下饭央视）无匹配 → 保留全部。
        filtered = [i for i in items
                    if str(i.get('vod_id') or '').split('_')[0] == tid_s
                    or i.get('vod_remarks') == tid_s]
        if filtered:
            items = filtered
    res = {"page": 1, "pagecount": 1, "limit": len(items), "total": len(items), "list": items}
    return res

def _fetch_detail(host, vid):
    resp = _post_form(host, "/api/v1/video/videoDetails", {"id": str(vid)})
    try:
        return json.loads(resp).get("data") or {}
    except Exception:
        return {}

def _detail(host, vid):
    vid = str(vid)
    if '_' in vid:
        # 兼容 "大类id_序号" 的 pid 形 vod_id（categoryContent 展开后直接传入）
        vid = vid.rsplit('_', 1)[0]
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
    """解析直链并返回 playerContent 标准结构；同 pid 60 秒内重复调用命中 TTL 缓存秒播。"""
    pid = str(pid or '')
    if '_' not in pid:
        # 兼容纯 vod_id（直播组把大类直接当频道播放时）：取该大类第一台
        d = _detail(host, pid)
        vod = (d.get('list') or [None])[0]
        if vod and vod.get('vod_play_url'):
            first = vod['vod_play_url'].split('#')[0]
            if '$' in first:
                pid = first.split('$', 1)[1]
    # TTL 缓存命中 → 秒播
    cached = _PLAY_CACHE.get(pid)
    if cached and (time.time() - cached[0] < _PLAY_TTL):
        return cached[1]
    try:
        vid, ep = pid.rsplit("_", 1)
        ep = int(ep)
    except Exception:
        _r = {"parse": 0, "url": pid, "header": {"User-Agent": UA}}
        _PLAY_CACHE[pid] = (time.time(), _r); return _r
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
                _r = {"parse": 0, "url": u, "header": {"User-Agent": UA}}
                _PLAY_CACHE[pid] = (time.time(), _r); return _r
        # 直播/加密码: 优先走服务端 analysisUrl 秒播解析 (zb-xxx / 数字房间号 / co_xxx)
        if pc and not str(pc).startswith("http"):
            u = _analysis_url(host, source_code, pc)
            if u:
                headers = {"User-Agent": UA}
                if source_code == "huya":
                    headers["Referer"] = "https://www.huya.com/"
                _r = {"parse": 0, "url": u, "header": headers}
                _PLAY_CACHE[pid] = (time.time(), _r); return _r
            # 解析失败: 仍把 code 原样返回, 交由播放器自行尝试
            _r = {"parse": 0, "url": pc, "header": {"User-Agent": UA}}
            _PLAY_CACHE[pid] = (time.time(), _r); return _r
        elif pc:
            _r = {"parse": 0, "url": pc, "header": {"User-Agent": UA}}
            _PLAY_CACHE[pid] = (time.time(), _r); return _r
    _r = {"parse": 0, "url": "", "header": {"User-Agent": UA}}
    _PLAY_CACHE[pid] = (time.time(), _r); return _r

def _rewrite_m3u8(content, base_url):
    """把 m3u8 里的相对分片/密钥地址改写为绝对地址（base_url 为最终 m3u8 地址）。"""
    out = []
    for line in content.splitlines():
        s = line.strip()
        if not s:
            out.append(line)
            continue
        if s.startswith('#'):
            if 'URI="' in s:
                line = re.sub(
                    r'URI="([^"]*)"',
                    lambda m: 'URI="' + urljoin(base_url, m.group(1)) + '"',
                    line)
            out.append(line)
        else:
            out.append(urljoin(base_url, s))
    return '\n'.join(out)


# ======================= 类式接口 (class Spider) =======================

class Spider(_BaseSpider):
    """OK影视/TVBox 类式规范: 各方法返回 dict, 完整引擎契约。
    - 聚合器/AjeoZB：categoryContent 返回 10 大类（按 _is_vod_source 透传）；
    - OK影视 顶部「直播」导航：liveContent 返回全量台的 m3u，频道地址走
      localProxy(fun=jxf) 按需解析，避免开播前 token 过期。
    """

    # 静态分类：仅一个大类入口，与 homeContent 一致（咕噜央视同模式）；
    # 聚合器 _sub_static_classes 优先读 homeContent['class']（见下方 homeContent）。
    _categories = [("22023", "直播")]

    # 不标记 _is_vod_source：本源与咕噜央视同属「双模式」——同时具备 homeContent
    # （一个大类入口，与 _categories 一致）+ categoryContent（大类卡片/台列表）
    # + liveContent（全量台 m3u）。聚合器应把父标签"下饭央视"点击路由到
    # liveContent → 按 group-title 分组 → 10 张大类卡片，和咕噜央视完全一致。
    # （无标记时 AjeoZB 的点播型透传分支 AND 条件被跳过，走双模式路径。）

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
        # 咕噜央视同模式：返回一个大类入口，与 _categories 完全一致。
        # OK影视 独立源模式下：左栏只显示"直播"一个分类，点它 → categoryContent
        # 返回 10 个大类卡片（央视CCTV/地方频道/虎牙直播/轮播专场…）。
        # 聚合器模式下：父标签点击走 liveContent → 按 m3u group-title 分组 → 同样
        # 得到 10 张大类卡片。
        _diag("homeContent filter=%s" % (filter,))
        return {"class": [{"type_id": "22023", "type_name": "直播"}], "filters": {}, "list": []}

    def homeVideoContent(self):
        _diag("homeVideoContent")
        return {"list": []}

    def _category_cards(self, pg="1"):
        """返回 10 个大类卡片（央视CCTV/地方频道/虎牙直播/轮播专场…），
        每个卡片 vod_play_url = 该大类所有台按「台名$proxy_url」拼接。
        图片取自原始 liveVideo 接口的分类封面（非第一个台的图片）。"""
        all_items = _live_category_expanded(self._host, pg, None).get('list', [])
        # 按大类分组
        groups = {}
        for it in all_items:
            grp = it.get('vod_remarks') or '其他'
            groups.setdefault(grp, []).append(it)
        # 原始大类卡片封面图（liveVideo 接口返回）：name → vod_pic
        cat_pic = {}
        try:
            cls_list = _live_category(self._host, pg).get('list') or []
            for c in cls_list:
                nm = c.get('vod_name') or ''
                if nm and c.get('vod_pic'):
                    cat_pic[nm] = c['vod_pic']
        except Exception:
            pass
        cards = []
        from urllib.parse import quote as _q
        import base64 as _b64, time as _t
        # 大类顺序按 _CATEGORIES
        _CAT_NAME2ID_for_card = {n: t for t, n in _CATEGORIES}
        for (_, gname) in _CATEGORIES:
            cls_items = groups.get(gname)
            if not cls_items:
                continue
            play_urls = []
            for ch in cls_items:
                n = ch.get('vod_name', '')
                pid = str(ch.get('vod_id', ''))
                if not pid or not n:
                    continue
                enc = _b64.b64encode(pid.encode('utf-8')).decode('ascii')
                prox = "localProxy(fun=jxf&id=%s&enc=%s&__v=%d)" % (
                    _q(pid), enc, int(_t.time()) % 1000)
                play_urls.append(n + '$' + prox)
            # 图片：优先原始大类封面，兜底用该类第一个台的图片
            first_pic = ''
            if cls_items:
                first_pic = cls_items[0].get('vod_pic', '') or ''
            pic = cat_pic.get(gname) or first_pic
            cards.append({
                "vod_id": _CAT_NAME2ID_for_card.get(gname, gname),
                "vod_name": gname,
                "vod_pic": pic,
                "vod_remarks": "直播",
                "vod_play_from": "jxf",
                "vod_play_url": '#'.join(play_urls),
            })
        return {"page": 1, "pagecount": 1, "limit": len(cards),
                "total": len(cards), "list": cards}

    def categoryContent(self, tid, pg="1", filter=True, extend=""):
        # 咕噜央视同模式：
        # - tid=22023/空/直播入口 → 返回 10 个大类卡片（左栏组），OK影视 自动展开
        #   卡片的 vod_play_url 为该类所有台；
        # - tid=大类 id（366473）/名（央视CCTV）→ 只返回该大类的具体台列表。
        tid_s = str(tid or '').strip()
        _diag("categoryContent tid=%r pg=%s filter=%s extend=%r" % (tid_s, pg, filter, extend))
        # 直播入口 → 返回 10 张大类卡片
        if tid_s in ('22023', '1', '直播', '') or not tid_s:
            ret = self._category_cards(pg)
            _diag("categoryContent cards tid=%s total=%d" % (tid_s, ret.get('total')))
            return ret
        # 指定大类 → 返回该大类具体台
        vid = tid_s if tid_s.isdigit() else _CATEGORY_NAME2ID.get(tid_s, '')
        if vid.isdigit():
            try:
                ret = _live_category_expanded(self._host, pg, vid)
                _diag("categoryContent class tid=%s total=%d" % (tid_s, ret.get('total')))
                return ret
            except Exception as e:
                _diag("categoryContent EXC tid=%s %s:%s" % (tid_s, type(e).__name__, e))
        ret = _live_category_expanded(self._host, pg, None)
        _diag("categoryContent all tid=%s total=%d" % (tid_s, ret.get('total')))
        return ret

    def detailContent(self, ids, flags=None):
        _diag("detailContent ids=%r" % (ids,))
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

    # ---- 直播组入口（OK影视 lives type=3） ----

    def liveContent(self, url):
        """把 10 大类展开为全量台的 m3u；频道地址统一走 localProxy 按需解析，
        避免开播前批量解析 180+ 台导致等待与 token 过期。
        秒播优化：① 内存缓存命中直接返回；② 分组详情并发拉取；③ 截止时间兜底。"""
        try:
            base_proxy = self.getProxyUrl() or ''
        except Exception:
            base_proxy = ''
        if base_proxy and not base_proxy.endswith(('?', '&')):
            base_proxy += '&'
        use_proxy = bool(base_proxy)
        ck = 'jxf|' + base_proxy
        cached = _live_cache_get(ck)
        if cached:
            return cached
        try:
            items = _live_category_expanded(self._host, '1', None).get('list') or []
        except Exception:
            items = []
        resolved = {}
        if not use_proxy and items:
            # 无代理底座（旧内核）：并发解析直链，整体 20s 截止
            r_lock = threading.Lock()
            def _rw(it):
                try:
                    u = (_play(self._host, '', it.get('vod_id')) or {}).get('url') or ''
                except Exception:
                    u = ''
                if u.startswith(('http://', 'https://')):
                    with r_lock:
                        resolved[str(it.get('vod_id'))] = u
            ths = [threading.Thread(target=_rw, args=(it,), daemon=True) for it in items]
            for t in ths:
                t.start()
            end = time.time() + 20
            for t in ths:
                t.join(max(0.0, end - time.time()))
        lines = ['#EXTM3U']
        for it in items:
            pid = str(it.get('vod_id') or '')
            name = it.get('vod_name') or ''
            grp = it.get('vod_remarks') or '剧下饭直播'
            if not pid or not name:
                continue
            if use_proxy:
                ch_url = base_proxy + 'fun=jxf&id=' + quote(pid)
            else:
                ch_url = resolved.get(pid, '')
            if not ch_url:
                continue
            lines.append('#EXTINF:-1 tvg-name="%s" group-title="%s",%s'
                         % (name, grp, name))
            lines.append(ch_url)
        m3u = '\n'.join(lines)
        if len(lines) > 1:
            _live_cache_set(ck, m3u)
        return m3u

    def localProxy(self, param):
        # 直播频道播放回调：fun=jxf&id=pid → 解析并回写 m3u8
        if isinstance(param, dict) and param.get('fun') == 'jxf':
            return self._proxy_live_channel(param)
        return {"list": [], "parse": 0, "url": ""}

    def _proxy_live_channel(self, param):
        pid = str(param.get('id') or '')
        if not pid:
            return [404, 'text/plain', b'not found', None]
        try:
            pr = _play(self._host, param.get('flag') or '', pid)
            url = (pr or {}).get('url') or ''
            if not url.startswith(('http://', 'https://')):
                return [502, 'text/plain', b'live resolve error', None]
            headers = dict((pr or {}).get('header') or {})
            headers.setdefault('User-Agent', UA)
            body = None
            final_url = url
            ct = 'application/vnd.apple.mpegurl'
            try:
                req = Request(url, headers=headers)
                with urlopen(req, timeout=10) as r:
                    # 只读前 256KB 判断是否 m3u8；直播 FLV/TS 不能整段读，避免卡住
                    body = r.read(262144)
                    final_url = r.geturl() or url
                    ct = r.headers.get('Content-Type') or ct
            except Exception:
                body = None
            if body is None:
                # 无法代理时退回 302，交给播放器直连
                return [302, 'text/plain', b'', {'Location': url}]
            try:
                text = body.decode('utf-8', 'replace')
                if '#EXTM3U' in text:
                    text = _rewrite_m3u8(text, final_url)
                    return [200, 'application/vnd.apple.mpegurl',
                            text.encode('utf-8'), None]
            except Exception:
                pass
            return [302, 'text/plain', b'', {'Location': url}]
        except Exception:
            return [502, 'text/plain', b'live resolve error', None]

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
