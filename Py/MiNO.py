# -*- coding: utf-8 -*-
"""TVBox Python Spider - MiNO (self-contained)"""
import sys, json
sys.path.append("..")
from base.spider import Spider

# ============ BEGIN ORIGINAL SOURCE ============
# -*- coding: utf-8 -*-
# TVBox Python Spider - MiNO 秒播4K
# 对齐 1109.jar -> csp_MiNO
# 说明：原版 init 需要 client_pub(EC 公钥) 走加密通道；
#       不带 client_pub 时服务端返回明文并提供 sign_key，效果一致。

import json
import time
import uuid
import base64
import binascii
import urllib.request
import urllib.parse

DEFAULT_BASE = "http://43.248.128.122:578"

CATS = [("1", "电影"), ("2", "连续剧"), ("3", "综艺"), ("4", "动漫"),
        ("20", "短剧"), ("21", "少儿"), ("22", "漫剧"), ("23", "纪录片")]

SORTS = [("", "默认"), ("hits", "最热"), ("score", "评分")]
AREAS = [("", "全部"), ("内地", "内地"), ("中国香港", "中国香港"), ("中国台湾", "中国台湾"),
         ("美国", "美国"), ("韩国", "韩国"), ("日本", "日本"), ("英国", "英国"),
         ("法国", "法国"), ("泰国", "泰国"), ("印度", "印度")]
LANGS = [("", "全部"), ("国语", "国语"), ("英语", "英语"), ("日语", "日语"),
         ("韩语", "韩语"), ("粤语", "粤语")]

BASE = DEFAULT_BASE
DEVICE_ID = ""
PAGE_SIZE = 20
SESSION = ""
EXPIRE_AT = 0
UA = "okhttp/4.12.0"

# token -> episode index ; code -> [tokens]（用于换线路回退）
_EP_INDEX = {}
_CODE_TOKENS = {}


def _qs(params):
    parts = []
    for k, v in params.items():
        if v is None or v == "":
            continue
        parts.append(urllib.parse.quote(str(k)) + "=" + urllib.parse.quote(str(v)))
    return "&".join(parts)


def _http(url, body=None, headers=None, timeout=20):
    h = {"User-Agent": UA}
    if body is not None:
        h["Content-Type"] = "application/json"
    if headers:
        h.update(headers)
    data = body.encode("utf-8") if isinstance(body, str) else body
    req = urllib.request.Request(url, data=data, headers=h,
                                 method="POST" if data is not None else "GET")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.read().decode("utf-8", "replace")
    except Exception as e:
        print("[MiNO] http error:", e)
        return ""


def _api_headers():
    h = {"User-Agent": UA}
    if SESSION:
        h["X-Session-Id"] = SESSION
    if DEVICE_ID:
        h["X-Device-Id"] = DEVICE_ID
    return h


def _gen_device_id():
    return uuid.uuid4().hex[:16]


def _ensure_session(force=False):
    global SESSION, EXPIRE_AT
    if not force and SESSION and time.time() * 1000 < EXPIRE_AT:
        return True
    SESSION = ""
    EXPIRE_AT = 0
    body = json.dumps({
        "platform": "android",
        "version": "1.0.13",
        "device_id": DEVICE_ID,
        "sig_src": "java",
        "so_version": 13,
    }, separators=(",", ":"))
    txt = _http(BASE + "/api/v1/security/init", body, {"User-Agent": UA, "Content-Type": "application/json"})
    try:
        data = json.loads(txt).get("data") or {}
    except Exception:
        return False
    sid = data.get("session_id") or ""
    if not sid:
        return False
    SESSION = sid
    exp = int(data.get("expires_in") or 600)
    EXPIRE_AT = int(time.time() * 1000) + max(60, exp - 30) * 1000
    return True


def _get_json(path, params=None):
    _ensure_session()
    url = BASE + path
    if params:
        url += "?" + _qs(params)
    txt = _http(url, None, _api_headers())
    try:
        return json.loads(txt)
    except Exception:
        return {}


def _to_list(arr):
    out = []
    for item in arr or []:
        if not isinstance(item, dict):
            continue
        tname = item.get("type_name") or item.get("vod_class") or ""
        out.append({
            "vod_id": str(item.get("vod_id", "")),
            "vod_name": item.get("vod_name", ""),
            "vod_pic": item.get("vod_pic", ""),
            "vod_remarks": item.get("vod_remarks", ""),
            "vod_year": item.get("vod_year", ""),
            "vod_area": item.get("vod_area", ""),
            "vod_actor": item.get("vod_actor", ""),
            "type_name": tname,
        })
    return out


