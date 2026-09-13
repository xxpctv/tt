# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   轮回音乐 (Djlh)
# 站点: https://www.dj92.cc

from base.spider import Spider
import requests
import re
import json
from urllib.parse import quote

BASE = "https://www.dj92.cc"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
CATES = [["1", "电音House"], ["2", "中文舞曲"], ["3", "外文舞曲"], ["4", "酒吧风格"],
         ["5", "串烧舞曲"], ["7", "私改舞曲"], ["8", "大赛作品"]]
RE_TOKEN = re.compile(r"token:\s*'([^']+)'")


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def _attr(html, name):
    m = re.search(name + r'\s*=\s*["\']([^"\']*)["\']', html or "")
    return m.group(1).strip() if m else ""


def _lis(html):
    out = []
    for m in re.finditer(r"<li", html or ""):
        start = m.start()
        nxt = html.find("<li", start + 1)
        seg = html[start:nxt if nxt > 0 else len(html)]
        out.append(seg)
    return out


class Spider(Spider):
    def getName(self):
        return "轮回音乐"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _get(self, url, post=None):
        try:
            if post is not None:
                return requests.post(url, data=post, headers={"User-Agent": UA}, timeout=12).text
            return requests.get(url, headers={"User-Agent": UA}, timeout=12).text
        except Exception:
            return ""

    @staticmethod
    def _parse(html):
        out = []
        for seg in _lis(html):
            nm = re.search(r'<a[^>]+href="([^"]+)"[^>]*title="([^"]*)"', seg)
            if not nm:
                continue
            href, title = nm.group(1).strip(), nm.group(2).strip()
            if not href or not title:
                continue
            im = re.search(r'<img[^>]+src="([^"]+)"', seg)
            pic = ""
            if im:
                pic = im.group(1)
                if not pic.startswith("http"):
                    pic = "https:" + pic
            nick = ""
            nm2 = re.search(r'title="([^"]*)"[^>]*href="[^"]*"', seg[seg.find("nickname"):] if "nickname" in seg else "")
            if nm2:
                nick = nm2.group(1).strip()
            out.append({"vod_id": href, "vod_name": title, "vod_pic": pic, "vod_remarks": nick})
        return out

    def homeContent(self, filter):
        return {"class": [{"type_id": c[0], "type_name": c[1]} for c in CATES], "filters": {}}

    def homeVideoContent(self):
        return self.categoryContent("1", 1, False, {})

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 9999}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            t = str(tid)
            if extend and extend.get("cateId"):
                t = str(extend["cateId"])
            url = f"{BASE}/djlist/{t}/{pg}.html"
            result["list"] = self._parse(self._get(url))
            result["page"] = pg
            result["pagecount"] = pg + 1
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0])
            html = self._get(BASE + vid)
            name = ""
            m = re.search(r'class="name"[^>]*>(.*?)</span>', html, re.S)
            if m:
                name = _text(m.group(1))
            token = ""
            m = RE_TOKEN.search(html or "")
            if m:
                token = m.group(1)
            play = ""
            if token:
                j = json.loads(self._get(f"{BASE}/ajax/info", post=f"token={token}"))
                play = j.get("playurl") or ""
                if play and not play.startswith("http"):
                    play = "https:" + play
            vod = {"vod_id": vid, "vod_name": name or "轮回DJ", "vod_pic": "",
                   "vod_play_from": "轮回DJ", "vod_play_url": f"点击播放${play}"}
        except Exception:
            pass
        return {"list": [vod]}

    def playerContent(self, flag, playId, vipFlags):
        return {"parse": 0, "url": (playId or "").strip(), "header": {"User-Agent": UA}}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 9999}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            url = f"{BASE}/search.html?key={quote(str(key))}&page={pg}"
            result["list"] = self._parse(self._get(url))
            result["page"] = pg
            result["pagecount"] = pg + 1
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
