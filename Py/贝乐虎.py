# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   贝乐虎 (BeiLeHu)

from base.spider import Spider
import requests
import json

API = "https://vd.ubestkid.com/api/v1/bv/video"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1"
CATES = [["56", "儿歌"], ["63", "故事"], ["62", "少儿"], ["61", "古诗"], ["64", "认知"], ["65", "习惯"]]


def _fmt_time(end_interval):
    try:
        sec = int(end_interval) // 10
        m, s = divmod(sec, 60)
        return f"{m}:{s:02d}"
    except Exception:
        return ""


class Spider(Spider):
    def getName(self):
        return "贝乐虎"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    @staticmethod
    def _req(p, subcate, headers):
        body = {"age": 1, "appver": "6.1.9", "egvip_status": 0, "svip_status": 0,
                "vps": 60, "subcateId": subcate, "p": p}
        try:
            r = requests.post(API, data=json.dumps(body), headers=headers, timeout=12)
            return r.json()
        except Exception:
            return {}

    @staticmethod
    def _items(j):
        try:
            res = j.get("result") or {}
            return res.get("items") or []
        except Exception:
            return []

    def _to_vods(self, items, limit=0):
        out = []
        items = items if limit <= 0 else items[:limit]
        for it in items:
            url = str(it.get("url") or "")
            if not url:
                continue
            title = str(it.get("title") or "贝乐虎")
            image = str(it.get("image") or "")
            vid = f"{url}@@{title}@@{image}"
            rem = _fmt_time(it.get("endInterval")) or str(it.get("brand") or "")
            out.append({"vod_id": vid, "vod_name": title, "vod_pic": image, "vod_remarks": rem})
        return out

    def homeContent(self, filter):
        result = {"class": [{"type_id": c[0], "type_name": c[1]} for c in CATES], "filters": {}}
        try:
            hdrs = {"Content-Type": "application/json", "appver": "6.1.9"}
            result["list"] = self._to_vods(self._items(self._req(1, 1, hdrs)), 20)
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        return self.categoryContent("56", 1, False, {})

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 30, "total": 999999}
        try:
            pg = int(str(pg).strip() or 1)
            sub = int(str(tid).strip() or 56)
            hdrs = {"Content-Type": "application/json",
                    "User-Agent": UA}
            result["list"] = self._to_vods(self._items(self._req(pg, sub, hdrs)))
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            parts = str(ids[0]).split("@@")
            vod = {
                "vod_id": str(ids[0]),
                "vod_name": parts[1] if len(parts) > 1 else "贝乐虎",
                "vod_pic": parts[2] if len(parts) > 2 else "",
                "type_name": "少儿",
                "vod_play_from": "贝乐虎",
                "vod_play_url": f"播放${parts[0]}",
            }
        except Exception:
            pass
        return {"list": [vod]}

    def playerContent(self, flag, playId, vipFlags):
        url = str(playId or "")
        if "播放" in url:
            url = url.split("播放", 1)[0]
        if "$" in url:
            url = url[url.index("$") + 1:]
        return {"parse": 0, "url": url, "header": {"User-Agent": UA}}

    def searchContent(self, key, quick):
        return {"list": []}

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
