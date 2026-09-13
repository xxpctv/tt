# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   即刻云盘 (Jike)
# 说明: 列表/搜索完整(分享链接即 vod_id); 原版依赖 QuarkYun token 解析分享链,
#      播放时原样返回分享链.

from base.spider import Spider
import requests
import re
import json
from urllib.parse import quote

API = "https://api.uuuka.com/api"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
PIC_QUARK = "https://pic7.fukit.cn/autoupload/gE6Y0Af2tjXBCNig6CtNDI12_FRYNb81z6UPhMWD8iI/20260503/LX2y/1200X800/quark.jpg"
PIC_UC = "https://pic7.fukit.cn/autoupload/gE6Y0Af2tjXBCNig6CtNDI12_FRYNb81z6UPhMWD8iI/20260503/kbEn/1200X800/uc.jpg"
PIC_BAIDU = "https://pic7.fukit.cn/autoupload/gE6Y0Af2tjXBCNig6CtNDI12_FRYNb81z6UPhMWD8iI/20260503/dyXZ/1200X800/baidu.jpg"
PIC_123 = "https://pic7.fukit.cn/autoupload/gE6Y0Af2tjXBCNig6CtNDI12_FRYNb81z6UPhMWD8iI/20260503/N1l5/1200X800/123.jpg"
PIC_189 = "https://pic7.fukit.cn/autoupload/gE6Y0Af2tjXBCNig6CtNDI12_FRYNb81z6UPhMWD8iI/20260503/n1b9/1200X800/189.jpg"
PIC_ALI = "https://pic7.fukit.cn/autoupload/gE6Y0Af2tjXBCNig6CtNDI12_FRYNb81z6UPhMWD8iI/20260503/8Yr6/1200X800/aliyun.jpg"


def pic_for_link(link):
    if "pan.quark.cn" in link:
        return PIC_QUARK
    if "drive.uc.cn" in link:
        return PIC_UC
    if "pan.baidu.com" in link:
        return PIC_BAIDU
    if "www.123" in link:
        return PIC_123
    if "cloud.189.cn" in link:
        return PIC_189
    if "aliyundrive.com" in link or "alipan.com" in link:
        return PIC_ALI
    return PIC_QUARK


def _title_clean(t):
    t = (t or "").strip()
    i = t.find("\u300a")
    if i < 0:
        return t
    j = t.find("\u300b", i)
    if j >= 0 and j > i:
        return t[i + 1:j].strip()
    i += 1
    return t[i:].strip() if i < len(t) else t


def _parse_items(items):
    out = []
    for it in items:
        link = str(it.get("source_link") or "").strip()
        if not link:
            continue
        title = _title_clean(it.get("title") or "")
        if not title:
            title = "云盘资源"
        out.append({"vod_id": link, "vod_name": title,
                    "vod_pic": pic_for_link(link),
                    "vod_remarks": str(it.get("update_time") or "")})
    return out


class Spider(Spider):
    def getName(self):
        return "即刻云盘"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _get(self, url):
        try:
            r = requests.get(url, headers={"User-Agent": UA,
                                           "Referer": "https://api.uuuka.com/"}, timeout=15)
            return json.loads(r.text or "{}")
        except Exception:
            return {}

    def homeContent(self, filter):
        return {"class": [{"type_id": "movie", "type_name": "电影"},
                          {"type_id": "tv", "type_name": "电视剧"},
                          {"type_id": "dongman", "type_name": "动漫"},
                          {"type_id": "post", "type_name": "短剧"}],
                "filters": {}, "list": []}

    def homeVideoContent(self):
        return self.categoryContent("movie", 1, False, {})

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            j = self._get(f"{API}/contents/{str(tid)}?page={pg}&limit=20")
            if not j.get("success"):
                return result
            data = j.get("data") or {}
            result["list"] = _parse_items(data.get("items") or [])
            result["page"] = data.get("page") or pg
            result["pagecount"] = data.get("total_pages") or 1
            result["total"] = data.get("total") or len(result["list"])
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            link = str(ids[0]).strip()
            if not link.startswith("http"):
                return {"list": [], "error": "无效的分享链接"}
            name = ("夸克分享" if "pan.quark.cn" in link else
                    "UC分享" if "drive.uc.cn" in link else
                    "百度分享" if "pan.baidu.com" in link else
                    "123分享" if "www.123" in link else
                    "天翼分享" if "cloud.189.cn" in link else
                    "阿里分享" if ("aliyundrive.com" in link or "alipan.com" in link) else
                    "网盘分享")
            vod = {"vod_id": link, "vod_name": name,
                   "vod_pic": pic_for_link(link),
                   "vod_play_from": "网盘",
                   "vod_play_url": f"网盘1${link}"}
        except Exception:
            pass
        return {"list": [vod]}

    def playerContent(self, flag, playId, vipFlags):
        p = playId or ""
        if "$" in p:
            p = p[p.rfind("$") + 1:]
        return {"parse": 0, "url": p.strip(),
                "header": {"User-Agent": UA, "Referer": "https://api.uuuka.com/"}}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            j = self._get(f"{API}/search?keyword={quote(key)}&page=1&limit=20")
            if not j.get("success"):
                return result
            data = j.get("data") or {}
            result["list"] = _parse_items(data.get("items") or [])
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
