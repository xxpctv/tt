# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   糯米影视 (Wwys)
# 站点: https://vip.wwgz.cn:5200 (可 ext 覆盖)
# 说明: 完整复刻 分类(含类型过滤)/首页/详情(集数+mac_url)/搜索;
#       播放地址为详情页 mac_url 直链(原版 player 三级 JS 解析已内置在详情阶段完成).

from base.spider import Spider
import requests
import re
import json
from urllib.parse import quote

UA = ("Mozilla/5.0 (Linux; Android 13; SM-A037U) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36  uacq")
FILTERS = {
    "1": [["cateId", "类型", [("全部", "1"), ("动作片", "5"), ("喜剧片", "6"),
                             ("爱情片", "7"), ("科幻片", "8"), ("恐怖片", "9"),
                             ("剧情片", "10"), ("战争片", "11"), ("惊悚片", "16"),
                             ("奇幻片", "17")]]],
    "2": [["cateId", "类型", [("全部", "2"), ("国产剧", "12"), ("港台剧", "13"),
                             ("日韩剧", "14"), ("欧美剧", "15")]]],
}
RE_MAC = re.compile(r"mac_url='([^']*)'")


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


class Spider(Spider):
    def __init__(self):
        super().__init__()
        self.site = "https://vip.wwgz.cn:5200"

    def getName(self):
        return "糯米影视"

    def init(self, extend=""):
        s = (extend or "").strip()
        if s:
            self.site = s.rstrip("/")

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _fetch(self, url):
        try:
            return requests.get(url, headers={"User-Agent": UA, "Referer": self.site + "/"},
                                timeout=15).text
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

    def _pic(self, seg):
        m = re.search(r"<img[^>]+>", seg)
        if not m:
            return ""
        img = m.group(0)
        p = ""
        m2 = re.search(r'data-src="([^"]+)"', img)
        if m2:
            p = m2.group(1)
        else:
            m2 = re.search(r'src="([^"]+)"', img)
            if m2:
                p = m2.group(1)
        return self._abs(p)

    def _parse_li(self, seg):
        am = re.search(r'<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', seg)
        if not am:
            return None
        href = am.group(1).strip()
        vid = re.sub(r"\D+", "", href)
        if not vid:
            return None
        atag = am.group(0)
        name = ""
        m = re.search(r'title="([^"]+)"', atag)
        if m:
            name = m.group(1)
        else:
            name = _text(am.group(2))
        if not name:
            return None
        remark = ""
        rm = re.search(r'<span[^>]*class="sBottom"[^>]*>([^<]*)<', seg)
        if rm:
            remark = _text(rm.group(1))
        if not remark:
            rm = re.search(r'<a[^>]*>[\s\S]*?<span>([^<]*)</span>', seg)
            if rm:
                remark = _text(rm.group(1))
        pic = ""
        im = re.search(r'<div[^>]*>[\s\S]*?<img[^>]+>', seg)
        if im:
            pic = self._pic(im.group(0))
        return {"vod_id": vid, "vod_name": name, "vod_pic": pic,
                "vod_remarks": remark}

    def homeContent(self, filter):
        cats, lst = [], []
        try:
            html = self._fetch(self.site)
            for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>([^<]*)</a>', html or ""):
                rm = re.search(r"vod-(?:type|list)-id-(\d+)", m.group(1))
                if not rm:
                    continue
                name = _text(m.group(2))
                if not name:
                    continue
                cats.append({"type_id": rm.group(1), "type_name": name})
            # 首页推荐
            segs = re.findall(r"<li[^>]*>([\s\S]*?)</li>", html)
            for seg in segs:
                it = self._parse_li(seg)
                if it:
                    lst.append(it)
        except Exception:
            pass
        fts = {}
        for cid, f in FILTERS.items():
            fts[cid] = [{"key": k, "name": n,
                         "value": [{"n": nn, "v": vv} for nn, vv in vals]}
                        for k, n, vals in f]
        return {"class": cats, "filters": fts, "list": lst[:20]}

    def homeVideoContent(self):
        return {"list": self.homeContent(False)["list"]}

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
        try:
            pg = str(pg) if str(pg).strip().isdigit() else "1"
            ex = extend or {}
            if ex.get("cateId"):
                tid = str(ex["cateId"])
            url = (f"{self.site}/vod-list-id-{tid}-pg-{pg}-order--by-time-class-0-"
                   f"year-0-letter--area--lang-.html")
            html = self._fetch(url)
            if not re.search(r'class="resize_list"[^>]*>[\s\S]*?<li', html or ""):
                html = self._fetch(f"{self.site}/vod-type-id-{tid}-pg-{pg}.html")
            lst = []
            for seg in re.findall(r"<li[^>]*>([\s\S]*?)</li>", html or ""):
                it = self._parse_li(seg)
                if it:
                    lst.append(it)
            result["list"] = lst
            n = int(pg) if pg.isdigit() else 1
            result["page"] = n
            result["pagecount"] = n if not lst else n + 1
            result["total"] = len(lst)
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0])
            html = self._fetch(f"{self.site}/vod-detail-id-{vid}.html")
            name = ""
            m = re.search(r'class="title"[^>]*>\s*<a[^>]*title="([^"]*)"', html or "")
            if m:
                name = m.group(1).strip()
            pic = ""
            m = re.search(r'class="page-hd"[^>]*>\s*<a[^>]*>\s*<img[^>]+src="([^"]+)"', html or "")
            if m:
                pic = self._abs(m.group(1))
            year, area = "", ""
            m = re.search(r'class="desc_item"[^>]*>[\s\S]*?<font[^>]*>([^<]*)</font>', html or "")
            if m:
                year = _text(m.group(1))
            m = re.search(r'class="desc_item"[^>]*>[\s\S]*?<a[^>]*>([^<]*)</a>', html or "")
            if m:
                area = _text(m.group(1))
            # 播放页集数
            ph = self._fetch(f"{self.site}/vod-play-id-{vid}-src-1-num-1.html")
            eps = []
            blocks = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', ph or "")
            for i, (href, txt) in enumerate(blocks):
                t = _text(txt) or f"第{i + 1}集"
                t = t.replace("$", "").replace("#", "").strip()
                pu = href if href.startswith("http") else self._abs(href)
                pu = self._abs(href)
                mac = ""
                m2 = RE_MAC.search(self._fetch(pu) or "")
                if m2:
                    mac = m2.group(1).strip()
                    if not mac.startswith("http"):
                        mac = self._abs(mac)
                if not mac:
                    continue
                eps.append(f"{t}${mac}")
            if not eps:
                mac = RE_MAC.search(ph or "")
                if mac and mac.group(1):
                    m2 = mac.group(1).strip()
                    if not m2.startswith("http"):
                        m2 = self._abs(m2)
                    eps.append(f"正片${m2}")
            vod = {"vod_id": vid, "vod_name": name or vid, "vod_pic": pic,
                   "vod_year": year, "vod_area": area}
            if eps:
                vod["vod_play_from"] = "糯米"
                vod["vod_play_url"] = "#".join(eps)
            else:
                vod["vod_remarks"] = "无 mac_url"
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
            html = self._fetch(f"{self.site}/index.php?m=vod-search&wd={quote(key)}")
            for seg in re.findall(r"<li[^>]*>([\s\S]*?)</li>", html or ""):
                it = self._parse_li(seg)
                if it:
                    result["list"].append(it)
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
