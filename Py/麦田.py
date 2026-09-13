# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   麦田 (AppV6)
# 说明: 完整复刻; ext 需填 "mtys.php 一类入口" host(如 https://xxx/yyy/mtys.php).
#       首页导航/推荐/分类(过滤)/详情(多线路)/播放(直链 或 ?url=/?key= 二次解析)/搜索 全可用.

from base.spider import Spider
import requests
import re
import json
from urllib.parse import quote

UA = "okhttp/4.9.3"


class Spider(Spider):
    def __init__(self):
        super().__init__()
        self.a = ""

    def getName(self):
        return "麦田"

    def init(self, extend=""):
        s = (extend or "").strip()
        if s:
            self.a = re.sub(r"/+$", "", s)

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _get(self, url):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
            return r.json() if r.text.strip() else {}
        except Exception:
            return {}

    def _d(self, arr):
        out = []
        for it in arr or []:
            if not isinstance(it, dict):
                continue
            out.append({"vod_id": str(it.get("vod_id") or ""),
                        "vod_name": str(it.get("vod_name") or ""),
                        "vod_pic": str(it.get("vod_pic") or ""),
                        "vod_remarks": str(it.get("vod_remarks") or "")})
        return out

    def _filters(self, te):
        if not isinstance(te, dict):
            return []
        fts = []
        for key, name in (("class", "类型"), ("area", "地区"),
                          ("year", "年份"), ("lang", "语言")):
            vals = [v.strip() for v in str(te.get(key) or "").split(",") if v.strip()]
            if len(vals) > 1:
                fts.append({"key": key, "name": name,
                            "value": [{"n": v, "v": v} for v in vals]})
        return fts

    def homeContent(self, filter):
        if not self.a:
            return {"class": [], "filters": {}, "list": [],
                    "error": "AppV6: ext 为空，请填 mtys.php 一类入口"}
        cats, fts = [], {}
        try:
            j = self._get(f"{self.a}/v6/nav")
            for it in j.get("data") or []:
                if not isinstance(it, dict):
                    continue
                tid = str(it.get("type_id") or "")
                name = str(it.get("type_name") or "")
                if not tid:
                    continue
                cats.append({"type_id": tid, "type_name": name or tid})
                fl = self._filters(it.get("type_extend"))
                if fl:
                    fts[tid] = fl
        except Exception:
            pass
        return {"class": cats, "filters": fts, "list": self.homeVideoContent()["list"]}

    def homeVideoContent(self):
        lst = []
        try:
            if self.a:
                j = self._get(f"{self.a}/v6/index_video")
                for sec in j.get("data") or []:
                    if isinstance(sec, dict):
                        lst.extend(self._d(sec.get("vlist")))
        except Exception:
            pass
        return {"list": lst}

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
        if not self.a:
            result["error"] = "AppV6: ext 为空"
            return result
        try:
            pg = str(pg) if str(pg).strip().isdigit() else "1"
            ex = extend or {}
            url = f"{self.a}/v6/video?pg={pg}&tid={str(tid)}"
            for k in ("class", "area", "lang", "year"):
                v = str(ex.get(k) or "").strip()
                if v:
                    url += f"&{k}={quote(v)}"
            url += "&order=time&token=&"
            j = self._get(url)
            lst = self._d(j.get("data"))
            result["list"] = lst
            n = int(pg) if pg.isdigit() else 1
            result["page"] = n
            result["pagecount"] = n
            result["total"] = len(lst)
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0])
            j = self._get(f"{self.a}/v6/video_detail?id={vid}")
            data = j.get("data") or {}
            vi = data.get("vod_info") or data
            if not isinstance(vi, dict):
                return {"list": [], "error": "AppV6 detail: 无 data"}
            vod = {"vod_id": vid,
                   "vod_name": str(vi.get("vod_name") or ""),
                   "vod_pic": str(vi.get("vod_pic") or ""),
                   "vod_remarks": str(vi.get("vod_remarks") or ""),
                   "vod_content": str(vi.get("vod_content") or ""),
                   "vod_actor": str(vi.get("vod_actor") or ""),
                   "vod_director": str(vi.get("vod_director") or ""),
                   "vod_class": str(vi.get("vod_class") or "")}
            froms, urls = [], []
            for i, pl in enumerate(vi.get("vod_url_with_player") or []):
                if not isinstance(pl, dict):
                    continue
                name = str(pl.get("name") or "") or f"线路{i + 1}"
                u = str(pl.get("url") or "")
                if not u:
                    continue
                pa = str(pl.get("parse_api") or "")
                if pa:
                    u = u.replace("$", "$" + pa)
                froms.append(name)
                urls.append(u)
            if urls:
                vod["vod_play_from"] = "$$$".join(froms)
                vod["vod_play_url"] = "$$$".join(urls)
        except Exception:
            pass
        return {"list": [vod] if vod else []}

    def playerContent(self, flag, playId, vipFlags):
        try:
            pid = (playId or "").strip()
            if not pid:
                return {"parse": 0, "url": "", "header": {}, "error": "AppV6 play: 空地址"}
            if "?url=" in pid or "?key=" in pid:
                try:
                    j = self._get(pid)
                    return {"parse": 0, "url": str(j.get("url") or ""), "header": {}}
                except Exception:
                    return {"parse": 0, "url": "", "header": {},
                            "error": "播放链接解析失败,请更换其他源播放"}
            if re.search(r".*(m3u8|mp4|mkv).*", pid, re.I):
                return {"parse": 0, "url": pid, "header": {}}
            return {"parse": 0, "url": "", "header": {},
                    "error": "播放链接解析失败,请更换其他源播放"}
        except Exception:
            return {"parse": 0, "url": "", "header": {},
                    "error": "播放链接解析失败,请更换其他源播放"}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        if not self.a:
            result["error"] = "AppV6: ext 为空"
            return result
        try:
            key = str(key or "").strip()
            if not key:
                return result
            j = self._get(f"{self.a}/v6/search?pg=1&tid=0&text={quote(key)}")
            result["list"] = self._d(j.get("data"))
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
