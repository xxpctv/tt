# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   悦听吧 (YueTingBa)
# 播放: AES 解密 efi + 动态密钥 + md5 token (密钥串 |xMiP5W1DHBxC5PwQ5oj5QfRn0tsT5UBk)

from base.spider import Spider
import requests
import re
import json
import hashlib
import time
import base64
from urllib.parse import quote
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

SITE = "http://www.yuetingba.cn"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
KEY_CFG = base64.b64decode("le95G3hnFDJsBE+1/v9eYw==")
IV_CFG = base64.b64decode("IvswQFEUdKYf+d1wKpYLTg==")
SECRET = "|xMiP5W1DHBxC5PwQ5oj5QfRn0tsT5UBk"
CATES = [["latest", "最新"], ["recommend", "推荐"], ["1", "玄幻"], ["4", "都市"], ["2", "历史"],
         ["6", "名著"], ["7", "女频"], ["5", "科幻"], ["3", "武侠"], ["a", "评书"], ["8", "社科"]]
RE_YEAR = re.compile(r"(?:19|20)\d{2}")


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def _abs(u):
    u = (u or "").strip()
    if not u:
        return SITE + "/"
    if u.startswith("//"):
        return "http:" + u
    if u.startswith("/"):
        return SITE + u
    if u.startswith("http"):
        return u
    return SITE + "/" + u


def _attr(html, name):
    m = re.search(name + r'\s*=\s*["\']([^"\']*)["\']', html or "")
    return m.group(1).strip() if m else ""


def _aes_decrypt(b64, key, iv):
    raw = base64.b64decode((b64 or "").replace("\n", "").strip())
    dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    return (dec.update(raw) + dec.finalize()).decode("utf-8", "ignore")


def _md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


class He:
    def __init__(self):
        self.a = ""   # bookId
        self.b = ""   # tingId
        self.c = ""   # tingTitle
        self.d = ""   # assl
        self.e = ""   # py
        self.a_list = None


def _js_var(html, name):
    m = re.search(r"var\s+" + re.escape(name) + r"\s*=\s*'([^']*)'", html or "")
    return m.group(1) if m else ""


def _digit(s, i):
    if 0 <= i < len(s) and s[i].isdigit():
        return int(s[i])
    return 0


def _dyn_key(uuid, date):
    s1 = uuid.replace("-", "")
    s2 = re.sub(r"[-:T. ]", "", date or "")
    while len(s2) < 20:
        s2 += "0"
    key = bytearray()
    for i in range(len(s1)):
        key.append(ord(s1[i]) + _digit(s2, i % 20))
    iv = bytearray()
    n3 = 20
    while n3 > 4:
        ch = s1[n3] if n3 < len(s1) else "0"
        iv.append(ord(ch) + _digit(s2, n3 - 1))
        n3 -= 1
    return bytes(key), bytes(iv)


