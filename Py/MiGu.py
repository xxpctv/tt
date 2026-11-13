# -*- coding: utf-8 -*-
"""TVBox Python Spider - MiGu (self-contained)"""
import sys, json
sys.path.append("..")
from base.spider import Spider

# ============ BEGIN ORIGINAL SOURCE ============
# -*- coding: utf-8 -*-
# TVBox Python Spider - MiGu (咪咕视频直播)
# Source: 1109.jar -> csp_MiGu

import json
import time
import random
import hashlib
import urllib.request
import urllib.parse

CATEGORIES = [
    ["央视频道", "1ff892f2b5ab4a79be6e25b69d2f5d05"],
    ["卫视频道", "0847b3f6c08a4ca28f85ba5701268424"],
    ["地方频道", "855e9adc91b04ea18ef3f2dbd43f495b"],
    ["其它频道", "7538163cdac044398cb292ecf75db4e0,10b0d04cb23d4ac5945c4bc77c7ac44e,c584f67ad63f4bc983c31de3a9be977c,af72267483d94275995a4498b2799ecd,e76e56e88fff4c11b0168f55e826445d,192a12edfef04b5eb616b878f031f32f,fc2f5b8fd7db43ff88c4243e731ecede,e1165138bdaa44b9a3138d74af6c6673"],
]

_channel_cache = {}
_cache_time = {}
CACHE_TTL = 300000  # 5 minutes


def _md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[MiGu] get error: {e}")
        return {}


def _get_channels(group_id):
    now = time.time() * 1000
    if group_id in _cache_time and now - _cache_time[group_id] < CACHE_TTL and group_id in _channel_cache:
        return _channel_cache[group_id]

    url = f"https://program-sc.miguvideo.com/live/v2/tv-data/{group_id}"
    data = _get(url)
    channels = []
    for item in data.get("body", {}).get("dataList", []):
        name = item.get("name", "")
        pid = item.get("pID", "")
        pic = item.get("pics", {}).get("highResolutionH", "")
        if name and pid:
            channels.append({"pID": pid, "name": name, "pic": pic})
    _channel_cache[group_id] = channels
    _cache_time[group_id] = now
    return channels


def _all_channels():
    all_ch = []
    for _, ids in CATEGORIES:
        for gid in ids.split(","):
            all_ch.extend(_get_channels(gid.strip()))
    return all_ch


def _calc_ddcalcu(pu_data, params):
    """计算 ddCalcu 参数"""
    if not pu_data:
        return ""
    userid = params.get("userid", "eeeeeeeee")
    timestamp = params.get("timestamp", "tttttttttttttt")
    program_id = params.get("ProgramID", "ccccccccc")
    channel_id = params.get("Channel_ID", "nnnnnnnnnnnnnnnn")
    char_map = [' ', 'e', 't', 'c', 'n']
    idx_map = [-1, 0, 1, 2, 3]
    arr = [8, 3, 7, 6, 6]
    length = len(pu_data)
    half = length // 2
    sb = []
    for i in range(half):
        sb.append(pu_data[length - 1 - i])
        sb.append(pu_data[i])
        if 1 <= i <= 4:
            val_str = [None, userid, timestamp, program_id, channel_id][i]
            pos = arr[idx_map[i]] - 1
            c = char_map[i]
            if pos < len(val_str):
                c = val_str[pos]
            sb.append(chr(((arr[4] ^ ord(c)) % 26) + 97))
    if length % 2 == 1:
        sb.append(pu_data[half])
    return "ddCalcu=" + "".join(sb)


def _process_play_url(url):
    """处理播放URL，添加 ddCalcu/sv/ct 参数"""
    if not url:
        return ""
    qidx = url.find("?")
    params = {}
    if qidx >= 0:
        query = url[qidx + 1:]
        for pair in query.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                k = k.strip()
                if k not in params:
                    params[k] = urllib.parse.unquote(v)
    pu_data = params.get("puData", "")
    if not pu_data:
        return url

    extra = []
    if not params.get("ddCalcu"):
        extra.append(_calc_ddcalcu(pu_data, params))
    if not params.get("sv"):
        extra.append("sv=10004")
    if not params.get("ct"):
        extra.append("ct=android")
    if not extra:
        return url

    sep = "&" if "?" in url and url[-1] not in "?&" else "?" if "?" not in url else ""
    return url + sep + "&".join(extra)


