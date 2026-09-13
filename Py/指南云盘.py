# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   指南云盘 (KZN)
# 站点: https://4kzn.cc (ext site)
# 注意: 播放地址为夸克/UC/阿里/百度等网盘分享链, 需账号 token 才能解析为直链;
#      列表/搜索/详情完整可用, 详情页以"分享链"呈现.

from base.spider import Spider
import requests
import re
from urllib.parse import quote

SITE = "https://4kzn.cc"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
CATES = [["top250", "TOP250"], ["dianying", "电影"], ["juji", "剧集"], ["zuixin", "影视"]]
RE_HREF = re.compile(r'href\s*=\s*["\'](https?://[^"\']+)["\']')
PAN_HOSTS = ("pan.quark.cn", "drive.uc.cn", "alipan.com", "aliyundrive.com", "pan.baidu.com",
             "115.com", "115cdn.com", "123pan", "123684.com", "xunlei.com", "cloud.189.cn",
             "caiyun.139.com", "guangya", "gyapan", "guangyapan")


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def _attr(html, name):
    m = re.search(name + r'\s*=\s*["\']([^"\']*)["\']', html or "")
    return m.group(1).strip() if m else ""


def _articles(html):
    out = []
    for m in re.finditer(r"<article", html or ""):
        start = m.start()
        nxt = html.find("<article", start + 1)
        seg = html[start:nxt if nxt > 0 else len(html)]
        out.append(seg)
    return out


class Spider(Spider):
    def __init__(self):
        super().__init__()
        self.site = SITE

    def getName(self):
        return "指南云盘"

    def init(self, extend=""):
        import json as _json
        s = (extend or "").strip()
        if s:
            try:
                j = _json.loads(s)
                u = j.get("site")
                if isinstance(u, list):
                    u = u[0] if u else ""
                u = str(u or "").strip()
            except Exception:
                u = s
            if u:
                self.site = u.rstrip("/").replace("https://4kzn.com", SITE).replace("http://4kzn.com", SITE)
        if not self.site:
            self.site = SITE

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _get(self, url):
        try:
            return requests.get(url, headers={"User-Agent": UA}, timeout=15).text
        except Exception:
            return ""

    def _norm_href(self, href):
        h = (href or "").strip()
        h = h.replace("https://4kzn.com", self.site).replace("http://4kzn.com", self.site)
        if h.startswith(self.site):
            h = h[len(self.site):]
            if not h:
                h = "/"
        return h

    @staticmethod
    def _is_pan(url):
        u = url.lower()
        return any(h in u for h in PAN_HOSTS)

    def _parse_articles(self, html):
        out = []
        for seg in _articles(html):
            am = re.search(r'<a[^>]+href="([^"]*)"', seg)
            if not am or "/book/" not in am.group(1):
                continue
            href = self._norm_href(am.group(1))
            if not href or href in [v["vod_id"] for v in out]:
                continue
            im = re.search(r"<(?:img|IMG)[^>]+>", seg)
            pic = ""
            if im:
                pic = _attr(im.group(0), "data-src") or _attr(im.group(0), "src")
            nm = re.search(r"<h3>\s*<a[^>]*>(.*?)</a>", seg, re.S) or re.search(r"<h3[^>]*>(.*?)</h3>", seg, re.S)
            name = _text(nm.group(1)) if nm else ""
            if not name:
                continue
            rm = re.search(r"<h3[^>]*>\s*<a[^>]*>.*?</a>\s*(?:<div[^>]*>|<span[^>]*>)?(.*?)</", seg, re.S)
            remark = _text(rm.group(1)) if rm else ""
            out.append({"vod_id": href, "vod_name": name, "vod_pic": pic, "vod_remarks": remark})
        return out

    def homeContent(self, filter):
        result = {"class": [{"type_id": c[0], "type_name": c[1]} for c in CATES], "filters": {}, "list": []}
        try:
            result["list"] = self._parse_articles(self._get(self.site + "/books/zuixin"))
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        return self.categoryContent("zuixin", 1, False, {})

    def _tid_path(self, tid):
        t = (tid or "").strip() or "zuixin"
        if t.startswith("/books/"):
            t = t[7:]
        elif t.startswith("books/"):
            t = t[6:]
        if "/" in t:
            t = t.split("/", 1)[0]
        return t

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 30, "total": 0}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            path = self._tid_path(tid)
            url = f"{self.site}/books/{path}"
            if pg > 1:
                url += f"/page/{pg}"
            html = self._get(url)
            result["list"] = self._parse_articles(html)
            has_more = ('加载更多' in html) or bool(re.search(r'<a[^>]+class="[^"]*next[^"]*"', html))
            nxt = pg + 1 if has_more else pg
            n = max(len(result["list"]), 1)
            result["page"] = pg
            result["pagecount"] = nxt
            result["total"] = nxt * n
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0]).strip()
            if vid.startswith("http"):
                url = vid
            else:
                url = self.site + ("/" if not vid.startswith("/") else "") + vid
            html = self._get(url)
            name = ""
            m = re.search(r'<h1[^>]*class="[^"]*site-name[^"]*"[^>]*>(.*?)</h1>', html, re.S) \
                or re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
            if m:
                name = _text(m.group(1))
            pic = ""
            m = re.search(r'<img[^>]+class="[^"]*book-cover[^"]*"[^>]*>', html)
            if m:
                pic = _attr(m.group(0), "data-src") or _attr(m.group(0), "src")
            remark = ""
            m = re.search(r'class="[^"]*mt-n2[^"]*"[^>]*>\s*<p[^>]*>(.*?)</p>', html, re.S)
            if m:
                remark = _text(m.group(1))
            content = ""
            m = re.search(r'class="[^"]*content-wrap[^"]*"[^>]*>\s*<p[^>]*>(.*?)</p>', html, re.S)
            if m:
                content = _text(m.group(1))
            shares = []
            for am in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>', html):
                u = am.group(1).strip()
                if self._is_pan(u) and u not in shares:
                    shares.append(u)
            seg = re.search(r'class="[^"]*site-go[^"]*"[\s\S]*?(?=<div class=|<footer|</body|$)', html)
            if seg:
                for um in RE_HREF.finditer(seg.group(0)):
                    u = um.group(1).strip()
                    if self._is_pan(u) and u not in shares:
                        shares.append(u)
            urls = [f"分享{i + 1}${u}" for i, u in enumerate(shares)]
            vod = {
                "vod_id": str(ids[0]),
                "vod_name": name or "书籍",
                "vod_pic": pic,
                "vod_remarks": remark,
                "vod_content": content,
                "vod_play_from": "网盘" if urls else "",
                "vod_play_url": "#".join(urls),
            }
        except Exception:
            pass
        return {"list": [vod]}

    def playerContent(self, flag, playId, vipFlags):
        return {"parse": 0, "url": (playId or "").strip(), "header": {"User-Agent": UA}}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            try:
                pg = max(1, int(pg))
            except Exception:
                pg = 1
            url = f"{self.site}/page/{pg}/?post_type=book&s={quote(key)}"
            result["list"] = self._parse_articles(self._get(url))
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
