# -*- coding: utf-8 -*-
"""猫果（七猫短剧）独立源。

复刻自本项目根目录 短剧聚合.py 中的 _Maoguo 实现（qm-params + MD5 签名）。
"""

import base64
import gzip
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

PC_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


# ---------------- 基础小工具 ----------------

def _s(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else ""
    return str(v).strip()


def _pick(d, *keys):
    if not isinstance(d, dict):
        return ""
    for k in keys:
        v = d.get(k)
        if v is None or v is False:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _pick_int(d, *keys):
    if not isinstance(d, dict):
        return 0
    for k in keys:
        v = d.get(k)
        try:
            n = int(float(str(v).strip()))
            if n:
                return n
        except Exception:
            continue
    return 0


_EP_PATTERNS = [
    re.compile(r"第\s*0*(\d+)\s*[集话期]"),
    re.compile(r"(?:更新至|共|全)\s*0*(\d+)\s*[集话期]"),
    re.compile(r"(?i)(?:episode|ep)\s*#?\s*0*(\d+)"),
]


def _ep_no(title, default=0):
    t = _s(title)
    for p in _EP_PATTERNS:
        m = p.search(t)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
    return default


def _q(s):
    return urllib.parse.quote(_s(s), safe="")


def _uq(s):
    return urllib.parse.unquote(_s(s))


def _md5(s):
    if isinstance(s, str):
        s = s.encode("utf-8")
    return hashlib.md5(s).hexdigest()


# ---------------- HTTP 层 ----------------
# urllib 主用；Python 栈被目标按 TLS 指纹丢弃时，回落 App 自带 OkHttp（真机）。

_JAVA_CLIENT = [None]


def _java_client():
    if _JAVA_CLIENT[0] is not None:
        return _JAVA_CLIENT[0] or None
    try:
        from java import jclass
        Builder = jclass("okhttp3.OkHttpClient$Builder")
        TimeUnit = jclass("java.util.concurrent.TimeUnit")
        b = Builder()
        b.followRedirects(True)
        b.followSslRedirects(True)
        b.connectTimeout(12, TimeUnit.SECONDS)
        b.readTimeout(30, TimeUnit.SECONDS)
        b.writeTimeout(12, TimeUnit.SECONDS)
        _JAVA_CLIENT[0] = b.build()
    except Exception:
        _JAVA_CLIENT[0] = False
    return _JAVA_CLIENT[0] or None


def _java_fetch(url, headers=None, data=None):
    """返回 (status, headers_dict, body)；失败返回 None。"""
    client = _java_client()
    if client is None:
        return None
    try:
        from java import jclass
        ReqBuilder = jclass("okhttp3.Request$Builder")
        rb = ReqBuilder()
        rb.url(str(url))
        ctype = "application/x-www-form-urlencoded"
        for k, v in (headers or {}).items():
            lk = str(k).lower()
            if lk == "content-type":
                ctype = str(v)
                continue
            if lk in ("content-length", "host", "cookie"):
                continue
            try:
                rb.header(str(k), str(v))
            except Exception:
                pass
        if data is not None:
            MediaType = jclass("okhttp3.MediaType")
            RequestBody = jclass("okhttp3.RequestBody")
            rb.post(RequestBody.create(MediaType.parse(ctype), bytes(data)))
        resp = client.newCall(rb.build()).execute()
        code = 0
        try:
            code = int(resp.code())
        except Exception:
            pass
        h = {}
        try:
            mm = resp.headers().toMultimap()
            for e in mm.entrySet():
                vals = []
                try:
                    for v in e.getValue():
                        vals.append(str(v))
                except Exception:
                    pass
                h[str(e.getKey()).lower()] = vals
        except Exception:
            pass
        out = b""
        try:
            bd = resp.body()
            if bd is not None:
                out = bytes(bd.bytes())
        except Exception:
            pass
        try:
            resp.close()
        except Exception:
            pass
        return code, h, out
    except Exception:
        return None


class _Resp(object):
    def __init__(self):
        self.status = 0
        self.headers = {}
        self.body = b""
        self.url = ""

    def text(self, encoding="utf-8"):
        return self.body.decode(encoding, "ignore")


def _parse_set_cookies(header_vals, jar):
    for hv in header_vals or []:
        part = _s(hv).split(";", 1)[0]
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip()
            if k:
                jar[k] = v.strip()


class _Session(object):
    """带 Cookie 罐的会话；fetch 返回 _Resp。"""

    def __init__(self):
        self.cookies = {}
        self._lock = threading.Lock()

    def _cookie_header(self):
        with self._lock:
            items = ["%s=%s" % (k, v) for k, v in self.cookies.items()]
        return "; ".join(items)

    def fetch(self, url, method="GET", headers=None, data=None,
              timeout=12, max_body=8 << 20):
        headers = dict(headers or {})
        ck = self._cookie_header()
        if ck and "cookie" not in {k.lower(): 1 for k in headers}:
            headers["Cookie"] = ck
        if "user-agent" not in {k.lower(): 1 for k in headers}:
            headers["User-Agent"] = PC_UA
        resp = _Resp()
        resp.url = url
        # 1) urllib
        try:
            req = urllib.request.Request(url, data=data, headers=headers,
                                         method=method.upper())
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp.status = r.status
                raw_h = {}
                try:
                    for k, v in r.headers.items():
                        raw_h.setdefault(k.lower(), []).append(v)
                except Exception:
                    pass
                resp.headers = raw_h
                body = r.read(max_body + 1)
                if len(body) > max_body:
                    raise ValueError("body too large")
                resp.body = body
                try:
                    resp.url = r.geturl()
                except Exception:
                    pass
        except Exception:
            # 2) 真机 OkHttp 回退
            jr = _java_fetch(url, headers=headers, data=data)
            if not jr:
                raise
            resp.status, resp.headers, resp.body = jr
            if len(resp.body) > max_body:
                raise ValueError("body too large")
        _parse_set_cookies(resp.headers.get("set-cookie"), self.cookies)
        # 部分站点不看 Accept-Encoding 直接发 gzip/deflate，中央解压
        try:
            enc = [_s(x).lower() for x in resp.headers.get(
                "content-encoding", [])]
            if resp.body[:2] == b"\x1f\x8b" or any(
                    "gzip" in x for x in enc):
                resp.body = gzip.decompress(bytes(resp.body))
            elif resp.body[:2] == b"\x78\x9c" or any(
                    "deflate" in x for x in enc):
                import zlib
                resp.body = zlib.decompress(bytes(resp.body))
        except Exception:
            pass
        return resp

    def get_text(self, url, headers=None, timeout=12):
        return self.fetch(url, headers=headers, timeout=timeout).text()

    def get_json(self, url, headers=None, timeout=12):
        return json.loads(self.fetch(url, headers=headers,
                                     timeout=timeout).text())


# ---------------- 站源框架 ----------------

class _SrcErr(Exception):
    """站源级可预期错误（接口变化/失效/加密等），Spider 会隔离。"""
    pass


def _tid(src, cat):
    return "%s::c::%s" % (src, _q(cat))


def _did(src, sid):
    return "%s::d::%s" % (src, _q(sid))


def _pid(src, sid, ep):
    return "%s::p::%s::%s" % (src, _q(sid), _q(ep))


def _split_tid(tid):
    head, _, cat = _s(tid).partition("::c::")
    return head, _uq(cat)


def _split_did(did):
    head, _, sid = _s(did).partition("::d::")
    return head, _uq(sid)


def _split_pid(pid):
    s = _s(pid)
    head, _, rest = s.partition("::p::")
    sid, _, ep = rest.partition("::")
    return head, _uq(sid), _uq(ep)


def _vod_item(src_id, sid, title, pic="", remark="", content=""):
    return {
        "vod_id": _did(src_id, sid),
        "vod_name": _s(title),
        "vod_pic": _s(pic),
        "vod_remarks": _s(remark),
        "vod_content": _s(content),
    }


def _vod_detail(src, sid, title, pic="", remark="", content="",
                year="", area="", actor="", chapters=()):
    """chapters: [(epkey, eptitle)]"""
    play_url = "#".join(
        "%s$%s" % (_s(t) or ("第%d集" % (i + 1)), _pid(src.id, sid, k))
        for i, (k, t) in enumerate(chapters))
    return {
        "vod_id": _did(src.id, sid),
        "vod_name": _s(title),
        "vod_pic": _s(pic),
        "vod_remarks": _s(remark),
        "vod_content": _s(content),
        "vod_year": _s(year),
        "vod_area": _s(area),
        "vod_actor": _s(actor),
        "vod_play_from": src.name,
        "vod_play_url": play_url,
    }


class _Src(object):
    id = ""
    name = ""
    cats = [("", "推荐")]  # [(catid, catname)] 静态分类

    def __init__(self):
        self.sess = _Session()

    # -- 以下按需覆盖 --
    def home(self, pg):
        """返回 (items, has_more)。"""
        return self.cat("", pg)

    def cat(self, catid, pg):
        raise _SrcErr("本站源暂无目录")

    def detail(self, sid):
        raise _SrcErr("本站源暂无详情")

    def play(self, sid, ep):
        """返回 (media_url, headers_dict)。"""
        raise _SrcErr("本站源暂无播放")

    def search(self, key, pg):
        raise _SrcErr("本站源不支持搜索")


_SOURCES = []


def _register(cls):
    _SOURCES.append(cls())
    return cls


def _find_src(src_id):
    for s in _SOURCES:
        if s.id == src_id:
            return s
    return None


# ============================================================
# 猫果（七猫签名）— qm-params + MD5，参数顺序必须与原版一致
# ============================================================
@_register
class _Maoguo(_Src):
    id = "maoguo"
    name = "猫果"
    cats = [("0", "推荐")]
    STORE = "https://api-store.qmplaylet.com"
    READ = "https://api-read.qmplaylet.com"
    KEY = "d3dGiJc651gSQ8w1"
    TRACK_ID = "ec1280db127955061754851657967"
    # 与 Go 源码 duanjuMaoguoCharMap 逐字一致（'=' 不在表中，保持原样）
    CHARMAP = {
        '+': 'P', '/': 'X', '0': 'M', '1': 'U', '2': 'l', '3': 'E',
        '4': 'r', '5': 'Y', '6': 'W', '7': 'b', '8': 'd', '9': 'J',
        'A': '9', 'B': 's', 'C': 'a', 'D': 'I', 'E': '0', 'F': 'o',
        'G': 'y', 'H': '_', 'I': 'H', 'J': 'G', 'K': 'i', 'L': 't',
        'M': 'g', 'N': 'N', 'O': 'A', 'P': '8', 'Q': 'F', 'R': 'k',
        'S': '3', 'T': 'h', 'U': 'f', 'V': 'R', 'W': 'q', 'X': 'C',
        'Y': '4', 'Z': 'p', 'a': 'm', 'b': 'B', 'c': 'O', 'd': 'u',
        'e': 'c', 'f': '6', 'g': 'K', 'h': 'x', 'i': '5', 'j': 'T',
        'k': '-', 'l': '2', 'm': 'z', 'n': 'S', 'o': 'Z', 'p': '1',
        'q': 'V', 'r': 'v', 's': 'j', 't': 'Q', 'u': '7', 'v': 'D',
        'w': 'w', 'x': 'n', 'y': 'L', 'z': 'e',
    }

    def __init__(self):
        super().__init__()
        self._dyn_cats = None

    def _headers(self):
        payload = {
            "static_score": "0.8",
            "uuid": "00000000-7fc7-08dc-0000-000000000000",
            "device-id": "20250220125449b9b8cac84c2dd3d035c9052a2572f7dd0122edde3cc42a70",
            "mac": "",
            "sourceuid": "aa7de295aad621a6",
            "refresh-type": "0",
            "model": "22021211RC",
            "wlb-imei": "",
            "client-id": "aa7de295aad621a6",
            "brand": "Redmi",
            "oaid": "",
            "oaid-no-cache": "",
            "sys-ver": "12",
            "trusted-id": "",
            "phone-level": "H",
            "imei": "",
            "wlb-uid": "aa7de295aad621a6",
            "session-id": str(int(time.time() * 1000)),
        }
        b64 = base64.b64encode(
            json.dumps(payload, separators=(",", ":")).encode()).decode()
        qm = "".join(self.CHARMAP.get(c, c) for c in b64)
        sign = _md5("AUTHORIZATION=" + "app-version=10001" +
                    "application-id=com.duoduo.read" + "channel=unknown" +
                    "is-white=" + "net-env=5" + "platform=android" +
                    "qm-params=" + qm + "reg=" + self.KEY)
        return {
            "net-env": "5", "reg": "", "channel": "unknown", "is-white": "",
            "platform": "android", "application-id": "com.duoduo.read",
            "authorization": "", "app-version": "10001",
            "User-Agent": "webviewversion/0",
            "qm-params": qm, "sign": sign,
            "Accept": "application/json",
            "X-Requested-With": "com.duoduo.read",
        }

    def _get(self, base, path, sign_str):
        url = base + path + ("&" if "?" in path else "?") + "sign=" + sign_str
        return self.sess.get_json(url, headers=self._headers(), timeout=12)

    def categories(self):
        if self._dyn_cats is not None:
            return self._dyn_cats
        try:
            j = self._get(self.STORE, "/api/v1/playlet/tag/list?operation=1",
                          _md5("operation=1" + self.KEY))
            cats = []
            for c in (j.get("data") or {}).get("list") or []:
                cid = _pick(c, "tag_id", "id")
                cn = _pick(c, "tag_name", "name", "title")
                if cid and cn:
                    cats.append((cid, cn))
            if cats:
                self._dyn_cats = cats[:24]
                return self._dyn_cats
        except Exception:
            pass
        return self.cats

    def _node(self, n):
        vid = _pick(n, "playlet_id", "playletId", "id")
        if not vid:
            return None
        total = _pick_int(n, "total_episode_num", "totalEpisodeNum", "total")
        tags = n.get("tags") or n.get("tag_list") or []
        cat = ",".join(_s(t) for t in tags if _s(t))[:60]
        v = _vod_item(
            self.id, vid, _pick(n, "title", "playlet_name", "name"),
            _pick(n, "image_link", "imageLink", "cover", "cover_url"),
            ("全%d集" % total) if total else "",
            _pick(n, "intro", "description", "desc"))
        if cat:
            v["vod_remarks"] = (v["vod_remarks"] + " " + cat).strip()
        return v

    def cat(self, catid, pg):
        catid = _s(catid) or "0"
        if not catid.isdigit():
            catid = "0"
        if pg > 1:
            sign = _md5("next_id=%doperation=1playlet_privacy=1tag_id=%s%s"
                        % (pg, catid, self.KEY))
            path = ("/api/v1/playlet/index?tag_id=%s&playlet_privacy=1"
                    "&operation=1&next_id=%d" % (catid, pg))
        else:
            sign = _md5("operation=1playlet_privacy=1tag_id=%s%s"
                        % (catid, self.KEY))
            path = ("/api/v1/playlet/index?tag_id=%s&playlet_privacy=1"
                    "&operation=1" % catid)
        j = self._get(self.STORE, path, sign)
        rows = (j.get("data") or {}).get("list") or []
        items = [v for v in (self._node(n) for n in rows) if v]
        more = len(items) > 0 if pg > 1 else False
        return items, more

    def home(self, pg):
        return self.cat("0", pg)

    def detail(self, sid):
        sign = _md5("playlet_id=" + sid + self.KEY)
        j = self._get(self.READ, "/player/api/v1/playlet/info?playlet_id="
                      + _q(sid), sign)
        data = j.get("data") or {}
        v = self._node(data) or _vod_item(self.id, sid, sid)
        v["vod_content"] = _pick(data, "intro", "description", "desc")
        chapters = []
        for i, e in enumerate(data.get("play_list") or []):
            u = _pick(e, "video_url", "videoUrl", "url")
            if not u:
                continue
            no = _pick_int(e, "sort", "episode", "index") or (i + 1)
            t = _pick(e, "title", "name") or ("第%d集" % no)
            chapters.append((u, t))
        chapters.sort(key=lambda x: _ep_no(x[1]))
        v.update({
            "vod_remarks": ("全%d集" % len(chapters)) if chapters else "",
            "vod_play_from": self.name,
            "vod_play_url": "#".join(
                "%s$%s" % (t, _pid(self.id, sid, k)) for k, t in chapters),
        })
        return v

    def play(self, sid, ep):
        if not _s(ep).startswith("http"):
            raise _SrcErr("猫果分集地址无效")
        return _s(ep), {}

    def search(self, key, pg):
        # 顺序敏感：extend,page,read_preference,track_id,wd
        sign = _md5("extend=page=1read_preference=0track_id=%swd=%s%s"
                    % (self.TRACK_ID, key, self.KEY))
        path = ("/api/v1/playlet/search?extend=&page=1&wd=%s"
                "&read_preference=0&track_id=%s" % (_q(key), self.TRACK_ID))
        j = self._get(self.STORE, path, sign)
        data = j.get("data") or {}
        rows = data.get("list") or []
        items = [v for v in (self._node(n) for n in rows) if v]
        return items, False


# ============================================================
# Spider 主类（FongMi 5.6.4 / Chaquopy 合约：全部返回 dict）
# ============================================================
class Spider(BaseSpider):

    def getName(self):
        return "猫果"

    def init(self, extend=""):
        self.extend = _s(extend)
        return {}

    def destroy(self):
        return {}

    def isVideoFormat(self, url):
        u = _s(url).lower()
        return (".m3u8" in u or ".mp4" in u or ".flv" in u or ".ts" in u
                or ".mkv" in u)

    def manualVideoCheck(self):
        return False

    # ---------- 首页 ----------
    def _source_cats(self, src):
        try:
            if hasattr(src, "categories"):
                cats = src.categories()
                if cats:
                    return cats[:24]
        except Exception:
            pass
        return src.cats or [("", "推荐")]

    def homeContent(self, filter=False):
        # 大分类=站源名（顶部 tab）；子分类=站源自己的分类，走 filters 二级筛选栏。
        cats_map = {}
        for src in _SOURCES:
            try:
                cats_map[src.id] = self._source_cats(src)
            except Exception:
                cats_map[src.id] = src.cats or [("", "推荐")]
        classes, filters = [], {}
        for src in _SOURCES:
            tid = _tid(src.id, "")
            classes.append({"type_id": tid, "type_name": src.name})
            subs = cats_map.get(src.id) or src.cats or [("", "推荐")]
            opts, seen_n = [], set()
            for cid, cname in subs[:30]:
                if not cname or cname in seen_n:
                    continue
                seen_n.add(cname)
                opts.append({"n": cname, "v": cid})
            groups = []
            if opts:
                groups.append({"key": "cat", "name": "分类", "value": opts})
            if groups:
                filters[tid] = groups
        vods = []
        try:
            items, _ = _SOURCES[0].home(1)
            vods = items[:24]
        except Exception:
            pass
        return {"class": classes, "list": vods, "filters": filters}

    def homeVideoContent(self):
        try:
            items, _ = _SOURCES[0].home(1)
            return {"list": items[:24]}
        except Exception:
            return {"list": []}

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        src_id, _ = _split_tid(tid)
        src = _find_src(src_id)
        if not src:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 20,
                    "total": 0}
        try:
            pg = max(1, int(pg))
        except Exception:
            pg = 1
        # 子分类来自 filters 二级筛选：extend = {"cat": <cid>}
        cat = ""
        ext = extend
        if isinstance(ext, str) and ext:
            try:
                ext = json.loads(ext)
            except Exception:
                ext = {}
        if isinstance(ext, dict):
            cat = _s(ext.get("cat", ""))
        if cat:
            # 兼容 FongMi 传显示名而不是 id 的情况
            try:
                cats = self._source_cats(src)
                if cat not in set(c[0] for c in cats):
                    by_name = dict((c[1], c[0]) for c in cats)
                    cat = by_name.get(cat, "")
            except Exception:
                pass
        if not cat:
            try:
                cats = self._source_cats(src)
                cat = cats[0][0] if cats else ""
            except Exception:
                cat = ""
        try:
            items, more = src.cat(cat, pg)
        except _SrcErr:
            items, more = [], False
        except Exception:
            items, more = [], False
        return {"list": items or [], "page": pg,
                "pagecount": 9999 if more else pg,
                "limit": 20, "total": 999999 if more else len(items or [])}

    # ---------- 详情 ----------
    def detailContent(self, ids):
        did = ids[0] if ids else ""
        src_id, sid = _split_did(did)
        src = _find_src(src_id)
        if not src:
            return {"list": []}
        try:
            vod = src.detail(sid)
        except _SrcErr as e:
            vod = _vod_detail(src, sid, "加载失败", "",
                              "", "原因：%s" % e, chapters=())
            vod["vod_id"] = did
        except Exception as e:
            vod = _vod_detail(src, sid, "加载失败", "",
                              "", "原因：%s" % type(e).__name__,
                              chapters=())
            vod["vod_id"] = did
        return {"list": [vod]}

    # ---------- 搜索 ----------
    def searchContent(self, key, quick=False, pg="1"):
        key = _s(key).strip()
        if not key:
            return {"list": []}
        out = []
        for src in _SOURCES:
            try:
                items, _ = src.search(key, 1)
            except Exception:
                items = []
            for v in (items or [])[:12]:
                if not v["vod_name"].startswith(src.name):
                    v["vod_name"] = "[%s] %s" % (src.name, v["vod_name"])
                out.append(v)
        return {"list": out}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags=None):
        src_id, sid, ep = _split_pid(id)
        src = _find_src(src_id)
        if not src:
            return {"parse": 0, "playUrl": "", "url": "", "header": {}}
        try:
            url, header = src.play(sid, ep)
        except _SrcErr:
            return {"parse": 0, "playUrl": "", "url": "", "header": {}}
        except Exception:
            return {"parse": 0, "playUrl": "", "url": "", "header": {}}
        return {"parse": 0, "playUrl": "", "url": _s(url),
                "header": dict(header or {})}