def _get_play_url(cont_id):
    ts = str(int(time.time() * 1000))
    salt = f"{random.randint(0, 999999):06d}25"
    sign = _md5(_md5(ts + cont_id + "26000346") + "2cac4f2c6c3346a5b34e085725ef7e33migu" + salt[:4])
    client_id = "".join(random.choice("0123456789abcdef") for _ in range(32))

    url = (f"https://play.miguvideo.com/playurl/v1/play/playurl?sign={sign}"
           f"&rateType=3&contId={cont_id}&timestamp={ts}&salt={salt}"
           f"&flvEnable=true&super4k=true&h265N=true&4kvivid=true&2Kvivid=true&vivid=2")

    headers = {
        "AppVersion": "2600034600",
        "TerminalId": "android",
        "X-UP-CLIENT-CHANNEL-ID": "2600034600-99000-201600010010028",
        "ClientId": client_id,
        "Accept": "*/*",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 13;)",
    }
    if cont_id not in ("641886683", "641886773"):
        headers["appCode"] = "miguvideo_default_android"

    data = _get(url, headers) or {}
    body = data.get("body") or {}
    play_url = (body.get("urlInfo") or {}).get("url", "")
    if play_url:
        return _process_play_url(play_url)
    return ""


def init(ext):
    pass


def homeContent(filter):
    classes = [{"type_id": ids, "type_name": name} for name, ids in CATEGORIES]
    return json.dumps({"class": classes, "list": []}, ensure_ascii=False)


def categoryContent(tid, pg, filter, extend):
    vlist = []
    for gid in tid.split(","):
        for ch in _get_channels(gid.strip()):
            vlist.append({
                "vod_id": ch["pID"],
                "vod_name": ch["name"],
                "vod_pic": ch["pic"],
                "vod_remarks": "直播",
            })
    return json.dumps({
        "page": 1,
        "pagecount": 1,
        "limit": len(vlist),
        "total": len(vlist),
        "list": vlist,
    }, ensure_ascii=False)


def detailContent(ids):
    if not ids:
        return ""
    pid = ids[0]
    name = pid
    pic = ""
    for ch in _all_channels():
        if ch["pID"] == pid:
            name = ch["name"]
            pic = ch["pic"]
            break
    result = {
        "vod_id": pid,
        "vod_name": name,
        "vod_pic": pic,
        "vod_play_from": "咪咕",
        "vod_play_url": f"播放${pid}",
        "vod_content": f"{name} 高清直播",
    }
    return json.dumps({"list": [result]}, ensure_ascii=False)


def playerContent(flag, id, vipFlags):
    play_url = _get_play_url(id)
    return json.dumps({
        "parse": 0,
        "playUrl": "",
        "url": play_url,
    }, ensure_ascii=False)


def searchContent(key, quick):
    vlist = []
    for ch in _all_channels():
        if key in ch["name"]:
            vlist.append({
                "vod_id": ch["pID"],
                "vod_name": ch["name"],
                "vod_pic": ch["pic"],
                "vod_remarks": "直播",
            })
    return json.dumps({"list": vlist}, ensure_ascii=False)

# ============ END ORIGINAL SOURCE ============

class Spider(Spider):
    def init(self, extend=""):
        globals()["init"](extend)

    def homeContent(self, filter):
        ret = globals()["homeContent"](filter)
        if isinstance(ret, str):
            try: return json.loads(ret)
            except: return {"class": [], "list": [], "filters": {}}
        return ret

    def categoryContent(self, tid, pg, filter, extend):
        ret = globals()["categoryContent"](tid, pg, filter, extend)
        if isinstance(ret, str):
            try: return json.loads(ret)
            except: return {"list": [], "page": int(pg) if pg else 1, "pagecount": 1, "limit": 20, "total": 0}
        return ret

    def detailContent(self, ids):
        ret = globals()["detailContent"](ids)
        if isinstance(ret, str):
            try: return json.loads(ret)
            except: return {"list": []}
        return ret

    def searchContent(self, key, quick, pg="1"):
        ret = globals()["searchContent"](key, quick)
        if isinstance(ret, str):
            try: return json.loads(ret)
            except: return {"list": []}
        return ret

    def playerContent(self, flag, id, vipFlags):
        ret = globals()["playerContent"](flag, id, vipFlags)
        if isinstance(ret, str):
            try: return json.loads(ret)
            except: return {"parse": 0, "url": ""}
        return ret

    def liveContent(self, url):
        fn = globals().get("liveContent")
        if not fn:
            return ""
        ret = fn(url)
        if isinstance(ret, str):
            return ret
        return json.dumps(ret, ensure_ascii=False)
