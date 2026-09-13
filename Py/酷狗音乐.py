# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   酷狗音乐 (Kugou)
# 播放链路: getSongInfo 直链 -> gequbao/s 搜索 -> common-play-url (多级兜底)

from base.spider import Spider
import requests
import json
import re
from urllib.parse import quote

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
UA_KG = "KuGou2012-9108-Expand133ManagerReview-117000-Android2010-9108-AddPlatinumDeviceExpand1-0"
PLACEHOLDER = "https://p1.music.126.net/5KJI2mq0G0OQHQaAfAJfwg==/109951173289563385.jpg?param=300y300"
RE_PLAY_ID = re.compile(r'play_id["\':]+([^"\'\\]+)')


def _pic(u):
    return (u or PLACEHOLDER).replace("{size}", "400")


def _name(it):
    fn = it.get("filename") or it.get("songname") or ""
    if not fn:
        fn = f"{it.get('singername') or ''} - {it.get('songname') or ''}"
    return str(fn).strip()


def _song_id(it):
    h = it.get("sqhash") or it.get("hash") or ""
    if not h:
        return ""
    return f"kugou-mp3_{h}_{it.get('album_id') or ''}_{it.get('album_audio_id') or ''}"


def _song_pic(it):
    p = it.get("album_sizable_cover") or it.get("imgurl") or ""
    if not p:
        tp = it.get("trans_param") or {}
        p = tp.get("union_cover") or ""
    return _pic(p)


