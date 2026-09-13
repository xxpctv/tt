# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   酷酷音乐 (KuKuMusic)
# 播放: kuwo convert_url_with_sign (128k -> 320k) -> antiserver convert_url 兜底

from base.spider import Spider
import requests
import json
from urllib.parse import quote

CATES = [["1", "华语男"], ["2", "华语女"], ["3", "华语组合"], ["4", "日韩男"], ["5", "日韩女"],
         ["6", "日韩组合"], ["7", "欧美男"], ["8", "欧美女"], ["9", "欧美组合"], ["0", "其他"]]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
           "Referer": "http://www.kuwo.cn/"}


def _https(u):
    u = (u or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("http://"):
        return "https://" + u[7:]
    return u


class Spider(Spider):
    def getName(self):
        return "酷酷音乐"

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
            return "{}"

    def _json(self, url):
        try:
            return json.loads(self._get(url))
        except Exception:
            return {}

    def homeContent(self, filter):
        return {"class": [{"type_id": c[0], "type_name": c[1]} for c in CATES], "filters": {}}

    def homeVideoContent(self):
        return self.categoryContent("1", 1, False, {})

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 9999, "limit": 90, "total": 999999}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            j = self._json(f"http://wapi.kuwo.cn/api/www/artist/artistInfo?category={tid}"
                           f"&prefix=&pn={pg}&rn=30")
            for it in ((j.get("data") or {}).get("artistList") or []):
                aid = str(it.get("id") or "")
                name = str(it.get("name") or "")
                if not aid or not name:
                    continue
                pic = it.get("pic300") or it.get("pic") or it.get("pic120") or ""
                result["list"].append({"vod_id": aid, "vod_name": name,
                                       "vod_pic": _https(pic), "vod_remarks": ""})
        except Exception:
            pass
        return result

    def _artist_songs(self, aid):
        out = []
        try:
            for p in range(1, 11):
                j = self._json(f"http://wapi.kuwo.cn/api/www/artist/artistMusic?artistid={aid}"
                               f"&pn={p}&rn=30")
                if j.get("code") != 200:
                    break
                lst = (j.get("data") or {}).get("list") or []
                if not lst:
                    break
                for it in lst:
                    name = (it.get("name") or "").strip()
                    rid = str(it.get("rid") or "")
                    if not name or not rid:
                        continue
                    album = (it.get("album") or "").strip()
                    ep = f"{name} - {album}${rid}" if album else f"{name}${rid}"
                    out.append(ep)
                    if len(out) >= 300:
                        return out
        except Exception:
            pass
        return out

    def detailContent(self, ids):
        vod = {}
        try:
            aid = str(ids[0])
            j = self._json(f"http://wapi.kuwo.cn/api/www/artist/artist?artistid={aid}")
            d = j.get("data")
            if not d:
                return {"list": [{"vod_id": aid, "vod_name": "加载失败", "vod_pic": "",
                                  "vod_remarks": "加载失败", "vod_actor": "未知",
                                  "vod_content": "加载歌手信息失败", "vod_play_from": "酷酷",
                                  "vod_play_url": ""}]}
            name = d.get("name") or ""
            pic = _https(d.get("pic300") or d.get("pic") or "")
            import re as _re
            info = _re.sub(r"<[^>]+>", "", d.get("info") or "").replace("&nbsp;", " ").strip()
            eps = self._artist_songs(aid)
            vod = {"vod_id": aid, "vod_name": name, "vod_pic": pic,
                   "vod_remarks": f"歌曲 :   {min(len(eps), 300)}首",
                   "vod_actor": name, "vod_content": info or "暂无歌手简介",
                   "vod_play_from": "酷酷", "vod_play_url": "#".join(eps)}
        except Exception:
            pass
        return {"list": [vod]}

    def _sign_url(self, rid, bitrate):
        j = self._json(f"https://nmobi.kuwo.cn/mobi.s?f=web&user=0"
                       f"&source=kwplayer_ar_4.4.2.7_B_nuoweida_vh.apk"
                       f"&type=convert_url_with_sign&rid={rid}&bitrate={bitrate}&format=mp3")
        if j.get("code") == 200:
            u = ((j.get("data") or {}).get("url")) or ""
            if u.startswith("http"):
                return u
        return ""

    def _anti_url(self, rid):
        try:
            u = "MUSIC_" + rid if not rid.startswith("MUSIC_") else rid
            r = requests.get(f"http://antiserver.kuwo.cn/anti.s?type=convert_url&format=mp3"
                             f"&response=url&rid={u}",
                             headers={"User-Agent": "Mozilla/5.0 (Linux; Android 10)",
                                      "Referer": "https://www.kuwo.cn/"}, timeout=12)
            t = r.text.strip()
            return t if t.startswith("http") else ""
        except Exception:
            return ""

    def playerContent(self, flag, playId, vipFlags):
        url = ""
        try:
            p = playId or ""
            if "$" in p:
                p = p[p.rfind("$") + 1:]
            if p.startswith("MUSIC_"):
                p = p[6:]
            p = p.strip()
            if p:
                url = self._sign_url(p, 128)
                if not url:
                    url = self._sign_url(p, 320)
                if not url:
                    url = self._anti_url(p)
        except Exception:
            pass
        return {"parse": 0, "url": url,
                "header": {"User-Agent": "Mozilla/5.0 (Linux; Android 10)",
                           "Referer": "https://www.kuwo.cn/", "Accept": "*/*"}}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            try:
                pg = max(1, int(pg))
            except Exception:
                pg = 1
            j = self._json(f"https://search.kuwo.cn/r.s?client=kt&pn={(pg - 1) * 30}&rn=30&all={quote(key)}"
                           f"&vipver=1&ft=artist&encoding=utf8&rformat=json&mobi=1")
            base_pic = j.get("BASEPICPATH", "http://img1.kuwo.cn/star/starheads/")
            for it in j.get("abslist") or []:
                aid = str(it.get("ARTISTID") or it.get("DC_TARGETID") or "")
                if not aid:
                    continue
                name = it.get("ARTIST") or ""
                if not name:
                    continue
                pic = it.get("hts_PICPATH") or ""
                if not pic and it.get("PICPATH"):
                    pic = base_pic + it["PICPATH"]
                num = it.get("SONGNUM") or "0"
                result["list"].append({"vod_id": aid, "vod_name": name,
                                       "vod_pic": _https(pic),
                                       "vod_remarks": f"歌曲 :  {num}首"})
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
