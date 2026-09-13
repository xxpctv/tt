# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   玩偶云盘 (Wogg)
# 站点: https://wogg.xxooo.cf (可 ext site 覆盖); 配置可 ext filter 指向 wogg_filters.json
# 说明: 原版依赖 QuarkYun token 解析分享链,提供完整 列表/搜索/详情,
#       播放时原样返回分享链文本.

from base.spider import Spider
import requests
import re
import json
from urllib.parse import quote

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
STATIC_CATES = [["1", "玩偶电影"], ["2", "玩偶剧集"], ["44", "臻彩视界"],
                ["3", "动漫"], ["6", "短剧"], ["4", "综艺"],
                ["46", "纪录片"], ["5", "音乐"]]
SHARE_RE = re.compile(
    r"https?://(?:pan\.quark\.cn|drive\.uc\.cn|pan\.baidu\.com|123pan\.com|"
    r"123684\.com|cloud\.189\.cn|aliyundrive\.com|alipan\.com|115\.com|"
    r"pan\.xunlei\.com|caiyun\.139\.com)[^\s\"'<>]*", re.I)
LINK_RE = re.compile(r"https?://\S+")


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def _attr(html, *names):
    for n in names:
        m = re.search(n + r'\s*=\s*["\']([^"\']*)["\']', html or "")
        if m and m.group(1).strip():
            return m.group(1).strip()
    return ""