class Spider(Spider):
    def getName(self):
        return "酷狗音乐"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _kg_json(self, url):
        try:
            r = requests.get(url, headers={"User-Agent": UA_KG}, timeout=12)
            return r.json()
        except Exception:
            return {}

    def _get(self, url, referer=""):
        hdrs = {"User-Agent": UA}
        if referer:
            hdrs["Referer"] = referer
        try:
            return requests.get(url, headers=hdrs, timeout=12).text
        except Exception:
            return ""

    def homeContent(self, filter):
        return {"class": [{"type_id": "hot", "type_name": "热门榜"},
                          {"type_id": "special", "type_name": "特色榜"},
                          {"type_id": "global", "type_name": "全球榜"}],
                "filters": {}}

    def homeVideoContent(self):
        return self.categoryContent("hot", 1, False, {})

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 30, "total": 9999}
        if str(pg) != "1":
            return result
        try:
            j = self._kg_json("http://mobilecdnbj.kugou.com/api/v3/rank/list?version=9108&plat=0"
                              "&showtype=2&parentid=0&apiver=6&area_code=1&withsong=0&with_res_tag=0")
            for it in ((j.get("data") or {}).get("info") or []):
                cls = str(it.get("classify") or "")
                if tid == "hot":
                    ok = cls == "1" or cls == "2"
                elif tid == "special":
                    ok = cls == "3" or cls == "5"
                else:
                    ok = cls == "4" or cls == "2"
                if not ok:
                    continue
                rankid = str(it.get("rankid") or "")
                if not rankid:
                    continue
                result["list"].append({"vod_id": "kugou_" + rankid,
                                       "vod_name": it.get("rankname") or "",
                                       "vod_pic": _pic(it.get("imgurl") or ""),
                                       "vod_remarks": "榜单"})
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0])
            if vid.startswith("kugou-mp3_") or vid.startswith("kugou-mv_"):
                parts = vid[len("kugou-"):].split("_")
                h = parts[1] if len(parts) > 1 else ""
                j = self._kg_json(f"https://m.kugou.com/app/i/getSongInfo.php?cmd=playInfo&hash={h}")
                name = j.get("fileName") or "酷狗单曲"
                pic = _pic(j.get("album_img") or "")
                vod = {"vod_id": vid, "vod_name": name, "vod_pic": pic,
                       "vod_remarks": "单曲", "vod_play_from": "MP3",
                       "vod_play_url": f"{name}${vid}", "vod_content": "酷狗音乐 · 单曲"}
                return {"list": [vod]}
            if vid.startswith("kugou_"):
                rankid = vid[6:]
                j = self._kg_json(f"http://mobilecdnbj.kugou.com/api/v3/rank/song?version=9108"
                                  f"&ranktype=0&plat=0&pagesize=200&area_code=1&page=1"
                                  f"&volid=35050&rankid={rankid}&with_res_tag=0")
                mp3s, mvs, pic = [], [], PLACEHOLDER
                for it in ((j.get("data") or {}).get("info") or []):
                    nm = _name(it)
                    sid = _song_id(it)
                    if sid:
                        mp3s.append(f"{nm}${sid}")
                    if it.get("mvhash"):
                        mvs.append(f"{nm}${'kugou-mv_' + str(it['mvhash'])}")
                    if pic == PLACEHOLDER:
                        pic = _song_pic(it)
                vod = {"vod_id": vid, "vod_name": f"酷狗榜单 {rankid}", "vod_pic": pic,
                       "vod_remarks": f"{len(mp3s)}首", "vod_play_from": "MP3$$$MV",
                       "vod_play_url": "#".join(mp3s) + "$$$" + "#".join(mvs),
                       "vod_content": "酷狗音乐 · 榜单"}
                return {"list": [vod]}
        except Exception:
            pass
        return {"list": [vod]}

    def _gequbao(self, song_name, author=""):
        # gequbao 搜索 -> 详情页 -> play_id -> common-play-url
        try:
            html = self._get("https://www.gequbao.com/s/" + quote(song_name), "https://www.gequbao.com/")
            href, title = "", ""
            for m in re.finditer(r'<a[^>]+href="(/music/[^"]+)"[^>]*>(.*?)</a>', html, re.S):
                href = m.group(1)
                title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if not href:
                return ""
            if author and author not in title and song_name not in title:
                return ""
            page = self._get("https://www.gequbao.com" + href, "https://www.gequbao.com/")
            m = RE_PLAY_ID.search(page or "")
            if not m:
                return ""
            pid = m.group(1)
            body = "id=" + quote(pid)
            hdrs = {"User-Agent": UA, "Referer": "https://www.gequbao.com" + href,
                    "Content-Type": "application/x-www-form-urlencoded"}
            r = requests.post("https://www.gequbao.com/member/common-play-url", data=body,
                              headers=hdrs, timeout=12)
            j = r.json()
            if j.get("code") == 1:
                return ((j.get("data") or {}).get("url")) or ""
        except Exception:
            pass
        return ""

    def playerContent(self, flag, playId, vipFlags):
        url = ""
        try:
            p = playId or ""
            if "-" in p:
                parts = p.split("-", 1)
                if len(parts) == 2:
                    p = parts[1]
            if p.startswith("mp3_"):
                h = p.split("_", 1)[1]
                j = self._kg_json(f"https://m.kugou.com/app/i/getSongInfo.php?cmd=playInfo&hash={h}")
                u = j.get("url") or ""
                if not u:
                    bu = j.get("backup_url")
                    if isinstance(bu, list) and bu:
                        u = bu[0]
                    elif isinstance(bu, str):
                        u = bu
                if not u:
                    err = j.get("error") or ""
                    if "付费" not in err:
                        u = ""
                if not u:
                    song = j.get("songName") or ""
                    author = j.get("author_name") or j.get("singerName") or ""
                    if song:
                        url = self._gequbao(song, author)
                        if url:
                            return {"parse": 0, "url": url,
                                    "header": {"User-Agent": UA, "Referer": "https://www.gequbao.com/"}}
                    return {"parse": 0, "url": "", "header": {"User-Agent": UA_KG}}
                url = u
            elif p.startswith("mv_"):
                h = p.split("_", 1)[1]
                j = self._kg_json(f"https://m.kugou.com/app/i/mv.php?cmd=100&hash={h}&ismp3=1&ext=mp4")
                mv = j.get("mvdata") or {}
                if "sq" in mv:
                    url = (mv.get("sq") or {}).get("downurl") or ""
                elif "le" in mv:
                    url = (mv.get("le") or {}).get("downurl") or ""
            else:
                url = p
        except Exception:
            pass
        hdrs = {"User-Agent": UA_KG}
        if "gequbao" in url or "kuwo.cn" in url:
            hdrs = {"User-Agent": UA, "Referer": "https://www.gequbao.com/"}
        return {"parse": 0, "url": url, "header": hdrs}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            j = self._kg_json(f"http://mobilecdn.kugou.com/api/v3/search/song?format=json"
                              f"&keyword={quote(key)}&page={pg}&pagesize=30&showtype=1")
            for it in ((j.get("data") or {}).get("info") or []):
                sid = _song_id(it)
                if not sid:
                    continue
                result["list"].append({"vod_id": sid, "vod_name": _name(it),
                                       "vod_pic": _song_pic(it),
                                       "vod_remarks": it.get("singername") or ""})
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
