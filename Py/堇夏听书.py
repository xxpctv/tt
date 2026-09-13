# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   堇夏听书 (TingBookJinXia)
# 站点: https://m.ting15.com

from base.spider import Spider
import requests
import re
import json
from urllib.parse import quote

SITE = "https://m.ting15.com"
UA = "Mozilla/5.0 (Linux; Android 12; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
CATES = [["wuxiaxuanhuan", "武侠玄幻"], ["kongbulingyi", "恐怖灵异"], ["tuilixuanyi", "推理悬疑"],
         ["dushiyanqing", "都市言情"], ["jiatinglunli", "家庭伦理"], ["wenxuemingzhu", "文学名著"],
         ["jingdianpingshu", "经典评书"], ["quyixiqu", "曲艺戏曲"], ["xiangshengxiaopin", "相声小品"]]
IMG_SUFFIX = "@Referer=https://m.ting15.com/@User-Agent=Mozilla/5.0 (Linux; Android 12; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def _attr(html, name):
    m = re.search(name + r'\s*=\s*["\']([^"\']*)["\']', html or "")
    return m.group(1).strip() if m else ""


def _abs(u):
    u = (u or "").strip()
    if not u:
        return SITE + "/"
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("http"):
        return u
    return SITE + ("/" if not u.startswith("/") else "") + u


def _pic_suffix(src):
    if src and "@Referer=" not in src:
        return src + IMG_SUFFIX
    return src


