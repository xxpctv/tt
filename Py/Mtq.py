# -*- coding: utf-8 -*-
# TVBox Python Spider - Mtq（🍊蒙太奇┃秒播4K）
# 对齐 1109.jar -> com.github.catvod.spider.Mtq (csp_Mtq extends Spider)
#
# 传输层（NativeCrypto.mtEnc / nMtDec，已实测）：
#   key      = md5(buildTime + "^~!@#[-" + pkId)
#   URL      = http://{host}/nmtq.php/v7/logs
#   请求体   = {"method":X,"data":{...},"csrf":毫秒时间戳}
#              mtEnc = base64( iv_ascii16 + AES-128-CBC(json, key, iv) )，iv_ascii = "%016x" % 毫秒
#   响应     = 明文 JSON（{ 开头）或容器：
#              base64(表串) + base64(密文) + "eGRkYXBwc2VjcmV0a2V5" + str(N)
#              N = 表串的 base64 长度；表串内 "0x123" 序列经位移还原成 IV，
#              密文用 AES-128-CBC + 该 IV 解密（PKCS7）
#
# 常量（1109.jar 解出）：
#   host = 23.225.14.70:520   pkId = com.aimiaozai.app.mtqa
#   buildTime = 1774102701179 signMd5 = e19d86d532651e31faddf2af4af2d539
#
# API：
#   nav              {token:""}                    → data[]: type_id/type_name/type_extend
#   index_recommend  {token:""}                    → data.videos[].vlist[]
#   video_list       {pg, tid, class?, area?, ...}  → data[] + pagecount/total
#   search           {text, pg}                    → data[]
#   video_detail     {token:"", id, sign_md5, apk_path, apk_length} → data.vod_info{...}
#
# 播放：线路 url 用 '#' 分集、'$' 分「集名/链接」；线路按优先级排序（直链/官网解析/...
#   以及含「勿信/广告/有广」的线路降权）；解密后的 av7: 元数据交给 playerContent。

import re
import json
import time
import base64
import hashlib
import urllib.request
import urllib.parse

# 基类：OK影视/影视仓 python 运行时提供 base.spider.Spider
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

# ---------------- 预设 ----------------
PRESET = {
    "host": "23.225.14.70:520",
    "pkId": "com.aimiaozai.app.mtqa",
    "buildTime": "1774102701179",
    "version": "2.0.3",
    "versionNumber": "103",
    "userAgent": "Dart/3.11 (dart:io)",
    "platform": "android",
    "platformVersion": "QKQ1.190828.002 test-keys",
    "signMd5": "e19d86d532651e31faddf2af4af2d539",
    "apkLength": "52642542",
    "apkPath": "/data/app/com.aimiaozai.app.mtqa-8GtF1uYYjXR-YZIfWPoUGA==/base.apk",
}

MARKER = "eGRkYXBwc2VjcmV0a2V5"   # base64("xddappsecretkey")
LOG_PATH = "/nmtq.php/v7/logs"
BROWSER_UA = "Mozilla/5.0 (Linux; Android 10) Chrome/120 Mobile Safari/537"
FILTER_WORDS = ("勿信", "广告", "有广")
TYPE_EXT_KEYS = ("class", "area", "year", "lang", "star", "director")
TYPE_EXT_LABELS = ("剧情", "地区", "年份", "语言", "主演", "导演")
# 站点自建解析 :801/:802/:803 实测恒返回 {"code":400,"msg":"失败4"}，整条线路无可播地址
DEAD_PARSE_RE = re.compile(r"^https?://[^/]*:(?:801|802|803)(?:[/?]|$)", re.I)
# nav 取不到时的兜底分类（同站点真实 type_id）
FALLBACK_CLASSES = (
    ("1", "电影"), ("2", "剧集"), ("3", "动漫"), ("4", "综艺"),
    ("5", "儿童"), ("20", "纪录"), ("22", "短剧"),
)

HOST = PRESET["host"]
SIGN = PRESET["signMd5"]
APK_PATH = PRESET["apkPath"]
APK_LENGTH = int(PRESET["apkLength"])
HIDE_UNPLAYABLE = False

