# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   骚火影视 (SaoHuo)
# 站点: https://shdy5.us (可 ext site 覆盖)
# 说明: 完整复刻 列表/分类(含类型过滤)/详情/搜索; 播放取播放页 iframe src 走通用解析(parse 1).

from base.spider import Spider
import requests
import re
import json
from urllib.parse import quote

UA = ("Mozilla/5.0 (Linux; Android 9; ALN-AL00 Build/PQ3B.190801.05281406; wv) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/91.0.4472.114 Safari/537.36")
FILTERS = {
    "1": [["cateId", "类型", [("全部", "1"), ("喜剧", "6"), ("爱情", "7"), ("恐怖", "8"),
                             ("动作", "9"), ("科幻", "10"), ("战争", "11"), ("犯罪", "12"),
                             ("动画", "13"), ("奇幻", "14"), ("剧情", "15"), ("冒险", "16"),
                             ("悬疑", "17"), ("惊悚", "18"), ("其他", "20")]]],
    "2": [["cateId", "类型", [("全部", "2"), ("国产剧", "20"), ("TVB", "21"), ("韩剧", "22"),
                             ("美剧", "23"), ("日剧", "24"), ("英剧", "25"), ("台剧", "26"),
                             ("其他", "27")]]],
    "3": [["cateId", "类型", [("全部", "4"), ("搞笑", "38"), ("恋爱", "39"), ("热血", "40"),
                             ("格斗", "41"), ("美少女", "42"), ("魔法", "43"), ("机战", "44"),
                             ("校园", "45"), ("亲子", "46"), ("童话", "47"), ("冒险", "48"),
                             ("真人", "49"), ("LOLI", "50"), ("其他", "51")]]],
}


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
        self.site = "https://shdy5.us"
        self.cookie = ""

    def getName(self):
        return "骚火影视"

    def init(self, extend=""):
        if not (extend or "").strip():
            return
        raw = (extend or "").strip()
        site = raw
        try:
            if not raw.startswith("http"):
                site = json.loads(raw).get("site", raw)
        except Exception:
            pass
        site = str(site).rstrip("/")
        if site.startswith("http"):
            self.site = site

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _headers(self):
        h = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
             "Referer": self.site + "/"}
        if self.cookie:
            h["Cookie"] = self.cookie
        return h

    def _fetch(self, url):
        try:
            r = requests.get(url, headers=self._headers(), timeout=15)
            for c in r.headers.get("set-cookie", "").split(","):
                kv = c.split(";")[0].strip()
                if "=" in kv:
                    self.cookie = kv
                    break
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
        for m in re.finditer(r'<li[^>]*>([\s\S]*?)</li>', html or ""):
            seg = m.group(1)
            am = re.search(r'<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', seg)
            if not am:
                continue
            href = self._abs(am.group(1).strip())
            if not href or href in seen:
                continue
            name = _attr(am.group(0), "title") or _text(am.group(2))
            if not name:
                continue
            pic = ""
            im = re.search(r"<img[^>]+>", seg)
            if im:
                pic = self._abs(_attr(im.group(0), "data-original", "data-src", "src"))
            remark = ""
            rm = re.search(r'class="(?:hdtag|note|pic-text|remarks)"[^>]*>([^<]*)<', seg)
            if rm:
                remark = _text(rm.group(1))
            seen.add(href)
            out.append({"vod_id": href, "vod_name": name,
                        "vod_pic": pic, "vod_remarks": remark})
        return out

    def homeContent(self, filter):
        cats = [{"type_id": "1", "type_name": "电影"},
                {"type_id": "2", "type_name": "电视剧"},
                {"type_id": "20", "type_name": "国产剧"},
                {"type_id": "4", "type_name": "动漫"}]
        fts = {k: [{"key": kk, "name": nn,
                    "value": [{"n": n, "v": v} for n, v in vals]} for kk, nn, vals in v]
               for k, v in FILTERS.items()}
        lst = self._parse_items(self._fetch(self.site))[:6]
        return {"class": cats, "filters": fts, "list": lst}

    def homeVideoContent(self):
        return {"list": self.homeContent(False)["list"]}

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
        try:
            pg = str(pg) if str(pg).strip().isdigit() else "1"
            ex = extend or {}
            if ex.get("cateId"):
                tid = str(ex["cateId"])
            html = self._fetch(f"{self.site}/list/{tid}-{pg}.html")
            lst = self._parse_items(html)
            result["list"] = lst
            n = int(pg) if pg.isdigit() else 1
            result["page"] = n
            result["pagecount"] = n + 1
            result["total"] = len(lst) * (n + 1)
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            url = self._abs(str(ids[0]))
            html = self._fetch(url)
            name = ""
            for sel in (r"<h1[^>]*>([^<]*)<", r'class="(?:vodh[^"]*)?[^"]*h2[^"]*"[^>]*>([^<]*)<',
                        r'class="detail-title"[^>]*>([^<]*)<', r'class="title"[^>]*>([^<]*)<'):
                m = re.search(sel, html)
                if m and _text(m.group(1)):
                    name = _text(m.group(1))
                    break
            if not name:
                m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', html)
                if m:
                    name = m.group(1).strip()
            pic = ""
            im = re.search(r'class="(?:thumb|cover|detail-pic)"[^>]*>([\s\S]*?)</', html)
            if im:
                m2 = re.search(r"<img[^>]+>", im.group(1))
                if m2:
                    pic = self._abs(_attr(m2.group(0), "data-original", "data-src", "src"))
            content = ""
            for sel in (r'class="p_txt"[^>]*>([\s\S]*?)<', r'class="vod_content"[^>]*>([\s\S]*?)<',
                        r'class="content"[^>]*>([\s\S]*?)<'):
                m = re.search(sel, html)
                if m and _text(m.group(1)):
                    content = _text(m.group(1))
                    if not content.startswith("简介"):
                        content = "简介：" + content
                    break
            info = {"year": "", "director": "", "actor": ""}
            im2 = re.search(r'class="(?:info|vod_info|detail-info)"[^>]*>([\s\S]*?)</', html)
            if im2:
                txt = _text(im2.group(1))
                parts = re.split(r" / 导演:| / 主演:", txt)
                if parts:
                    info["year"] = parts[0].strip()
                if len(parts) > 1:
                    info["director"] = parts[1].strip()
                if len(parts) > 2:
                    info["actor"] = parts[2].strip()
            # 播放线路: #play_link li
            play_from, play_url = [], []
            blocks = re.findall(r'<li[^>]*>([\s\S]*?)</li>', html)
            links = re.findall(r'id="play_link"[\s\S]*?</ul>', html)
            src_html = links[0] if links else html
            li_blocks = re.findall(r"<li[^>]*>([\s\S]*?)</li>", src_html)
            from_blocks = re.findall(r'class="play_from[\s\S]*?</ul>', html)
            from_li = re.findall(r"<li[^>]*>([\s\S]*?)</li>", from_blocks[0]) if from_blocks else []
            for i, seg in enumerate(li_blocks):
                if not re.search(r"<a[^>]+href=|<a\s", seg):
                    continue
                line = _text(from_li[i]) if i < len(from_li) and _text(from_li[i]) else f"线路{i + 1}"
                if not line:
                    line = "播放"
                eps = []
                for am in reversed(re.findall(r'<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', seg)):
                    name = _text(am[1]) or "正片"
                    eps.append(f"{name}${am[0].strip()}")
                if eps:
                    play_from.append(line)
                    play_url.append("#".join(eps))
            vod = {"vod_id": url, "vod_name": name or url,
                   "vod_pic": pic, "vod_content": content,
                   "vod_year": info["year"], "vod_director": info["director"],
                   "vod_actor": info["actor"]}
            if play_from:
                vod["vod_play_from"] = "$$$".join(play_from)
                vod["vod_play_url"] = "$$$".join(play_url)
            else:
                vod["vod_remarks"] = "无播放列表"
        except Exception:
            pass
        return {"list": [vod] if vod else []}

    def playerContent(self, flag, playId, vipFlags):
        try:
            pid = (playId or "").strip()
            if not pid:
                return {"parse": 0, "url": "", "header": {}, "error": "播放 id 为空"}
            if "$" in pid:
                pid = pid.split("$")[-1]
            url = pid if pid.startswith("http") else self.site + pid
            html = self._fetch(url)
            m = re.search(r"<iframe[^>]+src=[\"']([^\"']+)[\"']", html or "")
            src = m.group(1).strip() if m else ""
            if src:
                src = self._abs(src)
            else:
                src = url
            return {"parse": 1, "url": src, "header": self._headers()}
        except Exception:
            return {"parse": 1, "url": playId or "", "header": self._headers()}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            html = self._fetch(f"{self.site}/s----------.html?wd={quote(key)}")
            result["list"] = self._parse_items(html)
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
