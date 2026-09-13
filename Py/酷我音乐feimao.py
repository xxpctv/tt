# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   酷我音乐 (KuWo)
# 播放: 酷我 convert_url_with_sign 接口 (320k -> 128k 兜底)

from base.spider import Spider
import requests
import json
import time
from urllib.parse import quote

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "http://www.kuwo.cn/",
}
PLACEHOLDER_PIC = "https://p1.music.126.net/5KJI2mq0G0OQHQaAfAJfwg==/109951173289563385.jpg?param=300y300"


def _first(*args):
    for a in args:
        if a:
            return a
    return ""


class Spider(Spider):
    def getName(self):
        return "酷我音乐"

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

    def _json(self, url):
        try:
            return json.loads(self._get(url))
        except Exception:
            return {}

    @staticmethod
    def _song_ep(it):
        rid = it.get("id")
        if not rid:
            return ""
        name = _first(it.get("name"), it.get("SONGNAME"), it.get("displaysongname"))
        artist = _first(it.get("artist"), it.get("ARTIST"), it.get("FARTIST"), it.get("displayartistname"))
        if artist:
            name = f"{name} [{artist}]"
        return f"{name}${rid}&&{it.get('albumpic') or ''}&&{it.get('artistPic') or ''}"

    def homeContent(self, filter):
        return {"class": [{"type_id": "hot", "type_name": "热门歌单"},
                          {"type_id": "new", "type_name": "新歌推荐"}],
                "filters": {}}

    def homeVideoContent(self):
        return self.categoryContent("hot", 1, False, {})

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 999, "limit": 30, "total": 999999}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            url = (f"http://wapi.kuwo.cn/api/pc/classify/playlist/getRcmPlayList"
                   f"?loginUid=0&loginSid=0&appUid=76039576&rn=30&order={tid}&pn={pg}"
                   f"&_={int(time.time() * 1000)}")
            j = self._json(url)
            data = j.get("data")
            arr = (data or {}).get("data") if isinstance(data, dict) else data
            if isinstance(arr, dict):
                arr = arr.get("data") or arr.get("list")
            for it in arr or []:
                pid = _first(it.get("id"), it.get("pid"))
                if not pid:
                    continue
                name = _first(it.get("name"), it.get("title"), "未命名歌单")
                pic = _first(it.get("img"), it.get("pic"), it.get("cover"))
                info = _first(it.get("info"), it.get("uname"), it.get("userName"))
                result["list"].append({"vod_id": str(pid), "vod_name": name,
                                       "vod_pic": pic, "vod_remarks": info})
            result["page"] = pg
        except Exception:
            pass
        return result

    @staticmethod
    def _single_vod(rid):
        return {"vod_id": rid, "vod_name": "酷我单曲", "vod_pic": PLACEHOLDER_PIC,
                "vod_remarks": "酷我音乐", "vod_play_from": "酷我歌单",
                "vod_play_url": f"酷我单曲${rid}", "vod_content": "酷我音乐 · 单曲"}

    def detailContent(self, ids):
        vod = {}
        try:
            pid = str(ids[0])
            url = (f"http://nplserver.kuwo.cn/pl.svc?op=getlistinfo&pid={pid}"
                   f"&pn=0&rn=200&encode=utf8&keyset=pl2012&identity=kuwo&pcmp4=1"
                   f"&vipver=MUSIC_9.1.1.2_BCS2&newver=1")
            j = self._json(url)
            eps = []
            for it in j.get("musiclist") or []:
                ep = self._song_ep(it)
                if ep:
                    eps.append(ep)
            if not eps and str(pid).isdigit():
                return {"list": [self._single_vod(pid)]}
            name = _first(j.get("name"), j.get("title"), "酷我歌单")
            pic = _first(j.get("pic"), j.get("img"), PLACEHOLDER_PIC)
            info = _first(j.get("info"), j.get("desc"))
            vod = {
                "vod_id": pid, "vod_name": name, "vod_pic": pic,
                "vod_remarks": f"{len(eps)}首",
                "vod_play_from": "酷我歌单", "vod_play_url": "#".join(eps),
                "vod_content": info,
            }
        except Exception:
            pass
        return {"list": [vod]}

    def _play_url(self, rid, br):
        url = (f"http://nmobi.kuwo.cn/mobi.s?f=web&user=0"
               f"&source=kwplayerhd_ar_4.3.0.8_tianbao_T1A_qirui.apk"
               f"&type=convert_url_with_sign&rid={rid}&br={br}")
        j = self._json(url)
        return (j.get("data") or {}).get("url") or ""

    def playerContent(self, flag, playId, vipFlags):
        url = ""
        try:
            p = playId or ""
            if "&&" in p:
                p = p.split("&&", 1)[0]
            if "$" in p:
                p = p[p.rfind("$") + 1:]
            rid = p.strip()
            url = self._play_url(rid, "320kmp3")
            if not url:
                url = self._play_url(rid, "128kmp3")
        except Exception:
            pass
        return {"parse": 0, "url": url, "header": HEADERS}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            url = (f"https://search.kuwo.cn/r.s?client=kt&all={quote(key)}"
                   f"&pn=0&rn=20&vipver=1&ft=music&encoding=utf8&rformat=json&mobi=1")
            txt = self._get(url).strip()
            if txt.startswith("try{"):
                txt = txt[4:]
            if txt.endswith("}catch(e){}"):
                txt = txt[:-len("}catch(e){}")]
            j = json.loads(txt or "{}")
            for it in j.get("abslist") or []:
                rid = str(it.get("MUSICRID") or "").replace("MUSIC_", "")
                if not rid:
                    continue
                name = it.get("NAME") or ""
                artist = it.get("ARTIST") or ""
                title = f"{name} - {artist}" if artist else name
                result["list"].append({"vod_id": rid, "vod_name": title,
                                       "vod_pic": it.get("hts_MVPIC") or "",
                                       "vod_remarks": "酷我音乐"})
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