_NAV_CACHE = None
_REC_CACHE = None
_DETAIL_CACHE = {}   # vid -> vod_url_with_player[]

# ---------------- 纯 Python AES（CBC + PKCS7） ----------------
def _gmul(a, b):
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xff
        if hi:
            a ^= 0x1b
        b >>= 1
    return p


def _rotl8(x, n):
    return ((x << n) | (x >> (8 - n))) & 0xff


def _build_sbox():
    sbox = [0] * 256
    p = q = 1
    while True:
        p = (p ^ ((p << 1) & 0xff) ^ (0x1b if p & 0x80 else 0)) & 0xff
        q = (q ^ ((q << 1) & 0xff)) & 0xff
        q = (q ^ ((q << 2) & 0xff)) & 0xff
        q = (q ^ ((q << 4) & 0xff)) & 0xff
        if q & 0x80:
            q ^= 0x09
        x = q ^ _rotl8(q, 1) ^ _rotl8(q, 2) ^ _rotl8(q, 3) ^ _rotl8(q, 4)
        sbox[p] = (x ^ 0x63) & 0xff
        if p == 1:
            break
    sbox[0] = 0x63
    return sbox


_SBOX = _build_sbox()
_INV = [0] * 256
for _i, _v in enumerate(_SBOX):
    _INV[_v] = _i