class Spider(Spider):
    def __init__(self):
        super().__init__()
        self.site = "https://wogg.xxooo.cf"

    def getName(self):
        return "玩偶云盘"

    def init(self, extend=""):
        try:
            j = json.loads((extend or "").strip())
        except Exception:
            j = {}
        s = str(j.get("site") or "").strip()
        if s:
            self.site = s.rstrip("/")

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

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

    def _fetch(self, url):
        try:
            return requests.get(url, headers={"User-Agent": UA, "Referer": self.site + "/"},
                                timeout=15).text
        except Exception:
            return ""

    def _parse_items(self, html):
        out = []
        for m in re.finditer(r'class="module-item"', html or ""):
            start = m.start()
            nxt = html.find('class="module-item"', start + 1)
            seg = html[start:nxt if nxt > 0 else len(html)]
            am = re.search(r'class="module-item-titlebox"[^>]*>([\s\S]*?)</', seg)
            seg2 = am.group(1) if am else seg
            am2 = re.search(r'<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', seg2)
            if not am2:
                am2 = re.search(r'<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', seg)
            if not am2:
                continue
            name = _attr(am2.group(0), "title") or _text(am2.group(2))
            if not name or name == "臻彩":
                continue
            pic = ""
            im = re.search(r'class="module-item-pic"[^>]*>([\s\S]*?)</', seg)
            if im:
                pic = _attr(im.group(1), "data-src", "src")
            remark = ""
            rm = re.search(r'class="module-item-text"[^>]*>([^<]*)<', seg)
            if rm:
                remark = _text(rm.group(1))
            out.append({"vod_id": self._abs(am2.group(1).strip()), "vod_name": name,
                        "vod_pic": self._abs(pic), "vod_remarks": remark})
        return out

    def homeContent(self, filter):
        cats = [{"type_id": cid, "type_name": name} for cid, name in STATIC_CATES]
        lst = self._parse_items(self._fetch(self.site))[:12]
        return {"class": cats, "filters": {}, "list": lst}

    def homeVideoContent(self):
        return {"list": self.homeContent(False)["list"]}

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 30, "total": 0}
        try:
            pg = str(pg) if str(pg).strip().isdigit() else "1"
            ex = extend or {}
            if ex.get("cateId"):
                tid = str(ex["cateId"])
            fields = ["", "", "", "", "", "", "", "", pg, "", "", ""]
            if ex.get("area"):
                fields[1] = str(ex["area"])
            if ex.get("by"):
                fields[2] = str(ex["by"])
            if ex.get("class"):
                fields[3] = str(ex["class"])
            if ex.get("letter"):
                fields[5] = str(ex["letter"])
            if ex.get("year"):
                fields[11] = str(ex["year"])
            fields[0] = str(tid)
            path = "/vodshow/" + "-".join(fields) + ".html"
            html = self._fetch(self.site + path)
            if 'class="module-item"' not in (html or ""):
                html = self._fetch(self.site + "/index.php" + path)
            lst = self._parse_items(html)
            result["list"] = lst
            result["page"] = int(pg)
            result["pagecount"] = max(int(pg), 1) if not lst else int(pg) + 1
            result["total"] = 99999 if lst else 0
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0]).strip()
            if not vid.startswith("http"):
                return {"list": [], "error": "无效链接"}
            html = self._fetch(vid)
            # 分享链提取: .module-row-text data-clipboard-text / 文本 + 全页兜底
            shares, seen = [], set()
            for m in re.finditer(r'class="module-row-text"[^>]*data-clipboard-text="([^"]*)"', html):
                s = m.group(1).strip()
                if s and s not in seen:
                    seen.add(s)
                    shares.append(s)
            if not shares:
                for m in re.finditer(r'class="module-row-text"[^>]*>([^<]*)<', html):
                    s = m.group(1).strip()
                    if s and s not in seen:
                        seen.add(s)
                        shares.append(s)
            # 全页兜底
            if not shares:
                for s in SHARE_RE.findall(html):
                    if s and s not in seen:
                        seen.add(s)
                        shares.append(s)
            if not shares:
                return {"list": [], "error": "未找到网盘资源"}
            links = [s for s in shares if LINK_RE.match(s)]
            if len(links) > 1:
                links = links[::-1]
            name = ""
            m = re.search(r'class="page-title"[^>]*>([^<]*)<', html)
            if m:
                name = _text(m.group(1))
            if not name:
                m = re.search(r"<h1[^>]*>([^<]*)</h1>", html)
                if m:
                    name = _text(m.group(1))
            eps = [f"网盘{i + 1}${s}" for i, s in enumerate(links)]
            vod = {"vod_id": vid, "vod_name": name or "云盘资源",
                   "vod_play_from": "网盘", "vod_play_url": "#".join(eps)}
            pic = ""
            im = re.search(r'class="module-item-pic"[^>]*>([\s\S]*?)</', html)
            if im:
                pic = _attr(im.group(1), "data-src", "src")
            if pic:
                vod["vod_pic"] = self._abs(pic)
        except Exception:
            pass
        return {"list": [vod]}

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
            pg = str(pg) if str(pg).strip().isdigit() else "1"
            kw = quote(key)
            urls = [f"/index.php/vodsearch/{kw}----------{pg}---.html",
                    f"/index.php/vod/search/wd/{kw}.html",
                    f"/index.php/vod/search.html?wd={kw}"]
            for u in urls:
                html = self._fetch(self.site + u)
                lst = self._parse_search(html)
                if lst:
                    result["list"] = lst
                    break
        except Exception:
            pass
        return result

    def _parse_search(self, html):
        out = []
        for m in re.finditer(r'class="module-search-item"', html or ""):
            start = m.start()
            nxt = html.find('class="module-search-item"', start + 1)
            seg = html[start:nxt if nxt > 0 else len(html)]
            am = re.search(r'class="video-info-header"[^>]*>([\s\S]*?)</', seg)
            seg2 = am.group(1) if am else seg
            am2 = re.search(r'<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', seg2)
            if not am2:
                am2 = re.search(r'<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', seg)
            if not am2:
                continue
            name = _attr(am2.group(0), "title") or _text(am2.group(2))
            if not name:
                continue
            pic = ""
            im = re.search(r'class="module-item-pic"[^>]*>([\s\S]*?)</', seg)
            if im:
                pic = _attr(im.group(1), "data-src", "src")
            remark = ""
            rm = re.search(r'class="video-serial"[^>]*>([^<]*)<', seg)
            if rm:
                remark = _text(rm.group(1))
            out.append({"vod_id": self._abs(am2.group(1).strip()), "vod_name": name,
                        "vod_pic": self._abs(pic), "vod_remarks": remark})
        return out

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
