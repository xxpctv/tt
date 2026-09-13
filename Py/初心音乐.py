# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   初心音乐 (ChuXin)
# 播放: https://cfss.cc/api/kg/{id}.mp4

from base.spider import Spider
import requests
import json
import re
from urllib.parse import quote

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36",
    "Referer": "https://cfss.cc/mv/",
    "Accept": "*/*",
}
PIC_FALLBACK = "https://open.wya6.com/d/down/2026/fish4k.jpeg"
ARTISTS = ["周杰伦", "邓紫棋", "林俊杰", "陈奕迅"]
CHARTS = [["6666", "飙升榜"], ["8888", "TOP500"], ["24971", "会员畅听"]]
RE_MV = re.compile(r"<p[^>]*title=['\"]([^'\"]*)['\"][^>]*id=['\"]?(\d+)['\"]?[^>]*>", re.IGNORECASE)
RE_MV_FULL = re.compile(r"<p[^>]*title=['\"]([^'\"]*)['\"][^>]*id=['\"]?(\d+)['\"]?[^>]*>([\s\S]*?)</p>", re.IGNORECASE)
RE_SRC = re.compile(r"src=['\"]([^'\"]+)['\"]", re.IGNORECASE)


def _chart_name(cid):
    for c, n in CHARTS:
        if cid == c:
            return n
    return cid


def _strip_artist(s):
    idx = (s or "").find(" - ")
    return s[:idx].strip() if idx > 0 else (s or "").strip()