def _expand_key(key):
    nk = len(key) // 4
    nr = nk + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    rcon = 1
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [_SBOX[b] for b in t]
            t[0] ^= rcon
            rcon = _gmul(rcon, 2)
        elif nk > 6 and i % nk == 4:
            t = [_SBOX[b] for b in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    return w, nr


def _add_round_key(st, w, rnd):
    for c in range(4):
        word = w[4 * rnd + c]
        for r in range(4):
            st[4 * c + r] ^= word[r]


def _encrypt_block(block, w, nr):
    st = list(block)
    _add_round_key(st, w, 0)
    for rnd in range(1, nr + 1):
        st = [_SBOX[b] for b in st]
        old = list(st)
        for r in range(4):
            for c in range(4):
                st[4 * c + r] = old[4 * ((c + r) % 4) + r]
        if rnd != nr:
            for c in range(4):
                s0, s1, s2, s3 = st[4 * c:4 * c + 4]
                st[4 * c] = _gmul(s0, 2) ^ _gmul(s1, 3) ^ s2 ^ s3
                st[4 * c + 1] = s0 ^ _gmul(s1, 2) ^ _gmul(s2, 3) ^ s3
                st[4 * c + 2] = s0 ^ s1 ^ _gmul(s2, 2) ^ _gmul(s3, 3)
                st[4 * c + 3] = _gmul(s0, 3) ^ s1 ^ s2 ^ _gmul(s3, 2)
        _add_round_key(st, w, rnd)
    return bytes(st)


def _decrypt_block(block, w, nr):
    st = list(block)
    _add_round_key(st, w, nr)
    for rnd in range(nr - 1, -1, -1):
        old = list(st)
        for r in range(4):
            for c in range(4):
                st[4 * c + r] = old[4 * ((c - r) % 4) + r]
        st = [_INV[b] for b in st]
        _add_round_key(st, w, rnd)
        if rnd != 0:
            for c in range(4):
                s0, s1, s2, s3 = st[4 * c:4 * c + 4]
                st[4 * c] = _gmul(s0, 14) ^ _gmul(s1, 11) ^ _gmul(s2, 13) ^ _gmul(s3, 9)
                st[4 * c + 1] = _gmul(s0, 9) ^ _gmul(s1, 14) ^ _gmul(s2, 11) ^ _gmul(s3, 13)
                st[4 * c + 2] = _gmul(s0, 13) ^ _gmul(s1, 9) ^ _gmul(s2, 14) ^ _gmul(s3, 11)
                st[4 * c + 3] = _gmul(s0, 11) ^ _gmul(s1, 13) ^ _gmul(s2, 9) ^ _gmul(s3, 14)
    return bytes(st)


def _cbc_encrypt(key, iv, data):
    w, nr = _expand_key(key)
    n = 16 - len(data) % 16
    data = data + bytes([n]) * n
    out = b""
    prev = iv
    for i in range(0, len(data), 16):
        blk = bytes(a ^ b for a, b in zip(data[i:i + 16], prev))
        prev = _encrypt_block(blk, w, nr)
        out += prev
    return out


def _cbc_decrypt(key, iv, data):
    w, nr = _expand_key(key)
    out = b""
    prev = iv
    for i in range(0, len(data), 16):
        blk = data[i:i + 16]
        out += bytes(a ^ b for a, b in zip(_decrypt_block(blk, w, nr), prev))
        prev = blk
    if out:
        pad = out[-1]
        if 0 < pad <= 16 and out[-pad:] == bytes([pad]) * pad:
            out = out[:-pad]
    return out


# ---------------- 加解密（mtEnc / mtDec） ----------------
def _key():
    src = (PRESET["buildTime"] + "^~!@#[-" + PRESET["pkId"]).encode("utf-8")
    try:
        # 部分 Android/OpenSSL 构建禁止无用途的 md5
        return hashlib.md5(src, usedforsecurity=False).digest()
    except TypeError:
        return hashlib.md5(src).digest()


def _b64d(s):
    if isinstance(s, str):
        s = s.encode("latin1", "ignore")
    s = s.replace(b"-", b"+").replace(b"_", b"/")
    s = s.replace(b" ", b"").replace(b"\n", b"").replace(b"\r", b"")
    return base64.b64decode(s + b"=" * (-len(s) % 4))


def _mt_enc(text):
    """nMtEnc：base64(iv_ascii + AES-128-CBC(明文, key, iv_ascii))"""
    iv = ("%016x" % int(time.time() * 1000)).encode("ascii")
    return base64.b64encode(iv + _cbc_encrypt(_key(), iv, text.encode("utf-8"))).decode("ascii")


def _mt_dec(raw):
    """nMtDec：明文直返；否则拆容器（表串还原 IV）后 AES 解密"""
    try:
        text = raw.decode("latin1", "ignore") if isinstance(raw, (bytes, bytearray)) else str(raw)
        text = "".join(text.split())
        if not text:
            return None
        if text[0] in "{[":
            return text
        pos = text.find(MARKER)
        if pos < 0:
            return None
        tail = _b64d(text[pos + len(MARKER):]).decode("latin1", "ignore")
        digits = ""
        for ch in tail:
            if not ch.isdigit():
                break
            digits += ch
        if not digits:
            return None
        n = int(digits)
        if n <= 0 or n >= pos:
            return None
        table = _b64d(text[:n]).decode("latin1", "ignore")
        payload = _b64d(text[n:pos])
        nums = [int(x) for x in table.split("0x")[1:] if x.isdigit()]
        if not nums:
            return None
        cnt = len(nums)
        hexs = []
        for i in range(cnt):
            if i % 2 == 0:
                k = -11
            elif i % 3 == 0:
                k = -4
            elif i % 5 == 0:
                k = -2
            else:
                k = -3
            hexs.append("%02x" % ((nums[cnt - 1 - i] + k) & 0xff))
        hexs = "".join(hexs) + payload.hex()
        if len(hexs) < 64 or (len(hexs) & 0x1e):
            return None
        pt = _cbc_decrypt(_key(), bytes.fromhex(hexs[:32]), bytes.fromhex(hexs[32:]))
        return pt.decode("utf-8", "ignore")
    except Exception:
        return None


def _loads(text):
    """I111111l11ll1l：宽松 JSON（容忍尾部多余字符）"""
    if not text:
        return {}
    try:
        obj, _end = json.JSONDecoder().raw_decode(text.strip())
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


# ---------------- HTTP ----------------
def _headers():
    return {
        "User-Agent": PRESET["userAgent"],
        "version": PRESET["version"],
        "version-number": PRESET["versionNumber"],
        "pk-id": PRESET["pkId"],
        "build-time": PRESET["buildTime"],
        "platform": PRESET["platform"],
        "platform-version": PRESET["platformVersion"],
        "Content-Type": "text/plain; charset=utf-8",
    }


def _post(method, data=None):
    """lIl111Ill1l1I1l1：加密 POST {host}{LOG_PATH}"""
    try:
        body = json.dumps({
            "method": method,
            "data": data if isinstance(data, dict) else {},
            "csrf": int(time.time() * 1000),
        }, ensure_ascii=False, separators=(",", ":"))
        payload = _mt_enc(body).encode("ascii")
        req = urllib.request.Request("http://%s%s" % (HOST, LOG_PATH), data=payload,
                                     headers=_headers(), method="POST")
        resp = urllib.request.urlopen(req, timeout=20)
        return _loads(_mt_dec(resp.read()))
    except Exception:
        return {}


# ---------------- 工具 ----------------
def _clean(s):
    if not isinstance(s, str):
        return ""
    s = s.strip()
    for w in FILTER_WORDS:
        if w in s:
            return ""
    return s


def _to_int(v, d=0):
    try:
        return int(str(v).strip())
    except Exception:
        return d


def _first(a, b):
    return a if a not in (None, "") else (b if b is not None else "")


def _is_media(url):
    """l1IIl1l1l111I1l：http 且带直链后缀"""
    if not isinstance(url, str):
        return False
    u = url.lower()
    if not u.startswith("http"):
        return False
    return any(x in u for x in (".m3u8", ".mp4", ".flv", ".ts?", ".mpd"))


def _truthy(v):
    """Illll1l111I11l1lIl：判 parse_secret 之类的开关"""
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return str(v).strip().lower() in ("true", "1", "yes")


def _opt_str(d, k, default=""):
    v = d.get(k) if isinstance(d, dict) else None
    return v if isinstance(v, str) else default


def _map_vod(v):
    pic = _opt_str(v, "vod_pic")
    if pic.startswith("//"):
        pic = "https:" + pic
    return {
        "vod_id": str(_first(v.get("vod_id"), v.get("id"))),
        "vod_name": _clean(_first(v.get("vod_name"), v.get("name"))),
        "vod_pic": pic,
        "vod_remarks": _clean(_first(v.get("vod_remarks"), v.get("remarks"))),
    }


# ---------------- 初始化 ----------------
def init(ext=""):
    """对齐 init(Context, String)：ext 支持 host / token / apk_path / apk_length / hide_unplayable"""
    global HOST, SIGN, APK_PATH, APK_LENGTH, HIDE_UNPLAYABLE, _NAV_CACHE, _REC_CACHE, _DETAIL_CACHE
    HOST = PRESET["host"]
    SIGN = PRESET["signMd5"]
    APK_PATH = PRESET["apkPath"]
    APK_LENGTH = int(PRESET["apkLength"])
    HIDE_UNPLAYABLE = False
    _NAV_CACHE = None
    _REC_CACHE = None
    _DETAIL_CACHE = {}
    if not ext:
        return
    if isinstance(ext, dict):
        obj = ext
    else:
        try:
            obj = json.loads(ext)
        except Exception:
            return
    if not isinstance(obj, dict):
        return
    # 对齐 I11IIllIII1IIl：去协议、去路径，只留 host
    h = str(obj.get("host") or "").strip()
    h = re.sub(r"^https?://", "", h, flags=re.I)
    h = re.sub(r"/.*$", "", h)
    h = re.sub(r"/+$", "", h)
    if h:
        HOST = h
    if obj.get("token"):
        SIGN = str(obj.get("token"))
    if obj.get("apk_path"):
        APK_PATH = str(obj.get("apk_path"))
    if obj.get("apk_length"):
        APK_LENGTH = _to_int(obj.get("apk_length"), APK_LENGTH)
    HIDE_UNPLAYABLE = bool(obj.get("hide_unplayable"))


# ---------------- 首页 ----------------
def homeContent(filter):
    global _NAV_CACHE
    if _NAV_CACHE is None:
        obj = _post("nav", {"token": ""})
        data = obj.get("data") if isinstance(obj, dict) else None
        _NAV_CACHE = data if isinstance(data, list) else []

    classes = []
    filters = {}
    for c in _NAV_CACHE:
        if not isinstance(c, dict):
            continue
        tid = str(c.get("type_id") or "").strip()
        if not tid:
            continue
        classes.append({"type_id": tid, "type_name": c.get("type_name") or ""})
        ext = c.get("type_extend") if isinstance(c.get("type_extend"), dict) else {}
        groups = []
        for key, label in zip(TYPE_EXT_KEYS, TYPE_EXT_LABELS):
            vals = str(ext.get(key) or "").strip()
            if not vals:
                continue
            arr = [{"n": "全部", "v": ""}]
            seen = []
            for v in vals.split(","):
                v = v.strip()
                if not v or v in seen:
                    continue
                seen.append(v)
                arr.append({"n": v, "v": v})
            if len(arr) > 1:
                groups.append({"key": key, "name": label, "value": arr})
        if groups:
            filters[tid] = groups

    if not classes:
        classes = [{"type_id": t, "type_name": n} for t, n in FALLBACK_CLASSES]

    return json.dumps({"class": classes, "filters": filters, "list": _rec_list()}, ensure_ascii=False)


def _rec_list():
    """index_recommend -> data.videos[].vlist[]（带缓存）"""
    global _REC_CACHE
    if _REC_CACHE is not None:
        return _REC_CACHE
    rec = _post("index_recommend", {"token": ""})
    rdata = rec.get("data") if isinstance(rec.get("data"), dict) else {}
    videos = []
    seen = set()
    for g in (rdata.get("videos") or []):
        if not isinstance(g, dict):
            continue
        for v in (g.get("vlist") or []):
            if not isinstance(v, dict):
                continue
            vd = _map_vod(v)
            if not vd["vod_id"] or vd["vod_id"] in seen:
                continue
            seen.add(vd["vod_id"])
            videos.append(vd)
    _REC_CACHE = videos
    return videos


# ---------------- 分类列表 ----------------
def categoryContent(tid, pg, filter, extend):
    page = max(1, _to_int(pg, 1))
    body = {"pg": page, "tid": _to_int(tid, 1)}
    if isinstance(extend, dict):
        for key in TYPE_EXT_KEYS:
            v = extend.get(key)
            if v and str(v).strip() not in ("", "全部"):
                body[key] = str(v).strip()
    obj = _post("video_list", body)
    arr = obj.get("data") if isinstance(obj.get("data"), list) else []
    pagecount = _to_int(obj.get("pagecount"), 0) or 9999
    total = _to_int(obj.get("total"), 0)
    vlist = [_map_vod(v) for v in arr if isinstance(v, dict)]
    return json.dumps({
        "page": page, "pagecount": pagecount, "limit": 20,
        "total": total, "list": vlist,
    }, ensure_ascii=False)


# ---------------- 详情 ----------------
def detailContent(ids):
    if isinstance(ids, str):
        ids = [ids]
    if not ids:
        return json.dumps({"list": []}, ensure_ascii=False)
    vid = str(ids[0]).strip()
    if not re.match(r"^\d+$", vid):
        return json.dumps({"list": []}, ensure_ascii=False)

    body = {
        "token": "",
        "id": _to_int(vid, 0),
        "sign_md5": SIGN,
        "apk_path": APK_PATH,
        "apk_length": APK_LENGTH,
    }
    obj = _post("video_detail", body)
    d = obj.get("data") if isinstance(obj.get("data"), dict) else {}
    info = d.get("vod_info") if isinstance(d.get("vod_info"), dict) else {}
    if not info:
        return json.dumps({"list": []}, ensure_ascii=False)

    arr = info.get("vod_url_with_player")
    arr = arr if isinstance(arr, list) else []
    if len(_DETAIL_CACHE) > 120:
        _DETAIL_CACHE.clear()
    _DETAIL_CACHE[vid] = arr

    has_co4k = any(isinstance(p, dict) and _opt_str(p, "code") == "CO4K"
                   and _truthy(p.get("parse_secret")) for p in arr)

    rows = []
    for it in arr:
        if not isinstance(it, dict):
            continue
        code = _opt_str(it, "code")
        raw = _opt_str(it, "url")
        if not raw:
            continue
        eps = [p for p in raw.split("#") if "$" in p]
        if not eps:
            continue
        name = _opt_str(it, "name") or code or "线路"
        first = eps[0].split("$", 1)[1] if "$" in eps[0] else ""
        ps = it.get("parse_secret")
        papi = _opt_str(it, "parse_api")
        xapi = _opt_str(it, "extra_parse_api")

        # 失效线路（站点自建 :801/:802/:803 解析）直接剔除
        if DEAD_PARSE_RE.match(papi):
            continue

        if _is_media(first):
            prio = 0
        elif first.lower().startswith("http"):
            prio = 4
        elif _truthy(ps):
            prio = 2
        elif _opt_str(it, "parse_secret") or xapi:
            prio = 1
        else:
            prio = 2
        if prio >= 2 and code == "co" and has_co4k:
            prio = 1
        if HIDE_UNPLAYABLE and prio >= 2:
            continue
        for w in FILTER_WORDS:
            if w in name:
                prio += 3
        rows.append((prio, -len(eps), name, eps, it))

    rows.sort(key=lambda r: (r[0], r[1], r[2]))

    froms = []
    urls = []
    for prio, _neg, name, eps, it in rows:
        code = _opt_str(it, "code")
        papi = _opt_str(it, "parse_api")
        xapi = _opt_str(it, "extra_parse_api")
        ps = _opt_str(it, "parse_secret")
        segs = []
        for ep in eps:
            i = ep.find("$")
            nm = ep[:i] if i > 0 else ep
            link = ep[i + 1:] if i >= 0 else ""
            if not link:
                continue
            meta = {"code": code, "url": link}
            if papi:
                meta["parse"] = papi
            if xapi:
                meta["extra"] = xapi
            if ps.startswith("http"):
                meta["secret"] = ps
            b = base64.urlsafe_b64encode(
                json.dumps(meta, ensure_ascii=False).encode("utf-8")).decode("utf-8").rstrip("=")
            segs.append(nm + "$av7:" + b)
        if segs:
            froms.append(name)
            urls.append("#".join(segs))

    content = _first(info.get("vod_content"), info.get("vod_blurb"))
    item = {
        "vod_id": str(_first(info.get("vod_id"), vid)),
        "vod_name": _clean(_first(info.get("vod_name"), "")),
        "vod_pic": _opt_str(info, "vod_pic"),
        "vod_content": re.sub(r"<[^>]+>", "", str(content or "")).strip(),
        "type_name": _clean(_first(info.get("type_name"), info.get("vod_class"))),
        "vod_year": str(info.get("vod_year") or ""),
        "vod_area": _clean(_first(info.get("vod_area"), "")),
        "vod_actor": _clean(_first(info.get("vod_actor"), "")),
        "vod_director": _clean(_first(info.get("vod_director"), "")),
        "vod_remarks": _clean(_first(info.get("vod_remarks"), "")),
    }
    if froms:
        item["vod_play_from"] = "$$$".join(froms)
        item["vod_play_url"] = "$$$".join(urls)

    return json.dumps({"list": [item]}, ensure_ascii=False)


# ---------------- 播放 ----------------
def _find_co4k_api():
    """llIlI11lIII1l：从 detail 缓存里找 code=CO4K 的 parse_secret"""
    for arr in list(_DETAIL_CACHE.values()):
        if not isinstance(arr, list):
            continue
        for p in arr:
            if isinstance(p, dict) and _opt_str(p, "code") == "CO4K":
                ps = _opt_str(p, "parse_secret")
                if ps.startswith("http"):
                    return ps
    return ""


def _parse_get(api, media):
    """lllII11Il11ll：api + URLEncoder(media)，取回直链"""
    if not api or not media:
        return ""
    try:
        url = str(api) + urllib.parse.quote(str(media), safe="").replace("+", "%20")
        req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
        text = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore").strip()
    except Exception:
        return ""
    if text.lower().startswith("http"):
        sp = text.find(" ")
        return text[:sp] if sp > 0 else text
    try:
        obj = json.loads(text)
    except Exception:
        return ""
    if not isinstance(obj, dict):
        return ""
    for k in ("url", "play_url", "m3u8", "vod_url"):
        v = obj.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
    d = obj.get("data")
    if isinstance(d, dict):
        for k in ("url", "play_url", "m3u8", "vod_url"):
            v = d.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v
    return ""


def playerContent(flag, id, vipFlags):
    s = (id or "").strip()
    if not s:
        return json.dumps({"parse": 0, "url": ""}, ensure_ascii=False)

    url, api = s, ""
    if s.startswith("av7:"):
        try:
            meta = json.loads(_b64d(s[4:]).decode("utf-8", "ignore"))
            url = str(meta.get("url") or "")
            api = str(meta.get("parse") or meta.get("secret") or "")
        except Exception:
            url, api = s, ""
    else:
        pos = s.find("@")
        if 0 < pos < len(s) - 1 and s[pos + 1:].lower().startswith("http"):
            url, api = s[:pos], s[pos + 1:]

    if not url:
        return json.dumps({"parse": 0, "url": ""}, ensure_ascii=False)
    header = json.dumps({"User-Agent": BROWSER_UA})

    if _is_media(url):
        return json.dumps({"parse": 0, "url": url, "header": header}, ensure_ascii=False)

    if not api and not url.lower().startswith("http"):
        api = _find_co4k_api()

    real = _parse_get(api, url) if api else ""
    if not real and not url.lower().startswith("http"):
        co = _find_co4k_api()
        if co and co != api:
            real = _parse_get(co, url)
    if real:
        return json.dumps({"parse": 0, "url": real, "header": header}, ensure_ascii=False)

    # 解析不出：交给客户端解析（与 JAR 一致 parse=1）
    return json.dumps({"parse": 1, "url": url, "header": header}, ensure_ascii=False)


# ---------------- 搜索 ----------------
def searchContent(key, quick, pg="1"):
    text = (key or "").strip()
    if not text:
        return json.dumps({"list": []}, ensure_ascii=False)
    page = max(1, _to_int(pg, 1))
    obj = _post("search", {"text": text, "pg": page})
    arr = obj.get("data") if isinstance(obj.get("data"), list) else []
    out = []
    for v in arr:
        if not isinstance(v, dict):
            continue
        vd = _map_vod(v)
        vd["type_name"] = _clean(_first(v.get("type_name"), v.get("vod_class")))
        vd["vod_director"] = _clean(_opt_str(v, "vod_director"))
        vd["vod_actor"] = _clean(_opt_str(v, "vod_actor"))
        if _kw_match(vd, text):
            out.append(vd)
    return json.dumps({"list": out}, ensure_ascii=False)


def _kw_match(vod, key):
    """搜索优化：只匹配 片名/分类/导演/演员（排除简介）"""
    key = (key or "").strip().lower()
    if not key:
        return True
    hay = " ".join([
        str(vod.get("vod_name", "")),
        str(vod.get("type_name", "")),
        str(vod.get("vod_director", "")),
        str(vod.get("vod_actor", "")),
    ]).lower()
    return key in hay


# ---------------- class 入口（OK影视 / 影视仓 python 运行时） ----------------
class Spider(BaseSpider):
    """运行时只识别 class Spider；module 级同名函数保留，方法内部转发过去"""

    def __init__(self, *args, **kwargs):
        try:
            super(Spider, self).__init__()
        except Exception:
            pass
        self.extend = ""

    def getName(self):
        return "蒙太奇"

    def init(self, extend=""):
        init(extend)

    def homeContent(self, filter):
        return json.loads(homeContent(filter))

    def homeVideoContent(self):
        return {"list": _rec_list()}

    def categoryContent(self, tid, pg, filter, extend):
        return json.loads(categoryContent(tid, pg, filter, extend))

    def detailContent(self, ids):
        return json.loads(detailContent(ids))

    def searchContent(self, key, quick, pg="1"):
        return json.loads(searchContent(key, quick, pg))

    def searchContentPage(self, key, quick, pg):
        return json.loads(searchContent(key, quick, pg))

    def playerContent(self, flag, id, vipFlags=None):
        return json.loads(playerContent(flag, id, vipFlags))

    def isVideoFormat(self, url):
        return _is_media(url)

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return None

    def destroy(self):
        pass