def init(ext):
    global BASE, DEVICE_ID, PAGE_SIZE
    if ext:
        ext = ext.strip()
        if ext.startswith("{"):
            try:
                cfg = json.loads(ext)
                base = (cfg.get("base") or "").rstrip("/")
                if base:
                    BASE = base
                did = cfg.get("device_id") or ""
                if did:
                    DEVICE_ID = did
                PAGE_SIZE = max(5, int(cfg.get("page_size") or 20))
            except Exception:
                pass
    if not DEVICE_ID:
        DEVICE_ID = _gen_device_id()
    _ensure_session(True)


def homeContent(filter):
    flt = [
        {"key": "sort", "name": "排序", "value": [{"n": n, "v": v} for v, n in SORTS]},
        {"key": "area", "name": "地区", "value": [{"n": n, "v": v} for v, n in AREAS]},
        {"key": "year", "name": "年份",
         "value": [{"n": "全部", "v": ""}] + [{"n": str(y), "v": str(y)} for y in range(2026, 2009, -1)]},
        {"key": "lang", "name": "语言", "value": [{"n": n, "v": v} for v, n in LANGS]},
    ]
    classes = [{"type_id": tid, "type_name": name} for tid, name in CATS]
    data = _get_json("/api/v1/category/videos",
                     {"type_id": "2", "page": "1", "page_size": str(PAGE_SIZE)})
    d = data.get("data") or {}
    return {"class": classes, "filters": {tid: flt for tid, _ in CATS},
            "list": _to_list(d.get("videos"))}


def categoryContent(tid, pg, filter, extend):
    page = 1
    try:
        page = max(1, int(pg))
    except Exception:
        pass
    params = {"type_id": tid, "page": str(page), "page_size": str(PAGE_SIZE)}
    if extend:
        for k in ("sort", "area", "year", "lang", "class"):
            v = extend.get(k)
            if v and v != "全部":
                params[k] = v
    data = _get_json("/api/v1/category/videos", params)
    d = data.get("data") or {}
    pgobj = d.get("pagination") or {}
    pc = int(pgobj.get("total_pages") or page) or page
    total = int(pgobj.get("total") or 0)
    return {"page": page, "pagecount": pc, "limit": PAGE_SIZE, "total": total,
            "list": _to_list(d.get("videos"))}


def detailContent(ids):
    if not ids:
        return {"list": []}
    vid = str(ids[0]).split(",")[0]
    _ensure_session()
    data = _get_json("/api/v1/video/detail", {"id": vid})
    info = (data.get("data") or {}).get("vod_info")
    if not info:
        return {"list": []}

    _EP_INDEX.clear()
    _CODE_TOKENS.clear()
    froms = []
    urls = []
    for src in info.get("vod_url_with_player") or []:
        name = src.get("name") or src.get("code") or ""
        code = src.get("code") or ""
        eps = []
        tokens = []
        for item in (src.get("url") or "").split("#"):
            if "$" not in item:
                continue
            ep_name, token = item.split("$", 1)
            if not ep_name or not token:
                continue
            eps.append(ep_name + "$" + code + "|" + token)
            _EP_INDEX[token] = len(tokens)
            tokens.append(token)
        if eps:
            froms.append(name)
            urls.append("#".join(eps))
            _CODE_TOKENS[code] = tokens

    blurb = info.get("vod_blurb") or info.get("vod_content") or ""
    result = {
        "vod_id": vid,
        "vod_name": info.get("vod_name", ""),
        "vod_pic": info.get("vod_pic", ""),
        "vod_remarks": info.get("vod_remarks", ""),
        "vod_actor": info.get("vod_actor", ""),
        "vod_director": info.get("vod_director", ""),
        "vod_year": info.get("vod_year", ""),
        "vod_area": info.get("vod_area", ""),
        "type_name": info.get("vod_class", ""),
        "vod_content": blurb,
        "vod_play_from": "$$$".join(froms),
        "vod_play_url": "$$$".join(urls),
    }
    return {"list": [result]}


def _ticket(token, retry=True):
    _ensure_session()
    body = json.dumps({"token": token}, separators=(",", ":"))
    txt = _http(BASE + "/api/v1/vod/ticket", body, _api_headers())
    try:
        j = json.loads(txt)
    except Exception:
        return ""
    if j.get("code") == 1:
        return (j.get("data") or {}).get("ticket") or ""
    if j.get("code") == 4805 and retry:
        global DEVICE_ID
        DEVICE_ID = _gen_device_id()
        if _ensure_session(True):
            return _ticket(token, False)
    return ""


