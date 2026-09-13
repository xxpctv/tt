# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   急救知识 (FirstAid)
# 站点: https://m.youlai.cn

from base.spider import Spider
import requests
import re

SITE = "https://m.youlai.cn"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
CATES = ["急救技能", "家庭生活", "急危重症", "常见损伤", "动物致伤", "海洋急救", "中毒急救", "意外事故"]
PICS = ["https://static.cnkang.com/images/youlai/patient/dissicon/jijiu/title_jjjn.png",
        "https://static.cnkang.com/images/youlai/patient/dissicon/jijiu/title_jtsh.png",
        "https://static.cnkang.com/images/youlai/patient/dissicon/jijiu/title_jwzz.png",
        "https://static.cnkang.com/images/youlai/patient/dissicon/jijiu/title_cjss.png",
        "https://static.cnkang.com/images/youlai/patient/dissicon/jijiu/title_dwzs.png",
        "https://static.cnkang.com/images/youlai/patient/dissicon/jijiu/title_hyjj.png",
        "https://static.cnkang.com/images/youlai/patient/dissicon/jijiu/title_zdjj.png",
        "https://static.cnkang.com/images/youlai/patient/dissicon/jijiu/title_ywsg.png"]
RE_VIDEO = re.compile(r"(https://vod\.youlai\.cn/[^\"'\s<>]+)")


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def _attr(html, name):
    m = re.search(name + r'\s*=\s*["\']([^"\']*)["\']', html or "")
    return m.group(1).strip() if m else ""


def _fix(u):
    u = (u or "").strip()
    if not u:
        return ""
    if u.startswith("https://https://"):
        return u.replace("https://https://", "https://")
    if u.startswith("http://https://"):
        return u.replace("http://https://", "https://")
    if u.startswith("http"):
        return u
    if u.startswith("//"):
        return "https:" + u
    return u


def _abs(u):
    u = (u or "").strip()
    if not u:
        return ""
    if u.startswith("http"):
        return u
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return SITE + u
    return SITE + "/" + u


class Spider(Spider):
    def getName(self):
        return "急救知识"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _get(self, url):
        try:
            return requests.get(url, headers={"User-Agent": UA, "Referer": SITE + "/"}, timeout=15).text
        except Exception:
            return ""

    def _home_items(self, html):
        out = []
        blocks = [b for b in re.finditer(r'class="jj-title-li"', html or "")]
        for i in range(len(CATES)):
            pic, name, href = PICS[i], CATES[i], f"jijiu|{i}"
            if i < len(blocks):
                seg_start = blocks[i].start()
                nxt = html.find('class="jj-title-li"', seg_start + 1)
                seg = html[seg_start:nxt if nxt > 0 else len(html)]
                im = re.search(r'<img[^>]+class="block100"[^>]+src="([^"]+)"', seg)
                if im:
                    pic = _fix(im.group(1)) or pic
                am = re.search(r'<a[^>]+href="([^"]*jijiu/article/[^"]+)"[^>]*>([\s\S]*?)</a>', seg)
                if am:
                    href = _abs(am.group(1))
                    title = ""
                    lm = re.search(r'class="line-clamp1"[^>]*>([^<]*)<', am.group(2))
                    title = _text(lm.group(1)) if lm else _text(am.group(2))
                    if title:
                        name = f"{CATES[i]} · {title}"
            out.append({"vod_id": href, "vod_name": name, "vod_pic": pic, "vod_remarks": "急救"})
        return out

    def homeContent(self, filter):
        result = {"class": [{"type_id": f"jijiu|{i}", "type_name": c} for i, c in enumerate(CATES)],
                  "filters": {}, "list": []}
        try:
            result["list"] = self._home_items(self._get(SITE + "/jijiu/"))
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        return self.categoryContent("jijiu|0", 1, False, {})

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
        try:
            idx = 0
            parts = str(tid or "").split("|")
            if len(parts) >= 2 and parts[1].strip().isdigit():
                idx = int(parts[1].strip())
            html = self._get(SITE + "/jijiu/")
            blocks = [b for b in re.finditer(r'class="jj-title-li"', html or "")]
            pic = PICS[idx] if 0 <= idx < len(PICS) else PICS[0]
            im = re.search(r'<img[^>]+class="block100"[^>]+src="([^"]+)"', html or "")
            if im and idx >= len(blocks):
                pass
            if 0 <= idx < len(blocks):
                seg_start = blocks[idx].start()
                nxt = html.find('class="jj-title-li"', seg_start + 1)
                seg = html[seg_start:nxt if nxt > 0 else len(html)]
                im = re.search(r'<img[^>]+class="block100"[^>]+src="([^"]+)"', seg)
                if im:
                    pic = _fix(im.group(1)) or pic
                for am in re.finditer(r'<a[^>]+href="([^"]*jijiu/article/[^"]+)"[^>]*>([\s\S]*?)</a>', seg):
                    href = _abs(am.group(1))
                    lm = re.search(r'class="line-clamp1"[^>]*>([^<]*)<', am.group(2))
                    name = _text(lm.group(1)) if lm else _text(am.group(2))
                    if href and name:
                        result["list"].append({"vod_id": href, "vod_name": name,
                                               "vod_pic": pic, "vod_remarks": "急救"})
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0])
            html = self._get(vid)
            name = ""
            for pat in (r'class="video-title h1-title"[^>]*>([^<]*)<', r'class="h1-title"[^>]*>([^<]*)<', r"<h1[^>]*>([^<]*)</h1>"):
                m = re.search(pat, html or "")
                if m:
                    name = _text(m.group(1))
                    break
            name = name or "急救教学"
            doc = ""
            m = re.search(r'<span[^>]*class="doc-name"[^>]*>([^<]*)</span>', html or "")
            if m:
                doc = _text(m.group(1))
            content = ""
            m = re.search(r'class="img-text-con"[^>]*>([\s\S]*?)</(?:div|section)>', html or "")
            if m:
                content = _text(m.group(1))
            pic = ""
            if m:
                for im in re.finditer(r'<img[^>]+src="([^"]+)"', m.group(1)):
                    u = _fix(im.group(1))
                    if u and ".gif" not in u:
                        pic = u
                        break
            if not pic:
                m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]*)"', html or "")
                if m:
                    pic = _fix(m.group(1))
            pic = pic or PICS[0]
            video = ""
            m = re.search(r'<video[^>]+id="video"[^>]+src="([^"]+)"', html or "")
            if m and "vod.youlai.cn" in m.group(1):
                video = m.group(1)
            if not video:
                m = RE_VIDEO.search(html or "")
                if m:
                    video = m.group(1)
            if not video:
                return {"list": [], "error": "未找到视频地址"}
            vod = {"vod_id": vid, "vod_name": name, "vod_pic": pic,
                   "vod_area": "中国", "vod_actor": doc, "vod_content": content,
                   "vod_play_from": "Qile", "vod_play_url": f"{name}${video}"}
        except Exception:
            pass
        return {"list": [vod]}

    def playerContent(self, flag, playId, vipFlags):
        return {"parse": 0, "url": (playId or "").strip(),
                "header": {"User-Agent": UA, "Referer": SITE + "/"}}

    def searchContent(self, key, quick):
        return {"list": []}

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
