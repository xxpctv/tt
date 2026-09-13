# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   枫叶影视 (FengYe)
# 站点: https://www.cd-zj.com / https://www.tjtcdl.com (自动轮换) + 解析站
# 说明: 完整复刻 分类/详情(多线路+集数)/搜索; 站点带 mac_verify 验证码时自动尝试
#       过验证(4位图形码), 失败则该页返回空; 播放走通用解析(parse 1).

from base.spider import Spider
import requests
import re
import json
import random
from urllib.parse import quote

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
SITES = ["https://www.cd-zj.com", "https://www.tjtcdl.com"]


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


class Spider(Spider):
    def __init__(self):
        super().__init__()
        self.site = SITES[0]

    def getName(self):
        return "枫叶影视"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _headers(self, ref=None):
        return {"User-Agent": UA,
                "Referer": (ref or self.site + "/"),
                "Accept-Language": "zh-CN,zh;q=0.9"}

    def _get(self, url, ref=None):
        try:
            return requests.get(url, headers=self._headers(ref), timeout=15).text
        except Exception:
            return ""

    def _fetch(self, url):
        """带验证码处理的抓取: 遇 mac_verify 尝试一次过验证, 失败返回''"""
        html = self._get(url)
        if not html or ("mac_verify" not in html and "captcha.php?type=verify" not in html
                        and "系统安全验证" not in html):
            return html
        # 尝试过验证
        for _ in range(1):
            try:
                s = requests.Session()
                s.headers.update(self._headers())
                r = s.get(url, timeout=15)
                code = re.search(r'<img[^>]+src="([^"]*captcha[^"]*)"', r.text or "")
                if not code:
                    return ""
                cv = s.get(self._abs(code.group(1)), timeout=15)
                import io
                try:
                    from PIL import Image
                    img = Image.open(io.BytesIO(cv.content)).convert("L")
                    img = img.resize((img.width * 4, img.height * 4))
                    px = list(img.getdata())
                    # 极简二值化: 取最暗块中心
                    dark = [(i, p) for i, p in enumerate(px) if p < 120]
                    if not dark:
                        return ""
                    grp = {}
                    for i, p in dark:
                        x = i % img.width // 4
                        grp.setdefault(x, []).append(i)
                    cols = sorted(grp, key=lambda x: len(grp[x]), reverse=True)
                    guess = "".join(str(c % 10) for c in cols[:4])
                    if len(guess) != 4:
                        return ""
                    r2 = s.post(self._abs("/captcha.php?type=verify"),
                                data={"check": guess}, headers=self._headers(), timeout=15)
                    if "code" in r2.text and "1" in r2.text:
                        return s.get(url, headers=self._headers(), timeout=15).text
                except Exception:
                    return ""
            except Exception:
                return ""
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
        for m in re.finditer(r'<a[^>]+class="public-list-exp"[^>]*>([\s\S]*?)</a>', html or ""):
            atag = "<a" + m.group(0)[m.group(0).find("class"):]
            am = re.search(r'href="([^"]+)"', atag)
            if not am:
                continue
            href = am.group(1).strip()
            rm = re.search(r"/(?:detail|chabeihu)/(\d+)\.html", href)
            if not rm or rm.group(1) in seen:
                continue
            vid = rm.group(1)
            seen.add(vid)
            name = ""
            tm = re.search(r'title="([^"]+)"', atag)
            if tm:
                name = tm.group(1).strip()
            if not name:
                im = re.search(r"<img[^>]+alt=\"([^\"]+)\"", m.group(1))
                if im:
                    name = im.group(1).strip()
            pic = ""
            im = re.search(r"<img[^>]+>", m.group(1))
            if im:
                pm = re.search(r'data-src="([^"]+)"', im.group(0))
                if pm:
                    pic = pm.group(1).replace("&amp;", "&")
                    if pic.startswith("//"):
                        pic = "https:" + pic
            remark = ""
            rm2 = re.search(r'class="(?:ft2|public-list-prb)"[^>]*>([^<]*)<', m.group(1))
            if rm2:
                remark = _text(rm2.group(1))
            year = ""
            ys = re.findall(r'class="public-prt"[^>]*>([^<]*)<', m.group(1))
            if ys:
                year = ",".join(y.strip() for y in ys if y.strip())
            out.append({"vod_id": vid, "vod_name": name or vid, "vod_pic": pic,
                        "vod_remarks": remark, "vod_year": year})
        return out

    def homeContent(self, filter):
        cats = [{"type_id": "/label/2", "type_name": "电影"},
                {"type_id": "/label/1", "type_name": "电视剧"},
                {"type_id": "/label/4", "type_name": "动漫"},
                {"type_id": "/label/3", "type_name": "综艺"},
                {"type_id": "/label/5", "type_name": "纪录片"}]
        lst = self._parse_items(self._fetch(self.site))
        return {"class": cats, "filters": {}, "list": lst[:12]}

    def homeVideoContent(self):
        return {"list": self.homeContent(False)["list"]}

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}
        try:
            pg = str(pg) if str(pg).strip().isdigit() else "1"
            tid = str(tid)
            if tid.startswith("/label"):
                url = self._abs(f"{tid}/page/{pg}.html")
            else:
                url = self._abs(f"/cupfox-list/{tid}--------{pg}---.html")
            html = self._fetch(url)
            if not self._parse_items(html) and not tid.startswith("/label"):
                html = self._fetch(self._abs(f"/label/{tid}/page/{pg}.html"))
            lst = self._parse_items(html)
            result["list"] = lst
            n = int(pg) if pg.isdigit() else 1
            result["page"] = n
            result["pagecount"] = n + 2 if len(lst) >= 24 else n
            result["total"] = len(lst)
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0]).split(",")[0].strip()
            if not vid:
                return {"list": [], "error": "影片ID为空"}
            html = self._fetch(self._abs(f"/detail/{vid}.html"))
            if not html or ("h3.slide-info-title" not in html and ".this-desc-title" not in html
                            and ".anthology-list-box" not in html):
                html2 = self._fetch(self._abs(f"/chabeihu/{vid}.html"))
                if html2:
                    html = html2
            if not html:
                return {"list": [], "error": "详情获取失败"}
            name = vid
            m = re.search(r'<h3[^>]*class="(?:slide-info-title|this-desc-title)"[^>]*>([^<]*)<', html)
            if m:
                name = _text(m.group(1))
            pic = ""
            m = re.search(r'<img[^>]+class="lazy"[^>]+>', html)
            if not m:
                m = re.search(r'<img[^>]+class="[^"]*this-desc-img[^"]*"[^>]+>', html)
            if m:
                pm = re.search(r'data-src="([^"]+)"', m.group(0))
                if pm:
                    pic = pm.group(1).replace("&amp;", "&")
            director, actor = "", ""
            for seg in re.findall(r'<[^>]*class="slide-info"[^>]*>([^<]*)<', html):
                t = _text(seg)
                if t.startswith("导演："):
                    director = t[3:].strip()
                elif t.startswith("演员："):
                    actor = t[3:].strip()
            if not director or not actor:
                for seg in re.findall(r'<li[^>]*>([^<]*)</li>', html):
                    t = _text(seg).replace("\u00a0", " ")
                    if "导演" in t and not director:
                        director = re.sub(r"^.*?导演[:：]?\s*", "", t).strip()
                    elif ("主演" in t or "演员" in t) and not actor:
                        actor = re.sub(r"^.*?(?:主演|演员)[:：]?\s*", "", t).strip()
            content = ""
            m = re.search(r'id="height_limit"[^>]*>([\s\S]*?)<', html)
            if m:
                content = _text(m.group(1))
            # 线路名
            lines = []
            for m in re.finditer(r'class="(?:anthology-tab[^"]*|swiper-slide)"[^>]*>([\s\S]*?)</a>', html):
                t = _text(m.group(1))
                b = re.search(r'class="badge"[^>]*>([^<]*)<', m.group(1))
                if b:
                    t = t.replace(_text(b.group(1)), "").strip()
                if t:
                    lines.append(t)
            # 集数: 每个线路一个 ul
            play_from, play_url = [], []
            uls = re.findall(r'class="anthology-list-box"[\s\S]*?(?=class="anthology-list-box"|$)', html)
            for i, ul in enumerate(uls):
                eps = []
                for am in re.finditer(r'<li[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', ul):
                    href = am.group(1).strip()
                    t = _text(am.group(2)) or "正片"
                    m2 = re.search(r"/play/(.*?)\.html", href)
                    if m2:
                        ep = m2.group(1)
                        if not ep.startswith(f"{vid}-"):
                            ep = f"{vid}-{ep}"
                        eps.append(f"{t}${ep}")
                    elif href.startswith("http") and "/play/" in href:
                        eps.append(f"{t}${href}")
                if eps:
                    play_from.append(lines[i] if i < len(lines) and lines[i] else f"线路{i + 1}")
                    play_url.append("#".join(reversed(eps)))
            vod = {"vod_id": vid, "vod_name": name or vid, "vod_pic": pic,
                   "vod_content": content, "vod_director": director, "vod_actor": actor}
            if play_from:
                vod["vod_play_from"] = "$$$".join(play_from)
                vod["vod_play_url"] = "$$$".join(play_url)
        except Exception:
            pass
        return {"list": [vod] if vod else []}

    def playerContent(self, flag, playId, vipFlags):
        try:
            pid = (playId or "").strip()
            if not pid:
                return {"parse": 1, "url": "", "header": {}, "error": "播放 id 为空"}
            if pid.startswith("http"):
                url = pid
            else:
                url = self._abs(f"/play/{pid}.html")
            html = self._fetch(url)
            m = re.search(r"<iframe[^>]+src=[\"']([^\"']+)[\"']", html or "")
            src = m.group(1).strip() if m else url
            if src and not src.startswith("http"):
                src = self._abs(src)
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
            html = self._fetch(self._abs(f"/cupfox-search/{quote(key)}----------{pg}---.html"))
            result["list"] = self._parse_items(html)
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