def _b64json(s):
    s = s.replace("-", "+").replace("_", "/")
    s += "=" * ((4 - len(s) % 4) % 4)
    try:
        return json.loads(base64.b64decode(s).decode("utf-8", "replace"))
    except Exception:
        return None


def _resolve(token):
    if not token:
        return ""
    ticket = _ticket(token)
    if not ticket:
        return ""
    obj = _b64json(ticket.split(".")[0])
    if not obj:
        return ""
    d = obj.get("data") or {}
    parse_api = (d.get("parse_api") or "").replace("\\u00026", "&").replace("\u0016", "").strip()
    url = d.get("url") or ""
    if not parse_api or not url:
        return ""
    if parse_api.startswith("/"):
        req_url = BASE + parse_api + urllib.parse.quote(url, safe="")
    elif "{md5}" in parse_api:
        req_url = parse_api.replace("{md5}", url)
    elif "url=" in parse_api:
        req_url = parse_api + urllib.parse.quote(url, safe="")
    else:
        req_url = parse_api + urllib.parse.quote(url, safe="")

    txt = _http(req_url, None, _api_headers())
    if not txt:
        return ""
    t = txt.strip()
    if t.startswith("{"):
        try:
            return json.loads(t).get("url") or ""
        except Exception:
            return ""
    if t.startswith("http"):
        return t
    return ""


def playerContent(flag, id, vipFlags):
    vid = id or ""
    code = ""
    if "|" in vid:
        code, vid = vid.split("|", 1)
    if vid.startswith("http"):
        return {"parse": 0, "playUrl": "", "url": vid}

    url = _resolve(vid)

    if not url and code:
        idx = _EP_INDEX.get(vid)
        if idx is not None:
            for other, tokens in _CODE_TOKENS.items():
                if other == code or idx >= len(tokens):
                    continue
                url = _resolve(tokens[idx])
                if url:
                    break

    if not url:
        return {"parse": 0, "playUrl": "", "url": ""}
    return {"parse": 0, "playUrl": "", "url": url,
            "header": json.dumps({"User-Agent": UA}, ensure_ascii=False)}


def _kw_match(vod, key):
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


def searchContent(key, quick, pg="1"):
    page = 1
    try:
        page = max(1, int(pg))
    except Exception:
        pass
    data = {}
    for delay in (0, 2, 4, 8, 12):
        if delay:
            time.sleep(delay)
        data = _get_json("/api/v1/search", {"wd": key, "page": str(page)})
        if data.get("code") == 1:
            break
        msg = (data.get("msg") or "").lower()
        if "频繁" not in msg and "rate" not in msg:
            break
    d = data.get("data") or {}
    pc = int(d.get("total_pages") or page) or page
    vlist = [v for v in _to_list(d.get("hits")) if _kw_match(v, key)]
    return {"page": page, "pagecount": pc, "limit": PAGE_SIZE,
            "total": int(d.get("total") or 0), "list": vlist}

# ============ END ORIGINAL SOURCE ============

class Spider(Spider):
    def init(self, extend=""):
        globals()["init"](extend)

    def homeContent(self, filter):
        ret = globals()["homeContent"](filter)
        if isinstance(ret, str):
            try: return json.loads(ret)
            except: return {"class": [], "list": [], "filters": {}}
        return ret

    def categoryContent(self, tid, pg, filter, extend):
        ret = globals()["categoryContent"](tid, pg, filter, extend)
        if isinstance(ret, str):
            try: return json.loads(ret)
            except: return {"list": [], "page": int(pg) if pg else 1, "pagecount": 1, "limit": 20, "total": 0}
        return ret

    def detailContent(self, ids):
        ret = globals()["detailContent"](ids)
        if isinstance(ret, str):
            try: return json.loads(ret)
            except: return {"list": []}
        return ret

    def searchContent(self, key, quick, pg="1"):
        ret = globals()["searchContent"](key, quick)
        if isinstance(ret, str):
            try: return json.loads(ret)
            except: return {"list": []}
        return ret

    def playerContent(self, flag, id, vipFlags):
        ret = globals()["playerContent"](flag, id, vipFlags)
        if isinstance(ret, str):
            try: return json.loads(ret)
            except: return {"parse": 0, "url": ""}
        return ret

    def liveContent(self, url):
        fn = globals().get("liveContent")
        if not fn:
            return ""
        ret = fn(url)
        if isinstance(ret, str):
            return ret
        return json.dumps(ret, ensure_ascii=False)
