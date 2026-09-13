# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   蜡笔云盘 (FishCloud)
# 站点: https://123.666291.xyz / 666.666291.xyz / www.muou.site / www.muou.asia
# 说明: 原版依赖 QuarkYun token 解析分享链,提供完整 列表/搜索/详情,
#       播放时原样返回分享链文本.

from base.spider import Spider
import requests
import re
import json
from urllib.parse import quote

DEFAULT_SITES = ["https://123.666291.xyz", "https://666.666291.xyz",
                 "https://www.muou.site", "https://www.muou.asia"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
STATIC_CATES = [["1", "电影"], ["2", "剧集"], ["3", "动漫"],
                ["4", "综艺"], ["5", "短剧"], ["26", "高分精选"]]
RE_TYPE = re.compile(r"(?:/id/|/vodtype/|/type/id/)(\d+)")


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def _attr(html, *names):
    for n in names:
        m = re.search(n + r'\s*=\s*["\']([^"\']*)["\']', html or "")
        if m and m.group(1).strip():
            return m.group(1).strip()
    return ""


def _clean_cat(name):
    n = (name or "").strip()
    for p in ("更多", "多多", "小虎斑"):
        if n.startswith(p):
            n = n[len(p):]
    return n.strip()


class Spider(Spider):
    def __init__(self):
        super().__init__()
        self.site = DEFAULT_SITES[0]
        self.type_mode = False

    def getName(self):
        return "蜡笔云盘"

    def init(self, extend=""):
        try:
            j = json.loads((extend or "").strip())
        except Exception:
            j = {}
        if j.get("cate") and str(j.get("cate")).lower() == "type":
            self.type_mode = True
        s = str(j.get("site") or "").strip()
        if not s:
            # 逐站探测
            for u in DEFAULT_SITES:
                try:
                    r = requests.get(u, headers={"User-Agent": UA, "Referer": u}, timeout=10)
                    if 200 <= r.status_code < 400 and ("module-item" in (r.text or "") or "vod" in (r.text or "")):
                        s = u
                        break
                except Exception:
                    continue
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
        # 切片 .module-item
        for m in re.finditer(r'class="module-item"', html or ""):
            start = m.start()
            nxt = html.find('class="module-item"', start + 1)
            seg = html[start:nxt if nxt > 0 else len(html)]
            am = re.search(r'class="module-item-titlebox"[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', seg)
            if not am:
                am = re.search(r'class="video-name"[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', seg)
            if not am:
                am = re.search(r'<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', seg)
            if not am:
                continue
            href = am.group(1).strip()
            name = _attr(am.group(0), "title") or _text(am.group(2))
            if not href or not name:
                continue
            pic = ""
            im = re.search(r'class="module-item-pic"[^>]*>([\s\S]*?)</', seg)
            if not im:
                im = re.search(r"<img[^>]+>", seg)
            if im:
                pic = _attr(im.group(1) if im.group(0).startswith("class") else im.group(0),
                            "data-src", "src")
            if not pic and im and not im.group(0).startswith("class"):
                pic = _attr(im.group(0), "data-src", "src")
            remark = ""
            rm = re.search(r'class="module-item-text"[^>]*>([^<]*)<', seg)
            if rm:
                remark = _text(rm.group(1))
            out.append({"vod_id": self._abs(href), "vod_name": name,
                        "vod_pic": self._abs(pic), "vod_remarks": remark})
        return out

    def _parse_cats(self, html):
        cats = {}
        for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>([^<]*)</a>', html or ""):
            href = m.group(1)
            rm = RE_TYPE.search(href)
            if not rm:
                continue
            name = _clean_cat(m.group(2))
            if not name or ("网址" in name or "专题" in name or "全部" in name):
                continue
            cid = rm.group(1)
            if cid not in cats:
                cats[cid] = name
        return cats

    def homeContent(self, filter):
        html = self._fetch(self.site)
        lst = self._parse_items(html)
        # 社会主义核心价值观 劫持检测
        if not lst or ("社会主义核心价值观" in (html or "")):
            html2 = self._fetch(self.site + "/index.php/vod/show/id/1.html")
            lst2 = self._parse_items(html2)
            if lst2:
                lst = lst2
        cats_map = self._parse_cats(html)
        if not cats_map:
            for cid, cname in STATIC_CATES:
                cats_map[cid] = cname
        # 分类兜底: 全量 a 再扫一次
        if len(cats_map) <= 1:
            cats_map.update(self._parse_cats(html))
        cats = [{"type_id": cid, "type_name": name} for cid, name in cats_map.items()]
        return {"class": cats, "filters": {}, "list": lst}

    def homeVideoContent(self):
        return {"list": self.homeContent(False)["list"]}

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 36, "total": 0}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            ex = extend or {}
            if ex.get("cateId"):
                tid = str(ex["cateId"])
            if self.type_mode:
                path = f"/index.php/vod/type/id/{tid}"
                if pg > 1:
                    path += f"/page/{pg}"
                path += ".html"
            else:
                path = f"/index.php/vod/show/id/{tid}/page/{pg}"
                for k in ("class", "area", "lang", "year", "by"):
                    v = str(ex.get(k) or "").strip()
                    if v:
                        path += f"/{k}/{v}"
                path += ".html"
            html = self._fetch(self.site + path)
            if not html:
                html = self._fetch(self.site + f"/index.php/vod/type/id/{tid}/page/{pg}.html")
            lst = self._parse_items(html)
            result["list"] = lst
            result["page"] = pg
            result["pagecount"] = pg if not lst else pg + 1
            result["total"] = 99999 if lst else 0
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0]).strip()
            if not vid.startswith("http"):
                return {"list": [], "error": "无效的分享链接"}
            html = self._fetch(vid)
            name = ""
            m = re.search(r"<h1[^>]*>([^<]*)</h1>", html or "")
            if m:
                name = _text(m.group(1))
            if not name:
                m = re.search(r"<title>([^<]*)</title>", html or "")
                if m:
                    name = _text(m.group(1))
                    for sep in ("-", "_"):
                        if sep in name:
                            name = name.split(sep)[0].strip()
            # 分享链接
            shares, seen = [], set()
            for am in re.finditer(r'<a[^>]+href="([^"]+)"', html or ""):
                h = am.group(1).strip()
                if not (("pan.quark.cn" in h) or ("drive.uc.cn" in h) or
                        ("pan.baidu.com" in h) or ("aliyundrive.com" in h) or
                        ("alipan.com" in h) or ("cloud.189.cn" in h) or
                        ("115.com" in h) or ("123pan.com" in h) or ("123684.com" in h)):
                    continue
                h = h.replace("&amp;", "&")
                if h and h not in seen:
                    seen.add(h)
                    shares.append(h)
            if not shares:
                return {"list": [], "error": "未找到网盘资源"}
            eps = [f"网盘{i + 1}${s}" for i, s in enumerate(shares)]
            vod = {"vod_id": vid, "vod_name": name or "云盘资源",
                   "vod_play_from": "网盘", "vod_play_url": "#".join(eps)}
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
            kw = quote(key)
            urls = [f"/index.php/vod/search/wd/{kw}.html",
                    f"/index.php/vod/search.html?wd={kw}",
                    f"/index.php/vodsearch/{kw}----------1---.html"]
            for u in urls:
                html = self._fetch(self.site + u)
                lst = []
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
                    lst.append({"vod_id": self._abs(am2.group(1).strip()),
                                "vod_name": name, "vod_pic": self._abs(pic),
                                "vod_remarks": remark})
                if lst:
                    result["list"] = lst
                    break
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
