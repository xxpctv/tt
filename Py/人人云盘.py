# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   人人云盘 (RenRen)
# 站点: https://www.rrdynb.com
# 说明: 完整复刻 列表/分类/详情/搜索; 原版依赖 QuarkYun token 解析分享链,
#      播放时原样返回分享链文本.

from base.spider import Spider
import requests
import re
import json
from urllib.parse import quote

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
CATS = {"movie": "list_2_", "dianshiju": "list_6_",
        "zongyi": "list_10_", "dongman": "list_13_"}
CAT_NAMES = [["movie", "电影"], ["dianshiju", "电视剧"],
             ["zongyi", "老电影"], ["dongman", "动漫"]]


def _clean(s):
    s = (s or "").replace("&amp;", "&").replace("&quot;", "\"")
    i = s.find("\u300a")
    j = s.find("\u300b", i)
    if i >= 0 and j > i:
        s = s[i + 1:j]
    return re.sub(r"<.*?>", "", s).strip()


class Spider(Spider):
    def __init__(self):
        super().__init__()
        self.site = "https://www.rrdynb.com"

    def getName(self):
        return "人人云盘"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _headers(self):
        return {"User-Agent": UA, "Referer": self.site + "/"}

    def _fetch(self, url):
        try:
            return requests.get(url, headers=self._headers(), timeout=15).text
        except Exception:
            return ""

    def _abs(self, u):
        u = (u or "").strip()
        if not u:
            return ""
        if u.startswith("http"):
            return u
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return self.site + u
        return self.site + "/" + u

    def _parse_items(self, html):
        out = []
        for m in re.finditer(r'<li[^>]*class="[^"]*pure-g[^"]*shadow[^"]*"[^>]*>([\s\S]*?)</li>', html or ""):
            seg = m.group(1)
            am = re.search(r'<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', seg)
            if not am:
                continue
            href = am.group(1).strip()
            name = _attr(am.group(0), "title") or ""
            if not name:
                h2 = re.search(r"<h2[^>]*>([\s\S]*?)</h2>", seg)
                name = _text(h2.group(1)) if h2 else _text(am.group(2))
            name = _clean(name)
            if not href or not name:
                continue
            pic = ""
            im = re.search(r'\[data-original="([^"]+)"\]', seg) or re.search(r'data-original="([^"]+)"', seg)
            if im:
                pic = im.group(1).strip()
            out.append({"vod_id": href, "vod_name": name,
                        "vod_pic": pic, "vod_remarks": ""})
        return out

    def homeContent(self, filter):
        cats = [{"type_id": tid, "type_name": name} for tid, name in CAT_NAMES]
        lst = self._parse_items(self._fetch(self.site + "/movie/"))
        return {"class": cats, "filters": {}, "list": lst[:12]}

    def homeVideoContent(self):
        return {"list": self.homeContent(False)["list"]}

    def _cat_url(self, pg, cat):
        base = f"{self.site}/{cat.rstrip('/')}"
        if pg <= 1:
            return base + "/"
        suffix = CATS.get(cat, "list_2_")
        return f"{base}/{suffix}{pg}.html"

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            html = self._fetch(self._cat_url(pg, str(tid)))
            lst = self._parse_items(html)
            result["list"] = lst
            result["page"] = pg
            result["pagecount"] = pg if pg >= 100 else pg + 1
            result["total"] = len(lst)
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0]).strip()
            url = vid if vid.startswith("http") else self.site + vid
            html = self._fetch(url)
            m = re.search(r'class="movie-des(?: shadow)?"[^>]*>([\s\S]*?)(?=<div|$)', html, re.S)
            if not m:
                return {"list": [], "error": "无法定位电影信息区域"}
            seg = m.group(1)
            name = ""
            h1 = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", seg)
            if h1:
                name = _clean(_text(h1.group(1)))
            pic = ""
            im = re.search(r'class="movie-txt"[^>]*>([\s\S]*?)</', seg)
            if im:
                im2 = re.search(r"<img[^>]+>", im.group(1))
                if im2:
                    p = _attr(im2.group(0), "src", "data-src")
                    if p.startswith("http") and (".jpg" in p or ".png" in p):
                        pic = p
            content = ""
            i = seg.find("剧情简介：")
            j = seg.find("资源：", i if i >= 0 else 0)
            if i >= 0 and j > i:
                content = _text(seg[i + 5:j])
            shares, seen = [], set()
            for am in re.finditer(r'<a[^>]+href="([^"]+)"', seg):
                h = am.group(1).strip().replace("&amp;", "&").replace("?entry=nmmecc", "")
                h = h.split("#")[0]
                if not (("pan.baidu.com" in h) or ("pan.quark.cn" in h) or
                        ("aliyundrive.com" in h) or ("alipan.com" in h)):
                    continue
                if h and h not in seen:
                    seen.add(h)
                    shares.append(h)
            if not shares:
                return {"list": [], "error": "未找到网盘资源"}
            eps = [f"网盘{i + 1}${s}" for i, s in enumerate(shares)]
            vod = {"vod_id": vid, "vod_name": name or "云盘资源",
                   "vod_pic": pic, "vod_content": content,
                   "vod_play_from": "网盘", "vod_play_url": "#".join(eps)}
        except Exception:
            pass
        return {"list": [vod] if vod else []}

    def playerContent(self, flag, playId, vipFlags):
        p = playId or ""
        if "$" in p:
            p = p[p.rfind("$") + 1:]
        return {"parse": 0, "url": p.strip(),
                "header": {"User-Agent": UA, "Referer": self.site + "/"}}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            html = self._fetch(f"{self.site}/plus/search.php?q={quote(key)}")
            result["list"] = self._parse_items(html)
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]


def _attr(html, *names):
    for n in names:
        m = re.search(n + r'\s*=\s*["\']([^"\']*)["\']', html or "")
        if m and m.group(1).strip():
            return m.group(1).strip()
    return ""


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()
