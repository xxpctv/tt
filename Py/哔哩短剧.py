#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TVBox Python Spider - 哔哩哔哩 (Bilibili) 纯py版
用途: 作为红果短剧锁定集的免费替代源 (B站有大量UP主搬运的完整短剧/漫剧)。

能力:
  - 首页: B站全站热门推荐 (popular)
  - 分类: 关键词频道 (短剧/漫剧/修仙/逆袭/战神/甜宠/悬疑/重生/穿越/一口气看完等)
  - 搜索: B站 wbi 签名搜索 (按剧名直接找搬运版)
  - 详情: 自动解析分P (多P视频每一集=一个分P)
  - 播放: 未登录可播 360P 单段mp4 (免登录);

【可选·看高清】
  把 B站登录后的 SESSDATA 填到下面 SESSDATA 常量, 即可取 480P/1080P。
  获取方式: 电脑浏览器登录 bilibili.com → F12 → Application/应用 → Cookies
           → https://www.bilibili.com → 复制 SESSDATA 的值。
"""

import json
import re
import sys
import time
import hashlib
import threading
import urllib.parse
import urllib.request

try:
    if '..' not in sys.path:
        sys.path.append('..')
    from base.spider import Spider as _BaseSpider
except Exception:
    _BaseSpider = object


# ==================== 可选登录态 ====================
SESSDATA = ""   # 填上 B站 SESSDATA 可看高清; 留空也能播(360P)


# ==================== 常量 ====================
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 关键词频道 (分类): type_id = kw_<关键词>
# 注意: 关键词必须是 B站能直接搜到的核心词 (带"全集"后缀的组合词会 0 结果)
_KW_CHANNELS = [
    ("短剧", "短剧"),
    ("漫剧", "漫剧"),
    ("修仙短剧", "修仙短剧"),
    ("逆袭短剧", "逆袭短剧"),
    ("战神短剧", "战神短剧"),
    ("甜宠短剧", "甜宠短剧"),
    ("悬疑短剧", "悬疑短剧"),
    ("重生短剧", "重生短剧"),
    ("穿越短剧", "穿越短剧"),
    ("一口气看完", "一口气看完"),
    ("沙雕动画", "沙雕动画"),
]

# wbi mixin 混淆表 (B站固定)
_MIXIN_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


def _strip_tag(s):
    return re.sub(r"<[^>]+>", "", str(s or ""))


def _pic(url):
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    return url


# ==================== B站 API 客户端 ====================
class _BiliApi(object):
    def __init__(self):
        self._lock = threading.Lock()
        self._cookie = {}
        self._img_key = ""
        self._sub_key = ""
        self._ready = False

    def _set_cookie(self, headers):
        for c in headers.get_all("Set-Cookie") or []:
            m = re.match(r"([^=]+)=([^;]+)", c)
            if m:
                self._cookie[m.group(1)] = m.group(2)

    def _request(self, url, referer="https://www.bilibili.com/"):
        req = urllib.request.Request(url)
        req.add_header("User-Agent", _UA)
        req.add_header("Referer", referer)
        if SESSDATA:
            self._cookie["SESSDATA"] = SESSDATA
        if self._cookie:
            req.add_header("Cookie", "; ".join(
                "%s=%s" % (k, v) for k, v in self._cookie.items()))
        with urllib.request.urlopen(req, timeout=20) as r:
            self._set_cookie(r.headers)
            return json.loads(r.read().decode("utf-8"))

    def _ensure(self):
        with self._lock:
            if self._ready:
                return
            try:
                # 1. buvid3/buvid4
                spi = self._request(
                    "https://api.bilibili.com/x/frontend/finger/spi")
                d = spi.get("data") or {}
                if d.get("b_3"):
                    self._cookie["buvid3"] = d["b_3"]
                if d.get("b_4"):
                    self._cookie["buvid4"] = d["b_4"]
                # 2. wbi keys
                nav = self._request(
                    "https://api.bilibili.com/x/web-interface/nav")
                wbi = (nav.get("data") or {}).get("wbi_img") or {}
                self._img_key = wbi.get("img_url", "").rsplit("/", 1)[-1].split(".")[0]
                self._sub_key = wbi.get("sub_url", "").rsplit("/", 1)[-1].split(".")[0]
                self._ready = bool(self._img_key and self._sub_key)
            except Exception:
                self._ready = False

    def _mixin_key(self):
        raw = self._img_key + self._sub_key
        return "".join(raw[i] for i in _MIXIN_TAB)[:32]

    def _sign(self, params):
        params = dict(params)
        params["wts"] = int(time.time())
        query = urllib.parse.urlencode(sorted(params.items()))
        params["w_rid"] = hashlib.md5(
            (query + self._mixin_key()).encode("utf-8")).hexdigest()
        return urllib.parse.urlencode(params)

    def search(self, keyword, page=1, order="totalrank"):
        self._ensure()
        params = {"search_type": "video", "keyword": keyword,
                  "page": page, "order": order, "platform": "Web"}
        url = ("https://api.bilibili.com/x/web-interface/wbi/search/type?"
               + self._sign(params))
        r = self._request(url)
        if r.get("code") != 0:
            # 签名可能过期: 强制重建一次
            self._ready = False
            self._ensure()
            url = ("https://api.bilibili.com/x/web-interface/wbi/search/type?"
                   + self._sign(params))
            r = self._request(url)
        return (r.get("data") or {}).get("result") or []

    def view(self, bvid):
        self._ensure()
        url = "https://api.bilibili.com/x/web-interface/view?bvid=%s" % bvid
        r = self._request(url)
        return r.get("data") or {}

    def popular(self, page=1):
        self._ensure()
        url = ("https://api.bilibili.com/x/web-interface/popular?ps=30&pn=%s"
               % page)
        r = self._request(url)
        return (r.get("data") or {}).get("list") or []

    def playurl(self, bvid, cid):
        """未登录返回单段低清mp4; 登录(SESSDATA)返回高清。"""
        self._ensure()
        qn = 80 if SESSDATA else 32
        params = {"bvid": bvid, "cid": cid, "qn": qn, "fnval": 1,
                  "fourk": 1 if SESSDATA else 0,
                  "platform": "html5", "high_quality": 1}
        url = ("https://api.bilibili.com/x/player/wbi/playurl?"
               + self._sign(params))
        r = self._request(url)
        data = r.get("data") or {}
        durl = data.get("durl") or []
        if not durl and not SESSDATA:
            # html5 失败时回退 PC 低清
            params = {"bvid": bvid, "cid": cid, "qn": 16, "fnval": 1,
                      "platform": "PC"}
            r2 = self._request(
                "https://api.bilibili.com/x/player/wbi/playurl?"
                + self._sign(params))
            durl = ((r2.get("data") or {}).get("durl")) or []
        return durl


# ==================== Spider ====================
class Spider(_BaseSpider):
    def __init__(self):
        self.api = _BiliApi()

    def getName(self):
        return "哔哩哔哩"

    def init(self, cfg=""):
        pass

    def getDependence(self):
        return []

    def download(self, path, url):
        try:
            urllib.request.urlretrieve(url, path)
        except Exception:
            pass

    # ---------- 搜索结果 / 视频 -> 卡片 ----------
    @staticmethod
    def _match_title(keyword, v):
        """完整关键词命中【标题】或【作者(UP主)】才算相关;
        只命中简介/详情(description)的一律剔除。关键词不拆分。
        B站短剧的剧名/演员名通常写在标题里, 故 title 命中即覆盖剧名/演员。"""
        kw = (keyword or "").strip()
        if not kw:
            return True
        title = _strip_tag(v.get("title"))
        author = v.get("author", "") or ""
        return (kw in title) or (kw in author)

    def _card_search(self, v):
        title = _strip_tag(v.get("title"))
        author = v.get("author", "")
        dur = v.get("duration", "")
        remark = dur if dur else author
        return {
            "vod_id": v.get("bvid", ""),
            "vod_name": title,
            "vod_pic": _pic(v.get("pic")),
            "vod_remarks": str(remark),
        }

    def _card_video(self, v):
        owner = ((v.get("owner") or {}).get("name")) or ""
        return {
            "vod_id": v.get("bvid", ""),
            "vod_name": v.get("title", ""),
            "vod_pic": _pic(v.get("pic")),
            "vod_remarks": owner,
        }

    # ---------- 首页 ----------
    def homeContent(self, filter=True):
        classes = [{"type_name": "热门推荐", "type_id": "home"}]
        classes += [{"type_name": name, "type_id": "kw_%s" % kw}
                    for name, kw in _KW_CHANNELS]
        result = {"class": classes, "filters": {}, "list": []}
        try:
            result["list"] = [self._card_video(v)
                              for v in self.api.popular(1)]
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        try:
            return {"list": [self._card_video(v)
                             for v in self.api.popular(1)]}
        except Exception:
            return {"list": []}

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg=1, filter=1, extend=None):
        page = 1
        try:
            page = int(pg)
        except (TypeError, ValueError):
            page = 1
        result = {"list": [], "page": page, "pagecount": page,
                  "limit": 30, "total": 0}
        try:
            if str(tid) == "home":
                items = self.api.popular(page)
                cards = [self._card_video(v) for v in items]
            else:
                kw = str(tid)
                if kw.startswith("kw_"):
                    kw = kw[3:]
                items = self.api.search(kw, page=page, order="totalrank")
                cards = [self._card_search(v) for v in items]
            if cards:
                result["list"] = cards
                result["total"] = (page - 1) * 30 + len(cards)
                result["pagecount"] = page + 1 if len(cards) >= 20 else page
        except Exception:
            pass
        return result

    # ---------- 详情 ----------
    def detailContent(self, ids):
        result = {"list": []}
        try:
            ids_list = ids if isinstance(ids, list) else [ids]
            bvid = str(ids_list[0]) if ids_list else ""
            if not bvid:
                return result
            data = self.api.view(bvid)
            if not data:
                return result
            pages = data.get("pages") or []
            owner = ((data.get("owner") or {}).get("name")) or ""
            if not pages:
                pages = [{"cid": data.get("cid"), "part": data.get("title")}]
            eps = []
            for i, p in enumerate(pages):
                # part 标题可能含 '#'/ '$', 会破坏集间分隔, 必须剔除
                part = str(p.get("part") or ("第%s集" % (i + 1)))
                part = part.replace("#", "").replace("$", "").strip()
                part = part or ("第%s集" % (i + 1))
                # 注意: 集间分隔符是 '#', 故 bvid/cid 用 '@' 分隔, 不能用 '#'
                ep_id = "%s@%s" % (bvid, p.get("cid"))
                eps.append("%s$%s" % (part, ep_id))
            desc = data.get("desc", "") or ""
            detail = {
                "vod_id": bvid,
                "vod_name": data.get("title", ""),
                "vod_pic": _pic(data.get("pic")),
                "vod_content": desc,
                "vod_remarks": ("UP:%s" % owner) if owner else "",
                "vod_year": "",
                "vod_area": "",
                "vod_actor": "",
                "vod_tag": "",
                "vod_play_from": "B站",
                "vod_play_url": "#".join(eps),
            }
            result["list"] = [detail]
        except Exception:
            pass
        return result

    # ---------- 搜索 ----------
    def searchContent(self, key, quick=False, pg=1):
        page = 1
        try:
            page = int(pg)
        except (TypeError, ValueError):
            page = 1
        try:
            items = self.api.search(key, page=page, order="totalrank")
            # 客户端过滤: 完整关键词只匹配标题/作者(剧名/演员在标题), 排除简介命中
            items = [v for v in items if self._match_title(key, v)]
            return {"list": [self._card_search(v) for v in items]}
        except Exception:
            return {"list": []}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags=None):
        result = {
            "parse": 0,
            "playUrl": "",
            "url": "",
            "header": json.dumps({
                "User-Agent": _UA,
                "Referer": "https://www.bilibili.com/",
            }, ensure_ascii=False),
        }
        try:
            parts = str(id).split("@")
            bvid = parts[0]
            cid = parts[1] if len(parts) > 1 else ""
            if not cid:
                data = self.api.view(bvid)
                cid = data.get("cid")
            durl = self.api.playurl(bvid, cid)
            if durl:
                # 多段时优先取单段; 低清html5通常单段
                result["url"] = durl[0]["url"]
        except Exception:
            pass
        return result

    # ---------- get 别名 ----------
    def getHomeContent(self, filter=True):
        return self.homeContent(filter)

    def getHomeVideoContent(self):
        return self.homeVideoContent()

    def getCategoryContent(self, tid, pg=1, filter=1, extend=None):
        return self.categoryContent(tid, pg, filter, extend)

    def getDetailContent(self, array):
        return self.detailContent(array)

    def getSearchContent(self, key, quick=False, pg=1):
        return self.searchContent(key, quick, pg)

    def getPlayerContent(self, flag, id, vipFlags=None):
        return self.playerContent(flag, id, vipFlags)
