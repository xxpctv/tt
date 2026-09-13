# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   兔小贝 (TuXiaoBei)
# 站点: https://www.tuxiaobei.com
# 说明: 完整复刻 分类(大类api/专题sub)/首页/详情/搜索; 播放为 resource-cdn mp4 直链.

from base.spider import Spider
import requests
import re
import json
from urllib.parse import quote

UA = ("Mozilla/5.0 (Linux; Android 12; Mobile) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36")
HOME = "https://www.tuxiaobei.com/"
CATS_A = [["2", "大类·儿歌"], ["3", "大类·故事"], ["4", "大类·国学"],
          ["25", "大类·启蒙"]]
CATS_B = [["17", "兔小贝原创儿歌"], ["16", "睡前儿歌"], ["1", "Everybody动起来"],
          ["3", "宝宝吃饭香"], ["4", "乖宝宝不哭闹"], ["5", "好宝宝爱上学"],
          ["6", "欢快儿歌"], ["9", "经典儿歌"], ["10", "快乐的节日"],
          ["11", "快乐的童年"], ["12", "流行儿歌"], ["13", "美丽四季"],
          ["14", "男孩最爱"], ["15", "女孩最爱"], ["19", "我爱爸爸妈妈"],
          ["20", "我的动物朋友"], ["21", "我的祖国和我"], ["22", "舞蹈音乐"],
          ["23", "英文儿歌"], ["24", "粤语儿歌"], ["25", "早教好习惯"],
          ["56", "放暑假啦"], ["57", "我能照顾好自己"], ["58", "画一个梦"],
          ["59", "哆啦A梦的神奇口袋"], ["60", "你是我的小天使"],
          ["61", "最动听的笑声"], ["62", "许个愿吧"], ["63", "阳光下的我们"],
          ["89", "智慧成语故事"], ["90", "名人成语故事"], ["88", "励志成语故事"],
          ["87", "神话成语故事"], ["39", "古诗启蒙"], ["43", "三字经"],
          ["46", "弟子规"], ["48", "千字文"], ["54", "十万个为什么"],
          ["55", "神奇的大自然"], ["50", "英语宝典"], ["51", "数学课堂"],
          ["53", "动物奇缘"], ["84", "安全教育"]]
RE_ITEM = re.compile(r'href="/play/(\d+)"[\s\S]*?mip-img[^>]+src="([^"]+)"'
                     r'[\s\S]*?class="title">([^<]+)</p>[\s\S]*?class="time">([^<]+)</span>')


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


class Spider(Spider):
    def getName(self):
        return "兔小贝"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _fetch(self, url):
        try:
            return requests.get(url if url.startswith("http") else HOME + url,
                                headers={"User-Agent": UA, "Referer": HOME},
                                timeout=15).text
        except Exception:
            return ""

    def _detail_info(self, vid):
        """fetch play/{vid} -> [title, pic, mp4]"""
        html = self._fetch(f"play/{vid}")
        title = ""
        m = re.search(r"<h1[^>]*>([^<]+)</h1>", html or "")
        if m:
            title = m.group(1).strip()
        if not title:
            m = re.search(r"<title>([^<]+)</title>", html or "")
            if m:
                t = m.group(1).strip()
                for sep in ("-", "_"):
                    if sep in t:
                        t = t.split(sep)[0].strip()
                title = t
        mp4 = ""
        m = re.search(r'video-src="(https://resource-cdn\.tuxiaobei\.com/[^"]+\.mp4)"', html or "")
        if m:
            mp4 = m.group(1).strip()
        if not mp4:
            m = re.search(r"https://resource-cdn\.tuxiaobei\.com/video/[^\"'\s]+\.mp4", html or "")
            if m:
                mp4 = m.group(0).strip()
        pic = ""
        m = re.search(r'poster="(https://resource-cdn\.tuxiaobei\.com/[^"]+)"', html or "")
        if m:
            pic = m.group(1).strip()
        if not pic:
            m = re.search(r"https://resource-cdn\.tuxiaobei\.com/video/[^\"'\s]+\.(?:png|jpg|webp)", html or "")
            if m:
                pic = m.group(0).strip()
        return [title, pic, mp4]

    def _parse_subject(self, html, tid):
        out, seen = [], set()
        for m in RE_ITEM.finditer(html or ""):
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            pic = m.group(2)
            if pic.startswith("//"):
                pic = "https:" + pic
            out.append({"vod_id": f"{vid}|||{tid}",
                        "vod_name": m.group(3).strip(),
                        "vod_pic": pic,
                        "vod_remarks": m.group(4).strip()})
        if not out:
            for m in re.finditer(r'href="/play/(\d+)"', html or ""):
                vid = m.group(1)
                if vid in seen:
                    continue
                seen.add(vid)
                out.append({"vod_id": f"{vid}|||{tid}",
                            "vod_name": f"视频{vid}", "vod_pic": "",
                            "vod_remarks": ""})
        return out

    def homeContent(self, filter):
        cats = [{"type_id": f"api_{cid}", "type_name": name} for cid, name in CATS_A]
        cats += [{"type_id": f"sub_{cid}", "type_name": name} for cid, name in CATS_B]
        return {"class": cats, "filters": {}, "list": []}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}
        try:
            pg = max(1, int(pg) if str(pg).strip().isdigit() else 1)
            tid = str(tid)
            if tid.startswith("api_"):
                html = self._fetch(f"list/mip-data?typeId={tid[4:]}&page={pg}&callback=jsonp")
                html = (html or "").strip()
                m = re.match(r"^jsonp\((.*)\);?$", html, re.S)
                if m:
                    html = m.group(1)
                try:
                    j = json.loads(html or "{}")
                    items = (j.get("data") or {}).get("items") or []
                    lst = []
                    for it in items:
                        vid = str(it.get("video_id") or "0")
                        if vid == "0":
                            continue
                        name = str(it.get("name") or "")
                        pic = str(it.get("image") or "")
                        if pic.startswith("//"):
                            pic = "https:" + pic
                        remark = str(it.get("duration_string") or "")
                        if not remark:
                            remark = str(it.get("play_num") or "")
                        lst.append({"vod_id": f"{vid}|||{tid}",
                                    "vod_name": name, "vod_pic": pic,
                                    "vod_remarks": remark})
                    result["list"] = lst
                    result["page"] = pg
                    result["pagecount"] = pg if not lst else pg + 1
                    result["total"] = 9999
                except Exception:
                    pass
            elif tid.startswith("sub_") and pg <= 1:
                html = self._fetch(f"subject/{tid[4:]}")
                result["list"] = self._parse_subject(html, tid)
                result["page"] = 1
                result["pagecount"] = 1
                result["total"] = len(result["list"])
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0])
            raw = vid.split("|||")[0]
            info = self._detail_info(raw)
            name = info[0] or raw
            vod = {"vod_id": vid, "vod_name": name, "vod_pic": info[1],
                   "vod_play_from": "兔小贝",
                   "vod_play_url": f"{name if name != raw else '播放'}${info[2]}"}
        except Exception:
            pass
        return {"list": [vod] if vod else []}

    def playerContent(self, flag, playId, vipFlags):
        try:
            pid = (playId or "").strip()
            if pid.startswith("http"):
                url = pid
            else:
                raw = pid.split("|||")[0]
                info = self._detail_info(raw)
                url = info[2] or ""
            return {"parse": 0, "url": url,
                    "header": {"User-Agent": UA, "Referer": HOME}}
        except Exception:
            return {"parse": 0, "url": "", "header": {}}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            html = self._fetch(f"search/index?key={quote(key)}")
            result["list"] = self._parse_subject(html, "api_2")
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