class Spider(Spider):
    def __init__(self):
        super().__init__()
        self._singer_pic = {}
        self._song_id = {}

    def getName(self):
        return "初心音乐"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _get(self, url):
        try:
            return requests.get(url, headers=HEADERS, timeout=12).text
        except Exception:
            return ""

    # ---- 歌手头像 (QQ 搜索) ----
    def _singer_pic_url(self, name):
        if name in self._singer_pic:
            return self._singer_pic[name]
        try:
            url = f"https://c.y.qq.com/soso/fcgi-bin/client_search_cp?w={quote(name)}&format=json&t=9&n=1"
            j = json.loads(self._get(url))
            lst = ((j.get("data") or {}).get("singer") or {}).get("list") or []
            if lst:
                pic = (lst[0].get("singerPic") or "").replace("R150x150M000", "R300x300M000")
                if pic:
                    self._singer_pic[name] = pic
                    return pic
        except Exception:
            pass
        self._singer_pic[name] = PIC_FALLBACK
        return PIC_FALLBACK

    # ---- cfss 搜索 MV ----
    def _search_mvs(self, name):
        html = self._get("https://cfss.cc/mv/?ss=" + quote(name))
        out = []
        for m in RE_MV.finditer(html or ""):
            t, i = m.group(1).strip(), m.group(2).strip()
            if t and i:
                out.append([t, i])
        return out

    # ---- 解析歌曲 -> MV id ----
    def _resolve_id(self, name):
        if not name:
            return ""
        if name in self._song_id:
            return self._song_id[name]
        try:
            lst = self._search_mvs(name)
            if not lst:
                lst = self._search_mvs(_strip_artist(name))
            if not lst and " - " in name:
                lst = self._search_mvs(name.split(" - ", 1)[0].strip())
            rid = ""
            for t, i in lst:
                if t == name:
                    rid = i
                    break
            if not rid and lst:
                rid = lst[0][1]
            if rid:
                self._song_id[name] = rid
            return rid
        except Exception:
            return ""

    # ---- 酷狗榜单歌曲 ----
    def _rank_songs(self, rankid):
        out = []
        try:
            j = json.loads(self._get(f"http://m.kugou.com/rank/info/?rankid={rankid}&page=1&json=true"))
            for it in ((j.get("songs") or {}).get("list") or []):
                fn = (it.get("filename") or "").strip()
                if fn:
                    out.append([fn, "song:" + fn])
        except Exception:
            pass
        return out

    def homeContent(self, filter):
        result = {"class": [{"type_id": "mv_artists", "type_name": "喜好歌手"},
                            {"type_id": "mv_charts", "type_name": "歌单"}],
                  "filters": {}, "list": []}
        result["list"].append({"vod_id": "117613@@周杰伦 - 晴天", "vod_name": "周杰伦 - 晴天",
                               "vod_pic": PIC_FALLBACK, "vod_remarks": "MV"})
        for name in ARTISTS:
            result["list"].append({"vod_id": "artist:" + name, "vod_name": name,
                                   "vod_pic": self._singer_pic_url(name), "vod_remarks": "歌手"})
        return result

    def homeVideoContent(self):
        return self.categoryContent("mv_artists", 1, False, {})

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            if pg > 1:
                return result
            t = str(tid or "")
            if t == "mv_artists":
                for name in ARTISTS:
                    result["list"].append({"vod_id": "artist:" + name, "vod_name": name,
                                           "vod_pic": self._singer_pic_url(name), "vod_remarks": "歌手"})
            elif t == "mv_charts":
                for cid, cname in CHARTS:
                    result["list"].append({"vod_id": "chart:" + cid, "vod_name": cname,
                                           "vod_pic": PIC_FALLBACK, "vod_remarks": "歌单"})
            elif t.startswith("chart:"):
                cid = t[6:]
                result["list"].append({"vod_id": t, "vod_name": _chart_name(cid),
                                       "vod_pic": PIC_FALLBACK, "vod_remarks": "歌单"})
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0])
            if not vid or vid.startswith("mv_artist_"):
                return {"list": []}
            # artist:
            if vid.startswith("artist:"):
                name = vid[7:]
                eps = self._search_mvs(name)
                vod = {"vod_id": vid, "vod_name": name, "vod_pic": self._singer_pic_url(name),
                       "vod_actor": name, "vod_content": "歌手：" + name, "type_name": "MV",
                       "vod_play_from": "初心",
                       "vod_play_url": "#".join(f"{t}${i}" for t, i in eps) or "暂无$empty"}
                return {"list": [vod]}
            # chart:
            if vid.startswith("chart:"):
                cid = vid[6:]
                cname = _chart_name(cid)
                eps = self._rank_songs(cid)
                vod = {"vod_id": vid, "vod_name": cname, "vod_pic": PIC_FALLBACK,
                       "vod_content": f"歌单 · {cname} · 共{len(eps)}首", "type_name": "歌单",
                       "vod_play_from": "初心",
                       "vod_play_url": "#".join(f"{t}${i}" for t, i in eps) or "暂无$empty"}
                return {"list": [vod]}
            # song: 或直接 id / 名字
            if vid.startswith("song:"):
                name = vid[5:]
            elif vid.startswith("117613@@") or "@@" in vid:
                name = vid.split("@@", 1)[0]
            else:
                name = vid
            rid = name if str(name).isdigit() else self._resolve_id(name)
            vod = {"vod_id": vid, "vod_name": name, "vod_pic": PIC_FALLBACK, "type_name": "MV",
                   "vod_play_from": "初心",
                   "vod_play_url": f"{_strip_artist(name)}${rid}" if rid else "暂无$empty"}
        except Exception:
            pass
        return {"list": [vod]}

    def playerContent(self, flag, playId, vipFlags):
        url = ""
        try:
            p = playId or ""
            if "$" in p:
                p = p[p.rfind("$") + 1:]
            if "#" in p:
                p = p[:p.index("#")]
            p = p.strip()
            if p and p != "empty":
                if p.startswith("song:"):
                    p = p[5:]
                if not p.isdigit():
                    rid = self._resolve_id(p)
                    if rid:
                        p = rid
                if p:
                    url = f"https://cfss.cc/api/kg/{p}.mp4"
        except Exception:
            pass
        return {"parse": 0, "url": url, "header": HEADERS}

    def searchContent(self, key, quick):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            html = self._get("https://cfss.cc/mv/?ss=" + quote(key))
            for m in RE_MV_FULL.finditer(html or ""):
                t, i = m.group(1).strip(), m.group(2).strip()
                if not t or not i:
                    continue
                pic = PIC_FALLBACK
                sm = RE_SRC.search(m.group(3) or "")
                if sm:
                    pic = sm.group(1)
                result["list"].append({"vod_id": f"{i}@@{t}", "vod_name": t,
                                       "vod_pic": pic, "vod_remarks": "MV"})
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
