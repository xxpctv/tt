# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   剧透云盘 (AiNewJuTou)
# 站点: https://1.star2.cn (可 ext {"site":"..."} 覆盖)
# 说明: 完整复刻 列表/分类/详情/搜索; 原版依赖 QuarkYun token 解析分享链,
#      播放时原样返回分享链文本.

from base.spider import Spider
import requests
import re
import json
from urllib.parse import quote

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
CATS = [["ju", "国剧"], ["zy", "综艺"], ["mv", "电影"], ["rh", "日韩"],
        ["ym", "英美"], ["wj", "外剧"], ["dm", "动漫"]]
SHARE_KW = ("pan.quark.cn", "drive.uc.cn", "pan.baidu.com", "115.com/s/",
            "123pan.com", "123684.com", "cloud.189.cn", "139.com",
            "pan.xunlei.com", "guangyapan.com")


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


class Spider(Spider):
    def __init__(self):
        super().__init__()
        self.site = "https://1.star2.cn"
        self.cookie = ""

    def getName(self):
        return "剧透云盘"

    def init(self, extend=""):
        if not (extend or "").strip():
            return
        try:
            j = json.loads(extend)
            site = j.get("site")
            if isinstance(site, list):
                site = site[0] if site else ""
            self.site = str(site or self.site).strip().rstrip("/")
        except Exception:
            pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _headers(self, with_cookie=True):
        h = {"User-Agent": UA, "Referer": self.site}
        if with_cookie and self.cookie:
            h["Cookie"] = self.cookie
        return h

    def _fetch(self, url):
        try:
            r = requests.get(url, headers=self._headers(), timeout=15)
            if not self.cookie:
                cookies = []
                for c in r.headers.get("set-cookie", "").split(","):
                    kv = c.split(";")[0].strip()
                    if "=" in kv and kv not in cookies:
                        cookies.append(kv)
                self.cookie = "; ".join(cookies)
            return r.text or ""
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
        out, seen = [], set()
        # 主列表: ul > li
        for m in re.finditer(r"<li[^>]*>([\s\S]*?)</li>", html or ""):
            seg = m.group(1)
            am = re.search(r'<div[^>]*class="[^"]*a[^"]*"[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', seg)
            if not am:
                am = re.search(r'<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', seg)
            if not am:
                continue
            href = am.group(1).strip()
            name = _text(am.group(2))
            if not href or not name or href in seen:
                continue
            seen.add(href)
            out.append({"vod_id": href, "vod_name": name, "vod_pic": "",
                        "vod_remarks": ""})
        # 回退: a[href*=.html]
        if not out:
            for am in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', html or ""):
                href = am.group(1).strip()
                name = _text(am.group(2))
                if not re.search(r".*/[a-z]+/\d+\.html.*", href) or not name or href in seen:
                    continue
                seen.add(href)
                out.append({"vod_id": href, "vod_name": name, "vod_pic": "",
                            "vod_remarks": ""})
        return out

    def homeContent(self, filter):
        return {"class": [{"type_id": cid, "type_name": name} for cid, name in CATS],
                "filters": {}, "list": []}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 15, "total": 0}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            ex = extend or {}
            if ex.get("cateId"):
                tid = str(ex["cateId"])
            cat = str(tid or "ju")
            html = self._fetch(f"{self.site}/{cat}_{pg}/")
            lst = self._parse_items(html)
            result["list"] = lst
            result["page"] = pg
            result["pagecount"] = pg if len(lst) < 15 else pg + 1
            result["total"] = 0
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0]).strip()
            url = vid if vid.lower().startswith("http") else self.site + vid
            html = self._fetch(url)
            name = ""
            for sel in (r"<h1[^>]*>([^<]*)</h1>",):
                m = re.search(sel, html)
                if m and _text(m.group(1)):
                    name = _text(m.group(1))
                    break
            # 云盘分享链: 多组选择器兜底
            shares, seen = [], set()
            for am in re.finditer(r'<a[^>]+href="([^"]+)"', html or ""):
                h = am.group(1).strip()
                if not any(k in h.lower() for k in SHARE_KW):
                    continue
                h = h.replace("&amp;", "&")
                if h and h not in seen:
                    seen.add(h)
                    shares.append(h)
            vod = {"vod_id": vid, "vod_name": name or vid, "vod_pic": "",
                   "vod_content": "", "vod_director": "", "vod_actor": ""}
            if shares:
                eps = [f"网盘{i + 1}${s}" for i, s in enumerate(shares)]
                vod["vod_play_from"] = "网盘"
                vod["vod_play_url"] = "#".join(eps)
            else:
                vod["vod_remarks"] = "未识别到已开启的网盘分享链"
        except Exception:
            pass
        return {"list": [vod] if vod else []}

    def playerContent(self, flag, playId, vipFlags):
        p = playId or ""
        if "$" in p:
            p = p[p.rfind("$") + 1:]
        return {"parse": 0, "url": p.strip(),
                "header": {"User-Agent": UA, "Referer": self.site}}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            pg = str(pg) if str(pg).strip().isdigit() else "1"
            html = self._fetch(f"{self.site}/search/?keyword={quote(key)}&page={pg}")
            result["list"] = self._parse_items(html)
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
