# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   魔都动漫 (MoDu)

from base.spider import Spider
import requests
from urllib.parse import quote

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
API = "https://www.mdzyapi.com/api.php/provide/vod"
CLASSES = [["1", "国产动漫"], ["2", "日韩动漫"], ["3", "欧美动漫"], ["4", "港台动漫"], ["5", "动漫电影"]]


class Spider(Spider):
    def getName(self):
        return "魔都动漫"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _get_json(self, url):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=12)
            return r.json()
        except Exception:
            return {}

    @staticmethod
    def _parse_list(obj):
        out = []
        try:
            for it in obj.get("list") or []:
                vid = str(it.get("vod_id") or "").strip()
                name = str(it.get("vod_name") or "").strip()
                if not vid or not name:
                    continue
                out.append({"vod_id": vid, "vod_name": name,
                            "vod_pic": it.get("vod_pic") or "",
                            "vod_remarks": it.get("vod_remarks") or ""})
        except Exception:
            pass
        return out

    def homeContent(self, filter):
        return {"class": [{"type_id": c[0], "type_name": c[1]} for c in CLASSES], "filters": {}}

    def homeVideoContent(self):
        return self.categoryContent("1", 1, False, {})

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            url = f"{API}?ac=detail&t={quote(str(tid))}&pg={pg}"
            j = self._get_json(url)
            result["list"] = self._parse_list(j)
            result["pagecount"] = max(1, int(j.get("pagecount") or 1))
            result["limit"] = max(1, int(j.get("limit") or 20))
            result["total"] = max(0, int(j.get("total") or len(result["list"])))
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0]).strip()
            if not vid:
                return {"list": []}
            j = self._get_json(f"{API}?ac=detail&ids={quote(vid)}")
            lst = j.get("list") or []
            if not lst:
                return {"list": []}
            it = lst[0]
            vod = {
                "vod_id": vid,
                "vod_name": it.get("vod_name") or "",
                "vod_pic": it.get("vod_pic") or "",
                "vod_year": it.get("vod_year") or "",
                "vod_area": it.get("vod_area") or "",
                "vod_actor": it.get("vod_actor") or "",
                "vod_director": it.get("vod_director") or "",
                "vod_content": it.get("vod_content") or "",
                "vod_remarks": it.get("vod_remarks") or "",
                "vod_play_from": it.get("vod_play_from") or "播放",
                "vod_play_url": it.get("vod_play_url") or "",
            }
            if not vod["vod_play_from"] and vod["vod_play_url"]:
                vod["vod_play_from"] = "播放"
        except Exception:
            pass
        return {"list": [vod]}

    def playerContent(self, flag, playId, vipFlags):
        return {"parse": 0, "url": (playId or "").strip(),
                "header": {"User-Agent": UA}}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": [], "page": int(pg) if str(pg).isdigit() else 1,
                  "pagecount": 1, "limit": 20, "total": 0}
        try:
            key = str(key).strip()
            if not key:
                return result
            url = f"{API}/?ac=detail&pg={quote(str(pg))}&wd={quote(key)}"
            j = self._get_json(url)
            result["list"] = self._parse_list(j)
            result["pagecount"] = max(1, int(j.get("pagecount") or 10))
            result["limit"] = max(1, int(j.get("limit") or 20))
            result["total"] = max(0, int(j.get("total") or len(result["list"])))
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
