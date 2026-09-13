# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   凤凰广播 (FenghuangFM)

from base.spider import Spider
import requests
import re
from urllib.parse import quote

BASE = "https://s.fm.renbenai.com"
UA = "okhttp/3.12.11"


class Spider(Spider):
    def getName(self):
        return "凤凰广播"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _get(self, path):
        try:
            r = requests.get(BASE + path, headers={"User-Agent": UA}, timeout=12)
            return r.text
        except Exception:
            return ""

    def _get_json(self, path):
        try:
            import json
            return json.loads(self._get(path))
        except Exception:
            return {}

    def homeContent(self, filter):
        result = {"class": [], "filters": {}}
        try:
            j = self._get_json("/fm/read/fmd/static/categoryTvGet_100.html")
            lst = j["data"]["list"]
            for it in lst[0].get("channelContent") or []:
                result["class"].append({"type_id": str(it.get("id")),
                                        "type_name": it.get("nodeName") or ""})
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        return self.categoryContent("", 1, False, {})

    @staticmethod
    def _clean(name):
        return "" if re.search(r"(名称|排除)", name or "") else name

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 9999}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            tid = str(tid or "")
            j = self._get_json(f"/fm/read/fmd/android/600/getProgramList.html&cid={tid}&pagenum={pg}")
            for it in (j.get("data") or {}).get("hotList") or []:
                name = self._clean(it.get("programName"))
                if not name:
                    continue
                pic = it.get("img640_640") or it.get("img370_370") or ""
                result["list"].append({"vod_id": str(it.get("id")), "vod_name": name,
                                       "vod_pic": pic, "vod_remarks": it.get("resourceTitle") or ""})
            result["page"] = pg
            result["pagecount"] = pg + 1 if result["list"] else pg
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            pid = str(ids[0])
            j = self._get_json(f"/fm/read/fmd/android/getProgramAudioList_620.html&pid={pid}")
            lst = (j.get("data") or {}).get("list") or []
            if not lst:
                return {"list": []}
            first = lst[0]
            play_url = []
            for item in lst:
                for a in item.get("audiolist") or []:
                    fp = a.get("filePath")
                    if not fp:
                        continue
                    title = a.get("title") or item.get("title") or ""
                    play_url.append(f"{title}${fp}")
            vod = {
                "vod_id": pid,
                "vod_name": first.get("title") or "",
                "vod_pic": first.get("img370_370") or "",
                "vod_content": first.get("programDetails") or "",
                "vod_remarks": first.get("tags") or "",
                "vod_play_from": "凤凰FM",
                "vod_play_url": "#".join(play_url),
            }
        except Exception:
            pass
        return {"list": [vod]}

    def playerContent(self, flag, playId, vipFlags):
        return {"parse": 0, "url": (playId or "").strip(),
                "header": {"User-Agent": UA}}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            pg = int(pg) if str(pg).isdigit() else 1
            j = self._get_json(f"/fm/read/fmd/public/search_720.html&keyWord={quote(key)}&searchType=1&pageNum={pg}")
            pat = re.compile(re.escape(key), re.IGNORECASE)
            for it in (j.get("data") or {}).get("program") or []:
                name = it.get("programName") or ""
                if not self._clean(name) or not pat.search(name):
                    continue
                result["list"].append({"vod_id": str(it.get("id")), "vod_name": name,
                                       "vod_pic": it.get("img640_640") or "",
                                       "vod_remarks": it.get("programName") or ""})
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
