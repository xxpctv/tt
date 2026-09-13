# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   六月听书 (TingBook)
# 站点: https://app.365ting.com

from base.spider import Spider
import requests
import re
import json
import time
from urllib.parse import quote

SITE = "https://app.365ting.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
CATES = [["6", "玄幻奇幻"], ["7", "都市言情"], ["8", "宫斗女频"], ["9", "官场商战"],
         ["10", "武侠仙侠"], ["11", "刑侦推理"], ["12", "探险科幻"], ["13", "重生穿越"],
         ["14", "恐怖惊悚"], ["15", "文学历史"], ["31", "评书相声"], ["49", "两性情感"],
         ["51", "儿童文学"], ["52", "国学启蒙"], ["53", "家教育儿"], ["54", "卡通动画"]]
RE_NUM = re.compile(r"^\d+(\*\d+)+$")


def _https(u):
    return "https:" + u if (u or "").startswith("//") else (u or "")


def _abs(u):
    u = (u or "").strip()
    if not u:
        return SITE
    if u.startswith("http"):
        return u
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return SITE + u
    return SITE + "/" + u


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def _attr(html, name):
    m = re.search(name + r'\s*=\s*["\']([^"\']*)["\']', html or "")
    return m.group(1).strip() if m else ""


class Spider(Spider):
    def getName(self):
        return "六月听书"

    def init(self, extend=""):
        global SITE
        s = (extend or "").strip()
        if s:
            try:
                j = json.loads(s)
                u = str(j.get("site") or j.get("url") or "").strip()
            except Exception:
                u = s
            if u:
                SITE = u.rstrip("/")

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _get(self, url):
        hdrs = {"User-Agent": UA, "Referer": SITE + "/",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
        try:
            return requests.get(url, headers=hdrs, timeout=15).text
        except Exception:
            return ""

    def _parse_books(self, html):
        out, seen = [], set()
        for m in re.finditer(r'<a[^>]+href="(/book/\d+\.html)"[^>]*>([\s\S]*?)</a>', html or ""):
            href = m.group(1)
            if href in seen:
                continue
            seg = m.group(2)
            name, cate = "", ""
            hm = re.search(r"<h2[^>]*>([\s\S]*?)</h2>", seg)
            if hm:
                t = _text(hm.group(1))
                if "|" in t:
                    cate, name = t.split("|", 1)
                    cate, name = cate.strip(), name.strip()
                else:
                    name = t
            if not name:
                name = _text(seg)
            if not name:
                continue
            im = re.search(r'<img[^>]+src="([^"]+)"', seg)
            pic = _https(im.group(1)) if im else ""
            seen.add(href)
            out.append({"vod_id": href, "vod_name": name, "vod_pic": pic,
                        "vod_remarks": cate or "听书"})
        return out

    def homeContent(self, filter):
        result = {"class": [{"type_id": c[0], "type_name": c[1]} for c in CATES], "filters": {}, "list": []}
        try:
            result["list"] = self._parse_books(self._get(f"{SITE}/category/6/2/1.html"))
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        return self.categoryContent("6", 1, False, {})

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            html = self._get(f"{SITE}/category/{tid}/2/{pg}.html")
            lst = self._parse_books(html)
            result["list"] = lst
            result["page"] = pg
            result["pagecount"] = pg if not lst else pg + 1
            result["total"] = max(len(lst), 1) * pg
        except Exception:
            pass
        return result

    @staticmethod
    def _extra(html, label):
        for m in re.finditer(r'class="extra"[^>]*>([\s\S]*?)</[^>]+>', html or ""):
            seg = m.group(1)
            if _text(seg).startswith(label):
                tm = re.search(r'class="text"[^>]*>([\s\S]*?)</', seg)
                if tm:
                    seg = tm.group(1)
                am = re.search(r"<a[^>]*>([\s\S]*?)</a>", seg)
                return _text(am.group(1)) if am else _text(seg)
        return ""

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0])
            html = ""
            for _ in range(3):
                html = self._get(_abs(vid))
                if "System Error" not in html:
                    break
                time.sleep(0.5)
            name = ""
            m = re.search(r'<h2[^>]*class="book-title"[^>]*>([\s\S]*?)</h2>', html or "")
            if not m:
                m = re.search(r'<h1[^>]*class="title"[^>]*>([\s\S]*?)</h1>', html or "")
            if m:
                name = _text(m.group(1))
            pic = ""
            m = re.search(r'<img[^>]+class="img"[^>]+src="([^"]+)"', html or "")
            if not m:
                m = re.search(r'<img[^>]+alt="[^"]*"[^>]+src="([^"]+)"', html or "")
            if m:
                pic = _https(m.group(1))
            content = ""
            m = re.search(r'class="book-intro"[^>]*>([\s\S]*?)</', html or "")
            if m:
                content = _text(m.group(1))
            author = self._extra(html, "作者")
            cate = self._extra(html, "类型")
            status = self._extra(html, "状态") or self._extra(html, "原著")
            bobei = self._extra(html, "播音")
            eps = []
            for m in re.finditer(r'<a[^>]+class="list-item[^"]*"[^>]+href="(/play/[^"]+)"[^>]*>([\s\S]*?)</a>', html or ""):
                t = _text(m.group(2)) or "章节"
                eps.append(f"{t}${m.group(1)}")
            # 分页
            max_pg = 1
            for m in re.finditer(r'href="[^"]*page=(\d+)[^"]*"', html or ""):
                try:
                    max_pg = max(max_pg, int(m.group(1)))
                except Exception:
                    pass
            max_pg = min(max_pg, 200)
            sep = "&" if "?" in vid else "?"
            for p in range(2, max_pg + 1):
                try:
                    html2 = self._get(_abs(vid) + f"{sep}page={p}")
                    for m in re.finditer(r'<a[^>]+class="list-item[^"]*"[^>]+href="(/play/[^"]+)"[^>]*>([\s\S]*?)</a>', html2 or ""):
                        t = _text(m.group(2)) or "章节"
                        eps.append(f"{t}${m.group(1)}")
                except Exception:
                    pass
            vod = {"vod_id": vid, "vod_name": name or "听书", "vod_pic": pic,
                   "vod_content": content, "vod_actor": author, "vod_director": bobei,
                   "type_name": cate, "vod_remarks": status,
                   "vod_play_from": "六月", "vod_play_url": "#".join(eps)}
        except Exception:
            pass
        return {"list": [vod]}

    @staticmethod
    def _decode(n, src):
        s = (src or "").strip()
        if not s:
            return ""
        if n == 1 or RE_NUM.match(s):
            try:
                out = "".join(chr(int(x)) for x in s.split("*") if x)
                return "https:" + out if out.startswith("//") else out
            except Exception:
                return s
        return s

    def playerContent(self, flag, playId, vipFlags):
        url = ""
        hdrs = {"User-Agent": UA, "Referer": SITE + "/",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
        try:
            p = playId or ""
            if "$" in p:
                p = p[p.rfind("$") + 1:]
            if "/play/" in p:
                s = p.replace("/play/", "").replace(".html", "")
                parts = s.split("/")
                if len(parts) >= 2:
                    ts = int(time.time())
                    u = (f"{SITE}/pc/index/getchapterurl/bookId/{parts[0]}/chapterId/{parts[1]}/timestamp/{ts}.html")
                    j = json.loads(self._get(u) or "{}")
                    src = self._decode(j.get("jsjm") or 0, j.get("src") or "")
                    if src:
                        url = src
            if not url:
                if not p.startswith("http"):
                    if not p.startswith("/"):
                        p = "/play/" + p.replace("/play/", "") + ".html"
                    p = _abs(p)
                url = p
        except Exception:
            pass
        return {"parse": 0, "url": url, "header": hdrs}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            html = self._get(f"{SITE}/pc/index/search/keyword/{quote(key)}.html")
            result["list"] = self._parse_books(html)
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