class Spider(Spider):
    def getName(self):
        return "堇夏听书"

    def init(self, extend=""):
        global SITE
        s = (extend or "").strip()
        if s:
            SITE = s.rstrip("/")

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _get(self, url, post=None):
        hdrs = {"User-Agent": UA, "Referer": SITE + "/",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
        try:
            if post is not None:
                return requests.post(url, data=post, headers=hdrs, timeout=15).text
            return requests.get(url, headers=hdrs, timeout=15).text
        except Exception:
            return ""

    # ---- 列表解析 ----
    def _parse_list(self, html):
        out = []
        # .clist > a[href] 或 section a[href$=.html]
        blocks = []
        for m in re.finditer(r'class="clist"[^>]*>([\s\S]*?)</(?:ul|div|section|dl)>', html or ""):
            blocks.append(m.group(1))
        if blocks:
            for seg in blocks:
                for am in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', seg):
                    href = am.group(1).strip()
                    if not href or href.startswith("http") or href.startswith("javascript:"):
                        continue
                    inner = am.group(2)
                    name = ""
                    hm = re.search(r"<h3[^>]*>([\s\S]*?)</h3>", inner)
                    if hm:
                        name = _text(hm.group(1))
                        if name.startswith("["):
                            idx = name.find("]")
                            if idx >= 0 and idx + 1 < len(name):
                                name = name[idx + 1:].strip()
                    if not name:
                        name = _text(inner)
                    if not name:
                        continue
                    pic = ""
                    im = re.search(r"<img[^>]+src=\"([^\"]+)\"", inner)
                    if im:
                        pic = _pic_suffix(im.group(1))
                    remark = ""
                    dm = re.search(r"<dd[^>]*>([\s\S]*?)</dd>", inner)
                    if dm:
                        for pm in re.finditer(r"<p[^>]*>([^<]*)</p>", dm.group(1)):
                            t = _text(pm.group(1))
                            if t.startswith("连载") or t.startswith("状态"):
                                remark = t.replace("状态：", "").replace("状态:", "").replace("连载：", "").replace("连载:", "").strip()
                                break
                    out.append({"vod_id": href, "vod_name": name, "vod_pic": pic, "vod_remarks": remark})
        if out:
            return out
        # 回退: section a 含 h3
        for am in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', html or ""):
            href = am.group(1).strip()
            inner = am.group(2)
            if not href or href.startswith("http") or href.startswith("javascript:"):
                continue
            if "<h3" not in inner:
                continue
            name = ""
            hm = re.search(r"<h3[^>]*>([\s\S]*?)</h3>", inner)
            if hm:
                name = _text(hm.group(1))
            if not name:
                continue
            out.append({"vod_id": href, "vod_name": name, "vod_pic": "", "vod_remarks": ""})
        return out

    def homeContent(self, filter):
        result = {"class": [{"type_id": c[0], "type_name": c[1]} for c in CATES], "filters": {}}
        fs = [{"key": "order", "name": "排序",
               "value": [{"n": "全部", "v": ""}, {"n": "热门", "v": "hits"}, {"n": "最新", "v": "addtime"}]}]
        result["filters"] = {c[0]: fs for c in CATES}
        try:
            result["list"] = self._parse_list(self._get(SITE + "/"))
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        return self.categoryContent("wuxiaxuanhuan", 1, False, {})

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            order = (extend or {}).get("order") or ""
            if order:
                path = f"/{tid}/index{pg}-order-{order}.html"
            elif pg <= 1:
                path = f"/{tid}/"
            else:
                path = f"/{tid}/index{pg}.html"
            html = self._get(SITE + path)
            lst = self._parse_list(html)
            result["list"] = lst
            # 分页 .cpage span "共/页"
            max_pg = pg
            for m in re.finditer(r'class="cpage"[^>]*>([\s\S]*?)</(?:div|span|ul|dl)>', html or ""):
                t = _text(m.group(1))
                for part in re.split(r"[共/页\s]+", t):
                    if part.strip().isdigit():
                        max_pg = max(max_pg, int(part.strip()))
            result["page"] = pg
            result["pagecount"] = max(pg, max_pg)
            result["total"] = max(len(lst), 1) * max(pg, max_pg)
        except Exception:
            pass
        return result

    @staticmethod
    def _binfo(html, label):
        for m in re.finditer(r'class="binfo"[^>]*>([\s\S]*?)</(?:div|dl|section)>', html or ""):
            for pm in re.finditer(r"<p[^>]*>([^<]+)</p>", m.group(1)):
                t = _text(pm.group(1))
                if t.startswith(label) and len(t) > len(label):
                    return t[len(label):].strip()
        return ""

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0])
            html = self._get(_abs(vid))
            name = ""
            m = re.search(r'class="binfo"[^>]*>\s*<h1[^>]*>([^<]*)</h1>', html or "")
            if m:
                name = _text(m.group(1))
            pic = ""
            m = re.search(r'class="bimg"[^>]*>([\s\S]*?)</(?:div|dl)>', html or "")
            if m:
                im = re.search(r'<img[^>]+src="([^"]+)"', m.group(1))
                if im:
                    pic = _pic_suffix(im.group(1))
            author = self._binfo(html, "作者")
            cate = self._binfo(html, "类型")
            status = self._binfo(html, "状态")
            anchor = self._binfo(html, "播音")
            content = ""
            m = re.search(r'class="intro"[^>]*>([\s\S]*?)</(?:div|dl)>', html or "")
            if m:
                for pm in re.finditer(r"<p[^>]*>([^<]*)</p>", m.group(1)):
                    t = _text(pm.group(1))
                    if t and "看APP" not in t and len(t) > 20:
                        content = t
                        break
            eps = []
            for am in re.finditer(r'<a[^>]+class="f"[^>]+href="([^"]+)"[^>]*>([^<]*)</a>', html or ""):
                h = am.group(1).strip()
                t = _text(am.group(2))
                if h and t:
                    eps.append(f"{t}${h}")
            vod = {"vod_id": vid, "vod_name": name or "听书", "vod_pic": pic,
                   "vod_content": content, "vod_actor": author, "vod_director": anchor,
                   "type_name": cate, "vod_remarks": status,
                   "vod_play_from": "堇夏", "vod_play_url": "#".join(eps)}
        except Exception:
            pass
        return {"list": [vod]}

    def playerContent(self, flag, playId, vipFlags):
        url = ""
        try:
            p = playId or ""
            if "$" in p:
                p = p[p.rfind("$") + 1:]
            path = p if p.startswith("/") else "/" + p
            html = self._get(SITE + path)
            book_id = ""
            is_pay = ""
            page = ""
            xt = ""
            for meta_name, var in (("_b", "book_id"), ("_p", "is_pay"), ("_cp", "page"), ("_c", "xt")):
                m = re.search(r'<meta[^>]+name="' + meta_name + r'"[^>]+content="([^"]*)"', html or "")
                if not m:
                    m = re.search(r'<meta[^>]+content="([^"]*)"[^>]+name="' + meta_name + r'"', html or "")
                val = m.group(1).strip() if m else ""
                if var == "book_id":
                    book_id = val
                elif var == "is_pay":
                    is_pay = val
                elif var == "page":
                    page = val
                else:
                    xt = val
            if book_id and is_pay:
                body = {"bookId": book_id, "isPay": is_pay, "page": page or "1"}
                if xt:
                    body["xt"] = xt
                resp = self._get(SITE + "/?s=api-getneoplay", post=body)
                resp = resp.lstrip("\ufeff")
                try:
                    j = json.loads(resp)
                    if j.get("status") == 1:
                        url = j.get("url") or j.get("ourl") or ""
                except Exception:
                    pass
            if not url:
                m = re.search(r'<audio[^>]+id="player"[^>]+src="([^"]+)"', html or "")
                if m:
                    url = m.group(1)
            if not url:
                url = SITE + path
        except Exception:
            pass
        return {"parse": 0, "url": url,
                "header": {"User-Agent": UA, "Referer": SITE + "/"}}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            html = self._get(f"{SITE}/?s=ting-search-wd-{quote(key)}")
            result["list"] = self._parse_list(html)
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