class Spider(Spider):
    def __init__(self):
        super().__init__()
        self._he_cache = {}

    def getName(self):
        return "悦听吧"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _get(self, url, referer=""):
        hdrs = {"User-Agent": UA, "Accept": "*/*"}
        hdrs["Referer"] = referer or (SITE + "/")
        try:
            return requests.get(url, headers=hdrs, timeout=15).text
        except Exception:
            return ""

    # ---- 列表解析 ----
    def _parse_books(self, html):
        out, seen = [], set()
        # .section-box-list-item 块
        for m in re.finditer(r'class="section-box-list-item"', html or ""):
            start = m.start()
            nxt = html.find('class="section-box-list-item"', start + 1)
            seg = html[start:nxt if nxt > 0 else len(html)]
            am = re.search(r'<a[^>]+href="([^"]*book/detail/[^"]+)"', seg)
            if not am:
                continue
            href = _abs(am.group(1).split("?")[0])
            if href in seen:
                continue
            im = re.search(r"<img[^>]+>", seg)
            alt, pic = "", ""
            if im:
                alt = _attr(im.group(0), "alt")
                pic = _abs(_attr(im.group(0), "src"))
            name = ""
            tm = re.search(r'class="[^"]*box-list-item-text-title[^"]*"[^>]*>\s*<a[^>]*>([^<]*)</a>', seg)
            if tm:
                name = _text(tm.group(1))
            name = name or alt or _text(re.sub(r'^.*?<a[^>]+href="[^"]*book/detail/[^"]*"[^>]*>', '', seg, count=1))
            if not name:
                continue
            rm = re.search(r'class="[^"]*box-list-item-text-title[^"]*"[^>]*>\s*<a[^>]*>[^<]*</a>\s*(?:<[^>]+>)?\s*([^<]{1,60})', seg)
            remark = ""
            if rm:
                remark = _text(rm.group(1))
            if not remark:
                for cls in ("box-list-item-text-intro", "box-list-item-text-author", "box-list-item-text"):
                    rm2 = re.search(r'class="' + cls + r'"[^>]*>([^<]*)</', seg)
                    if rm2 and _text(rm2.group(1)):
                        remark = _text(rm2.group(1))
                        break
            seen.add(href)
            out.append({"vod_id": href, "vod_name": name, "vod_pic": pic, "vod_remarks": remark})
        if out:
            return out
        # 回退: 所有 book/detail 链接
        for m in re.finditer(r'<a[^>]+href="([^"]*book/detail/[^"]+)"[^>]*>([^<]*)</a>', html or ""):
            href = _abs(m.group(1).split("?")[0])
            name = _text(m.group(2))
            if href in seen or not name:
                continue
            seen.add(href)
            out.append({"vod_id": href, "vod_name": name, "vod_pic": "", "vod_remarks": ""})
        return out

    def homeContent(self, filter):
        result = {"class": [{"type_id": c[0], "type_name": c[1]} for c in CATES], "filters": {}}
        try:
            result["list"] = self._parse_books(self._get(SITE + "/top/latest/1"))
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        return self.categoryContent("latest", 1, False, {})

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            t = str(tid or "")
            if t == "recommend":
                path = f"/top/recommend/{pg}"
            elif t == "latest" or not t:
                path = f"/top/latest/{pg}"
            else:
                path = f"/book/{t}/{pg}"
            html = self._get(SITE + path)
            lst = self._parse_books(html)
            result["list"] = lst
            result["page"] = pg
            result["pagecount"] = pg if not lst else pg + 1
            result["total"] = 0x7FFFFFFF if lst else 0
        except Exception:
            pass
        return result

    # ---- 详情 ----
    def _parse_he(self, url, html):
        he = He()
        m = re.search(r"/book/detail/([^/]+)/", url or "")
        he.a = m.group(1) if m else _js_var(html, "bookId")
        he.b = _js_var(html, "tingId")
        he.c = _js_var(html, "tingTitle")
        he.d = _js_var(html, "assl")
        he.e = _js_var(html, "py")
        rest = he.d.replace("xMiP5W1DHBxC5PwQ5oj5QfRn0tsT5UBk", "")
        if rest.strip():
            try:
                he.a_list = json.loads(_aes_decrypt(rest, KEY_CFG, IV_CFG))
            except Exception:
                he.a_list = None
        return he

    def _o(self, html, label):
        for m in re.finditer(r"<li[^>]*>([\s\S]*?)</li>|<p[^>]*>([\s\S]*?)</p>|<div[^>]*>([\s\S]*?)</div>", html or ""):
            seg = m.group(0)
            t = _text(seg)
            if t.startswith(label + "：") or t.startswith(label + ":"):
                return _text(t[len(label) + 1:])
        return ""

    def _parse_eps(self, html, he):
        eps = {}
        for m in re.finditer(r'class="ting-list-content-item"[^>]*>([\s\S]*?)</(?:div|li|a)>', html or ""):
            seg = m.group(1)
            tid = ""
            im = re.search(r'id="(item_[\w-]+)"', seg)
            if im:
                tid = im.group(1)
            else:
                om = re.search(r"testFn\('([^']+)'\)", _attr(seg, "onclick"))
                if om:
                    tid = om.group(1)
            if not tid:
                continue
            tm = re.search(r'<a[^>]+title="([^"]*)"[^>]*>', seg)
            title = tm.group(1) if tm else ""
            if not title:
                tm = re.search(r'<a[^>]+onclick="[^"]*testFn[^"]*"[^>]*>([^<]*)</a>', seg)
                if tm:
                    title = _text(tm.group(1))
            title = _text(title)
            if not title:
                title = f"第{len(eps) + 1}集"
            vid = f"{he.a}@@{he.e}@@{tid}"
            if vid not in eps.values():
                eps[title] = vid
        return eps

    def detailContent(self, ids):
        vod = {}
        try:
            url = _abs(str(ids[0]))
            html = self._get(url, url)
            he = self._parse_he(url, html)
            if he.a:
                self._he_cache[he.a] = he
            name = ""
            for pat in (r'class="book-detail-title"[^>]*>([\s\S]*?)<', r"<h1[^>]*>([\s\S]*?)</h1>", r"<title>([^<]+)</title>"):
                m = re.search(pat, html or "")
                if m:
                    name = _text(m.group(1))
                    break
            pic = ""
            m = re.search(r'<img[^>]+class="img-thumbnail"[^>]*>|<img[^>]+class="book-detail-img[^"]*"[^>]*>|<img[^>]+class="book-img[^"]*"[^>]*>|<meta[^>]+property="og:image"[^>]*>', html or "")
            if m:
                pic = _abs(_attr(m.group(0), "src") or _attr(m.group(0), "content"))
            status = self._o(html, "状态") or self._o(html, "集数")
            if not status:
                m = re.search(r'class="book-detail-info"[^>]*>([^<]{1,60})<', html or "")
                if m:
                    status = _text(m.group(1))
            cate = self._o(html, "类型") or self._o(html, "分类")
            anchor = self._o(html, "主播") or self._o(html, "播音")
            author = self._o(html, "作者")
            year = ""
            m = RE_YEAR.search(html or "")
            if m:
                year = m.group(0)
            content = ""
            m = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', html or "")
            if m:
                content = m.group(1)
            if not content:
                for cls in ("book-detail-intro", "book-detail-content", "intro"):
                    m = re.search(r'class="' + cls + r'"[^>]*>([\s\S]*?)<', html or "")
                    if m and _text(m.group(1)):
                        content = _text(m.group(1))
                        break
            # 章节 (含分页详情页)
            eps = self._parse_eps(html, he)
            for m in re.finditer(r'<a[^>]+href="([^"]*book/detail/[^"]+)"', html or ""):
                u = _abs(m.group(1).split("?")[0])
                if u == url or not re.search(r"/book/detail/[^/]+/\d+", u):
                    continue
                try:
                    h2 = self._get(u, u)
                    eps.update(self._parse_eps(h2, he))
                except Exception:
                    pass
            if not eps and he.b:
                title = he.c or "播放"
                eps[title] = f"{he.a}@@{he.e}@@{he.b}"
            play_from = "悦听吧"
            vod = {"vod_id": url, "vod_name": name or "听书", "vod_pic": pic,
                   "vod_year": year, "vod_area": cate, "vod_actor": anchor,
                   "vod_director": author, "vod_content": content, "vod_remarks": status,
                   "vod_play_from": play_from,
                   "vod_play_url": "#".join(f"{t}${v}" for t, v in eps.items())}
        except Exception:
            pass
        return {"list": [vod]}

    # ---- 播放 ----
    @staticmethod
    def _pick_media(arr, book_id):
        # AsType=1 Type=A 的节点; BookIds 含 bookId 优先; Name 以 _b/_p 结尾优先
        if not isinstance(arr, list):
            return None
        def pick(cond):
            for it in arr:
                if not isinstance(it, dict):
                    continue
                if str(it.get("AsType")) != "1" or str(it.get("Type")) != "A":
                    continue
                if cond(it):
                    return it
            return None
        bid = book_id
        if bid and "-" in str(bid):
            bid = str(bid)[str(bid).rfind("-") + 1:]
        obj = pick(lambda it: str(it.get("BookIds") or "").strip() and bid in str(it.get("BookIds")).split(",")) \
              or pick(lambda it: str(it.get("BookIds") or "").strip() == "")
        if obj is None:
            return None
        name = str(obj.get("Name") or "")
        base = f"{obj.get('Scheme')}://{obj.get('Value')}:{obj.get('Port')}"
        return {"name": name, "base": base}

    def playerContent(self, flag, playId, vipFlags):
        url = ""
        try:
            p = playId or ""
            if "$" in p:
                p = p[p.rfind("$") + 1:]
            parts = p.split("@@")
            if len(parts) < 3:
                return {"parse": 0, "url": "", "header": {"User-Agent": UA}}
            bid, py, tid = parts[0], parts[1], parts[2]
            he = self._he_cache.get(bid)
            if he is None or not he.d:
                u = f"{SITE}/book/detail/{bid}/0"
                h = self._get(u, u)
                he = self._parse_he(u, h)
                if not he.e:
                    he.e = py
                self._he_cache[bid] = he
            j = {}
            try:
                j = json.loads(self._get(_abs(f"/api/app/docs-listen/{tid}/ting-with-efi"), SITE + "/"))
            except Exception:
                pass
            efi = j.get("efi") or ""
            ctime = j.get("creationTime") or ""
            if not efi:
                return {"parse": 0, "url": "", "header": {"User-Agent": UA}}
            if ctime:
                k, iv = _dyn_key(tid, ctime)
                plain = _aes_decrypt(efi, k, iv)
            else:
                plain = efi
            if plain.endswith("/"):
                plain = plain[:-1]
            fname = plain[plain.rfind("/") + 1:] if "/" in plain else plain
            media = self._pick_media(he.a_list, bid)
            if not media:
                return {"parse": 0, "url": "", "header": {"User-Agent": UA}}
            path = ""
            if media["name"].endswith("_p"):
                path = f"/{he.e}_{bid}/{fname}"
            elif media["name"].endswith("_b"):
                path = f"/myfiles/host/listen/booksdir/{he.e}_{bid}/{fname}"
            else:
                path = "/" + fname
            expire = int(time.time()) + 600
            token = _md5(f"{fname}|{expire}{SECRET}")
            url = f"{media['base']}{path}?token={token}&expire={expire}"
        except Exception:
            pass
        return {"parse": 0, "url": url, "header": {"User-Agent": UA, "Referer": SITE + "/"}}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            html = self._get(f"{SITE}/Search?type=1&name={quote(key)}", SITE + "/")
            result["list"] = self._parse_books(html)
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
