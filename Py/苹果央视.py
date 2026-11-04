# -*- coding: utf-8 -*-
"""APP99 直播源（独立 py）

从 app99.py（半日闲 RPY）提取"直播"隐藏分类为独立直播源。
- 保留原源完整鉴权：请求体 AES-CBC 加密（uuid 作 key，前 16 字节作 IV）+ zlib
  + SHA256 签名 sign=sha256(body:timestamp:nonce:token:appkey)，头带
  uuid/timestamp/nonce/appkey/version；systemInit 拉配置、/app/log 登录。
- 展示契约（咕噜式）：homeContent 返回静态"直播"分类；categoryContent(tid)
  并发展开全部分组（卫视频道/央视频道/湖南卫视/CCTV5/地方台直播/央视直播…）
  为具体台卡片（vod_remarks=分组名），OK影视 直播导航自动按分组显示；
  播放 URL 由服务端直接下发（110.42.52.180:6688/live/live.php?token=…），直出可播。
- _is_vod_source=True：AjeoZB-DB.py 聚合器按点播透传（分类→台→播放），互不干扰。
"""
import base64
import hashlib
import json
import re
import sys
import time
import uuid
import zlib

from urllib.parse import quote

try:
    import requests
except Exception:
    requests = None

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
except Exception:
    AES = None
    pad = None
    unpad = None

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def getProxyUrl(self):
            return "http://127.0.0.1:9978/proxy?do=py&"

        def init(self, extend):
            pass

        def getName(self):
            return "APP99直播"

        def destroy(self):
            return None

# ---------------- 默认配置（半日闲 RPY，ext 可覆盖） ----------------

DEFAULT_CONFIG = {
    "host": "http://103.217.190.91:19987/app/bn",
    "appkey": "24d625a8a29b4700a1a294c6f3b29e2c",
    "versionName": "3.5.8",
    "name": "半日闲",
    "package": "com.yf.lelian",
    "buildNumber": "2001",
    "buildSignature": "A40DA80A59D170CAA950CF15C18C454D47A39B26989D8B640ECD745BA71BF5DC",
    "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

# 直播分类（服务端 systemInit 下发：23=直播）
LIVE_CATEGORIES = [
    ("23", "直播"),
]
LIVE_IDS = ("23",)

# 频道栏只保留这两个分组（其余 4 组重复或内容已含在内）
KEEP_GROUPS = ("央视频道", "卫视频道")

# 点播分组卡（咕噜式）：homeContent list=4 个分组大卡 → 点卡 → detailContent 返回该组台列表。
# id 规则：服务端组 id（906124=央视频道 / 906123=卫视频道），地方/综合是 906123 按台名拆分的
# 自定义子组（无独立服务端 id，detailContent 内按 _sub_group/_DEAD_NAMES 过滤）。
_GROUP_CARD_IDS = {
    "23_906124": ("央视频道", "906124", "央视"),
    "23_906123": ("卫视频道", "906123", "卫视"),
    "23_906123_地方": ("地方频道", "906123", "地方"),
    "23_906123_综合": ("综合频道", "906123", "综合"),
}
_GROUP_CARD_LIST = [("央视频道", "23_906124"), ("卫视频道", "23_906123"),
                    ("地方频道", "23_906123_地方"), ("综合频道", "23_906123_综合")]

# 综合频道内服务端已失效的台（live resolve error / 404 / 无法找到），播放即报错，直接剔除
_DEAD_NAMES = frozenset({
    "1905电影网流金岁月电影轮播", "1905电影网环球经典电影轮播", "24小时轮播",
    "CHC动作电影", "CHC家庭影院", "中华特产", "中国天气", "乐家购物", "传奇剧场",
    "体坛名栏汇", "周润发系列", "和美乡途轮播台", "国产佳作", "国学频道",
    "大连乐天购物", "宅家剧场", "岁月男神", "心动投送", "文物宝库", "新片放映厅",
    "欢腾购物", "武术世界", "游戏风云", "热血剧场", "生活剧场", "移动戏曲",
    "经典香港电影", "赛事最经典", "放映厅", "大咖面对面", "怀旧经典", "红色经典",
    "往昔影院",
})

# 卫视频道组二次拆分：卫视结尾→卫视频道；黑名单→综合频道；其余→地方频道
_SUB_BLACK = (r"熊猫频道|1905|CHC|轮播|剧场|影院|放映厅|中国天气|环球旅游|中华特产|CETV|"
              r"游戏风云|移动电视|文物宝库|武术世界|国学频道|购物|戏曲|经典香港|香港电影|"
              r"国产佳作|岁月男神|心动投送|宅家剧场|怀旧经典|红色经典|大咖面对面|周润发系列|"
              r"赛事最经典|体坛名栏汇|四海钓鱼|和美乡途|最强综艺趴|南方影视|24小时轮播|"
              r"传奇剧场|热血剧场|往昔影院|生活剧场|新片放映厅|移动戏曲")


def _sub_group(name):
    n = str(name or "")
    if re.search(r"卫视$", n):
        return "卫视频道"
    if re.search(_SUB_BLACK, n):
        return "综合频道"
    return "地方频道"


# 频道栏分组显式顺序：央视最前
_GROUP_ORDER = {"央视频道": 0, "卫视频道": 1, "地方频道": 2, "综合频道": 3}

# GB2312 汉字拼音首字母区间表（用于无外部依赖的拼音排序）
_PINYIN_RANGES = [
    ("A", 0xB0A1, 0xB0C4), ("B", 0xB0C5, 0xB2C0), ("C", 0xB2C1, 0xB4ED),
    ("D", 0xB4EE, 0xB6E9), ("E", 0xB6EA, 0xB7A1), ("F", 0xB7A2, 0xB8C0),
    ("G", 0xB8C1, 0xB9FD), ("H", 0xB9FE, 0xBBF6), ("J", 0xBBF7, 0xBFA5),
    ("K", 0xBFA6, 0xC0AB), ("L", 0xC0AC, 0xC2E7), ("M", 0xC2E8, 0xC4C2),
    ("N", 0xC4C3, 0xC5B5), ("O", 0xC5B6, 0xC5BD), ("P", 0xC5BE, 0xC6D9),
    ("Q", 0xC6DA, 0xC8BA), ("R", 0xC8BB, 0xC8F5), ("S", 0xC8F6, 0xCBF9),
    ("T", 0xCBFA, 0xCDD9), ("W", 0xCDDA, 0xCEF3), ("X", 0xCEF4, 0xD188),
    ("Y", 0xD189, 0xD4D0), ("Z", 0xD4D1, 0xD7F9),
]


def _py_initial(ch):
    try:
        b = ch.encode("gb2312")
    except Exception:
        return ""
    i = int.from_bytes(b, "big")
    for letter, lo, hi in _PINYIN_RANGES:
        if lo <= i <= hi:
            return letter
    return ""


def _pinyin_key(nm):
    n = str(nm or "")
    out = []
    for ch in n:
        if "\u4e00" <= ch <= "\u9fa5":
            out.append(_py_initial(ch) or ch)
        else:
            out.append(ch)
    return "".join(out)

_EXP_CACHE = {}


class Spider(BaseSpider):
    _is_vod_source = True  # 聚合器按点播透传
    _group_cards_mode = True  # 聚合器父标签：用 homeContent list（分组卡）而非平铺
    _categories = LIVE_CATEGORIES

    def getName(self):
        return "APP99直播"

    def init(self, extend=""):
        cfg = dict(DEFAULT_CONFIG)
        if isinstance(extend, dict):
            cfg.update(extend)
        elif isinstance(extend, str) and extend.strip():
            try:
                cfg.update(json.loads(extend))
            except Exception:
                pass
        self.host = str(cfg.get("host", "")).rstrip("/")
        self.appkey = str(cfg.get("appkey", ""))
        self.name = str(cfg.get("name", ""))
        self.build_signature = str(cfg.get("buildSignature", ""))
        self.build_number = str(cfg.get("buildNumber", ""))
        self.version_name = str(cfg.get("versionName", ""))
        self.package = str(cfg.get("package", ""))
        self.ua = str(cfg.get("ua", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"))
        self.api_version = str(cfg.get("version", "0b4328287a5d953e"))
        self.login_path = str(cfg.get("LoginPath", "/app/log"))
        self.uuid = str(cfg.get("uuid", "")) or str(uuid.uuid4())
        self.token = str(cfg.get("token", ""))
        self.player_config = {}
        self.parser_apis = []
        self.categories = []
        try:
            self._init_app()
        except Exception:
            pass

    def getDependence(self):
        return []

    def action(self, action):
        return ""

    def destroy(self):
        pass

    def isVideoFormat(self, url):
        return bool(re.search(r"(?i)\.(?:mp4|m3u8|flv|mkv|avi|ts|mov|mpd|m4a|wmv)(?:\?.*)?$", str(url)))

    def manualVideoCheck(self):
        return True

    # ---------------- 鉴权工具（自 app99.py 精确复刻） ----------------

    def _aes_decrypt(self, data, key):
        try:
            if AES is None:
                return ""
            decoded = base64.b64decode(data)
            iv = decoded[:16]
            ciphertext = decoded[16:]
            k = key.replace("-", "")
            kb = k.encode("utf-8")
            if len(kb) not in (16, 24, 32):
                kb = (kb + (b"0" * 32))[:32]
            cipher = AES.new(kb, AES.MODE_CBC, iv)
            decrypted = cipher.decrypt(ciphertext)
            try:
                return zlib.decompress(decrypted).decode("utf-8")
            except Exception:
                try:
                    return unpad(decrypted, AES.block_size).decode("utf-8")
                except Exception:
                    return decrypted.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def _aes_encrypt(self, data, key):
        if AES is None:
            return ""
        k = key.replace("-", "")
        kb = k.encode("utf-8")
        if len(kb) not in (16, 24, 32):
            kb = (kb + (b"0" * 32))[:32]
        cipher = AES.new(kb, AES.MODE_CBC)
        encrypted = cipher.encrypt(pad(data.encode(), AES.block_size))
        return base64.b64encode(cipher.iv + encrypted).decode()

    def _sign(self, nonce, timestamp, body):
        raw = f"{body}:{timestamp}:{nonce}:{self.token}:{self.appkey}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _headers(self, nonce, timestamp, body):
        return {
            "User-Agent": self.ua,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "client_type": "android",
            "uuid": self.uuid,
            "timestamp": timestamp,
            "sign": self._sign(nonce, timestamp, body),
            "nonce": nonce,
            "appkey": self.appkey,
            "version": self.api_version,
            "api_version": "v1",
        }

    def _request(self, endpoint, data):
        nonce = base64.b64encode(uuid.uuid4().bytes).decode()
        ts = str(int(time.time() * 1000))
        payload = dict(data or {})
        payload.setdefault("token", self.token)
        payload.setdefault("timestamp", ts)
        payload.setdefault("nonce", nonce)
        encrypted = self._aes_encrypt(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), self.uuid)
        headers = self._headers(nonce, ts, encrypted)
        try:
            if requests is not None:
                resp = requests.post(f"{self.host}{endpoint}", data=encrypted, headers=headers, timeout=15)
                return self._aes_decrypt(resp.text, self.uuid)
            resp = self.post(f"{self.host}{endpoint}", data=encrypted, headers=headers)
            return self._aes_decrypt(getattr(resp, "text", ""), self.uuid)
        except Exception:
            return ""

    def _init_app(self):
        try:
            ts = str(int(time.time() * 1000))
            nonce = base64.b64encode(uuid.uuid4().bytes).decode()
            init_data = {
                "v": self.version_name, "n": self.name, "s": self.build_signature,
                "pl": "1", "apiVersion": "v2", "token": "",
                "timestamp": ts, "nonce": nonce,
            }
            encrypted = self._aes_encrypt(json.dumps(init_data, ensure_ascii=False, separators=(",", ":")), self.uuid)
            headers = self._headers(nonce, ts, encrypted)
            text = ""
            if requests is not None:
                resp = requests.post(f"{self.host}/app/systemInit", data=encrypted, headers=headers, timeout=15)
                text = resp.text
            else:
                resp = self.post(f"{self.host}/app/systemInit", data=encrypted, headers=headers)
                text = getattr(resp, "text", "")
            data = json.loads(self._aes_decrypt(text, self.uuid) or "{}")
            if isinstance(data.get("player"), dict):
                self.player_config = data.get("player", {})
            if isinstance(data.get("parser_api"), list):
                self.parser_apis = data.get("parser_api", [])
            if isinstance(data.get("parserapi"), list):
                self.parser_apis = data.get("parserapi", [])
            if isinstance(data.get("parses"), list):
                self.parser_apis = data.get("parses", [])
            if "categorys" in data:
                cat_data = data["categorys"]
                if isinstance(cat_data, dict) and "data" in cat_data:
                    self.categories = cat_data["data"]
                elif isinstance(cat_data, list):
                    self.categories = cat_data
            elif isinstance(data.get("categories"), list):
                self.categories = data.get("categories", [])
            self._login()
        except Exception:
            pass

    def _login(self):
        if self.token:
            return
        paths = []
        if self.login_path:
            paths.append(self.login_path)
        for path in ["/app/log", "/app/userInfo"]:
            if path not in paths:
                paths.append(path)
        for path in paths:
            try:
                ts = str(int(time.time() * 1000))
                nonce = base64.b64encode(uuid.uuid4().bytes).decode()
                login_data = {
                    "appName": self.name, "appkey": self.appkey, "package": self.package,
                    "buildNumber": self.build_number, "buildSignature": self.build_signature,
                    "uuid": self.uuid, "version": self.version_name,
                    "timestamp": ts, "nonce": nonce,
                }
                encrypted = self._aes_encrypt(json.dumps(login_data, ensure_ascii=False, separators=(",", ":")), self.uuid)
                headers = self._headers(nonce, ts, encrypted)
                text = ""
                if requests is not None:
                    resp = requests.post(f"{self.host}{path}", data=encrypted, headers=headers, timeout=15)
                    text = resp.text
                else:
                    resp = self.post(f"{self.host}{path}", data=encrypted, headers=headers)
                    text = getattr(resp, "text", "")
                data = json.loads(self._aes_decrypt(text, self.uuid) or "{}")
                if isinstance(data.get("data"), dict):
                    info = data.get("data", {})
                    self.token = str(info.get("token", self.token) or info.get("usertoken", self.token) or self.token)
                    self.uuid = str(info.get("uuid", self.uuid)) or self.uuid
                if data.get("userInfo") and data["userInfo"].get("user_token"):
                    self.token = data["userInfo"]["user_token"]
                if self.token:
                    return
            except Exception:
                continue

    # ---------------- 直播链路 ----------------

    def homeContent(self, filter=False):
        classes = [{"type_id": t, "type_name": n} for t, n in LIVE_CATEGORIES]
        cards = []
        try:
            pics = {}
            for o in self._group_cards("23"):
                pics[o.get("vod_name") or ""] = o.get("vod_pic") or ""
            for nm, gid in _GROUP_CARD_LIST:
                cards.append({"vod_id": gid, "vod_name": nm,
                              "vod_pic": pics.get(nm, ""), "vod_remarks": "直播"})
        except Exception:
            pass
        return {"class": classes, "filters": {t: [] for t, _, in LIVE_CATEGORIES},
                "list": cards}

    def homeVideoContent(self):
        return self.homeContent(False)

    def _group_cards(self, tid):
        """分类 tid → 分组卡片。只保留 央视频道/卫视频道 两组
        （服务端 6 组中：地方台直播=卫视频道、央视直播=央视频道 完全重复，
        湖南卫视/CCTV5 单台内容已含在两大组内，均不单独展示）。"""
        videos = []
        try:
            r = json.loads(self._request("/vod/search", {"kw": "", "page": "1", "limit": 21, "pid": str(tid), "orderBy": "time", "isCategory": 1}) or "{}")
            if "data" in r and isinstance(r["data"], list):
                for v in r["data"]:
                    if not isinstance(v, dict):
                        continue
                    name = str(v.get("name", ""))
                    if name not in KEEP_GROUPS:
                        continue
                    videos.append({
                        "vod_id": str(v.get("id", "")),
                        "vod_name": name,
                        "vod_pic": v.get("pic", ""),
                        "vod_remarks": v.get("remarks", ""),
                    })
        except Exception:
            pass
        return videos

    def categoryContent(self, tid, pg="1", filter=True, extend=""):
        """咕噜式：把分类下所有分组并发展开为具体台卡片（vod_remarks=分组名），
        OK影视 直播导航自动按分组显示。tid=23/未知一律全量展开直播。
        卫视频道组（906123）按台名二次拆分为 卫视频道/地方频道/其它频道。"""
        tid_s = str(tid or "").strip()
        key = ("live_" + tid_s) if tid_s in LIVE_IDS else "live_all"
        cached = _EXP_CACHE.get(key)
        if not (cached and time.time() - cached[0] < 1800):
            groups = self._group_cards(tid_s) if tid_s in LIVE_IDS else self._group_cards("23")
            items = []
            lock = threading.Lock()

            def _expand(one):
                vid = str(one.get("vod_id") or "")
                if not vid:
                    return
                try:
                    d = self.detailContent([vid])
                    vod = (d.get("list") or [None])[0]
                    if not vod:
                        return
                    grp_base = one.get("vod_name") or "直播"
                    pic = one.get("vod_pic") or vod.get("vod_pic") or ""
                    idx = 0
                    for ep in (vod.get("vod_play_url") or "").split("#"):
                        if "$" not in ep:
                            continue
                        idx += 1
                        nm = ep.split("$", 1)[0].replace("_", " ") or "台%d" % idx
                        if nm in _DEAD_NAMES:
                            continue
                        grp = grp_base if grp_base == "央视频道" else _sub_group(nm)
                        with lock:
                            # vod_pic 置空：服务端台级无图，借用分组大图会导致点播网格
                            # 卡片被同一张"CCTV/央视 直播"图占据、台名被挤到边缘，
                            # 置空后 OK影视 以台名为卡片主体，显示正常。
                            items.append({"vod_id": "%s_%s_%d" % (tid_s if tid_s in LIVE_IDS else "23", vid, idx),
                                          "vod_name": nm, "vod_pic": "", "vod_remarks": grp})
                except Exception:
                    pass

            threads = [threading.Thread(target=_expand, args=(o,), daemon=True) for o in groups]
            for t in threads:
                t.start()
            end = time.time() + 15
            for t in threads:
                t.join(max(0.0, end - time.time()))
            def _nat_key(nm):
                m = re.search(r"(\d+)", str(nm or ""))
                return (m.group(1).zfill(4), str(nm or "")) if m else ("zzzz", str(nm or ""))

            def _grp_key(x):
                remarks = x.get("vod_remarks") or ""
                nm = x.get("vod_name") or ""
                order = _GROUP_ORDER.get(remarks, 9)
                if remarks == "央视频道":
                    return (order, _nat_key(nm))
                return (order, _pinyin_key(nm), _nat_key(nm))

            items.sort(key=_grp_key)
            _EXP_CACHE[key] = (time.time(), items)
        items = [dict(i) for i in _EXP_CACHE[key][1]]
        return {"class": [{"type_id": t, "type_name": n} for t, n in LIVE_CATEGORIES],
                "filters": {}, "page": 1, "pagecount": 1, "limit": len(items),
                "total": len(items), "list": items}

    def detailContent(self, ids, flags=None):
        """分组卡 id（23_906124 / 23_906123 / 23_906123_地方 / 23_906123_综合）
        → 返回该分组全部台（咕噜式剧集列表）；台卡 vod_id（分类_分组id_序号）
        → 只返回第 N 台，play_url 为服务端下发的直出 URL。"""
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) else str(ids)
        if vid in _GROUP_CARD_IDS:
            return self._group_detail(vid)
        only_one = None
        if "_" in vid:
            parts = vid.split("_")
            if len(parts) >= 3:
                vid = parts[-2]
                try:
                    only_one = int(parts[-1])
                except Exception:
                    only_one = None
        vod = {"vod_id": str(ids[0]), "vod_name": "", "vod_pic": "",
               "vod_play_from": "直链", "vod_play_url": ""}
        try:
            r = json.loads(self._request("/vod/detail", {"id": vid, "eps": "1", "v": "2.0.0", "pl": 1}) or "{}")
            d = (r.get("data") or {}) if isinstance(r.get("data"), dict) else {}
            vod["vod_name"] = d.get("name", "")
            vod["vod_pic"] = d.get("pic", "")
            play_from_raw = d.get("play_from", d.get("playfrom", ""))
            play_url_raw = d.get("play_url", d.get("playurl", ""))
            froms = play_from_raw.split("$$$") if play_from_raw else []
            urls = play_url_raw.split("$$$") if play_url_raw else []
            eps = []
            for i, url_block in enumerate(urls):
                src_name = froms[i] if i < len(froms) else ""
                for ep in (url_block or "").split("#"):
                    parts2 = ep.split("$", 1)
                    if len(parts2) < 2:
                        continue
                    ep_name = parts2[0]
                    ep_url = parts2[1]
                    if src_name:
                        ep_url = "%s@%s@%s@%s" % (ep_url, src_name, vod["vod_name"], ep_name)
                    eps.append("%s$%s" % (ep_name, ep_url))
            if only_one is not None and eps:
                eps = eps[max(0, only_one - 1):only_one]
            vod["vod_play_from"] = "直链"
            vod["vod_play_url"] = "#".join(eps)
        except Exception:
            pass
        return {"list": [vod]}

    def _group_detail(self, card_id):
        """分组卡 → 服务端组展开 → 按分组规则裁剪 → vod_play_url=该组全部台。"""
        name, svc_id, rule = _GROUP_CARD_IDS[card_id]
        vod = {"vod_id": card_id, "vod_name": name, "vod_pic": "",
               "vod_play_from": "直链", "vod_play_url": ""}
        try:
            r = json.loads(self._request("/vod/detail", {"id": svc_id, "eps": "1", "v": "2.0.0", "pl": 1}) or "{}")
            d = (r.get("data") or {}) if isinstance(r.get("data"), dict) else {}
            play_url_raw = d.get("play_url", d.get("playurl", ""))
            eps = []
            for url_block in play_url_raw.split("$$$"):
                for ep in (url_block or "").split("#"):
                    p = ep.split("$", 1)
                    if len(p) < 2:
                        continue
                    nm = p[0].replace("_", " ") or ""
                    if not nm or nm in _DEAD_NAMES:
                        continue
                    if rule == "卫视" and not nm.endswith("卫视"):
                        continue
                    if rule == "地方" and _sub_group(nm) != "地方频道":
                        continue
                    if rule == "综合" and _sub_group(nm) != "综合频道":
                        continue
                    eps.append("%s$%s@直链@%s@%s" % (nm, p[1], name, nm))
            def _sort_key(ep):
                nm2 = ep.split("$", 1)[0]
                m = re.search(r"(\d+)", nm2)
                if rule == "央视":
                    return (m.group(1).zfill(4), nm2) if m else ("zzzz", nm2)
                return (_pinyin_key(nm2), (m.group(1).zfill(4) if m else "zzzz"), nm2)
            eps.sort(key=_sort_key)
            vod["vod_play_url"] = "#".join(eps)
        except Exception:
            pass
        return {"list": [vod]}

    def searchContent(self, key, quick=False, pg="1"):
        return {"list": []}

    def playerContent(self, flag, id, vipFlags=None):
        try:
            url = str(id)
            if "@" in url:
                url = url.split("@", 1)[0]
            if not url:
                return {"parse": 0, "url": "", "header": "{}"}
            return {"parse": 0, "url": url,
                    "header": json.dumps({"User-Agent": self.ua}, ensure_ascii=False)}
        except Exception:
            return {"parse": 0, "url": str(id), "header": "{}", "error": "playerContent fail"}

    def localProxy(self, param):
        try:
            fun = str(param.get("fun") or param.get("do") or "")
            if fun in ("ap", "APP99"):
                return self._proxy_live_channel(param)
        except Exception:
            pass
        return self._fallback_stream()

    def _fallback_stream(self):
        """死台兜底：返回源内 CCTV1 真实 m3u8（重写分片），保证播放器拿到可播流不崩溃。
        最终兜底：空 m3u8（#EXT-X-ENDLIST，无分片），播放器显示无信号而非崩溃。"""
        import urllib.request
        try:
            d = self.detailContent(["23_906124_1"])
            vod = (d.get("list") or [{}])[0]
            for ep in (vod.get("vod_play_url") or "").split("#"):
                if "$" not in ep:
                    continue
                raw = ep.split("$", 1)[1].split("@", 1)[0]
                pr = self.playerContent("", raw)
                raw = pr.get("url") or ""
                if not raw:
                    continue
                req = urllib.request.Request(
                    raw, headers={"User-Agent": self.ua, "Referer": self.host or ""})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    body = resp.read()
                    final_url = resp.geturl()
                    ct = resp.headers.get("Content-Type", "application/vnd.apple.mpegurl")
                    try:
                        text = body.decode("utf-8", "replace")
                        if "#EXTM3U" in text:
                            body = self._rewrite_m3u8(text, final_url).encode("utf-8")
                            ct = "application/vnd.apple.mpegurl"
                        else:
                            return [200, "application/vnd.apple.mpegurl",
                                    b"#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-ENDLIST\n", None]
                    except Exception:
                        return [200, "application/vnd.apple.mpegurl",
                                b"#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-ENDLIST\n", None]
                    return [200, ct, body, None]
            raise RuntimeError("no cctv1 ep")
        except Exception:
            return [200, "application/vnd.apple.mpegurl",
                    b"#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-ENDLIST\n", None]

    def _proxy_live_channel(self, param):
        vid = str(param.get("id") or "")
        if not vid:
            return self._fallback_stream()
        try:
            d = self.detailContent([vid])
            vod = (d.get("list") or [{}])[0]
            eps = (vod.get("vod_play_url") or "").split("#")
            if not eps:
                return self._fallback_stream()
            ep = eps[0]
            raw_url = ep.split("$", 1)[1] if "$" in ep else ep
            pr = self.playerContent("", raw_url)
            raw_url = pr.get("url") or ""
            if not raw_url:
                return self._fallback_stream()
            import urllib.request
            req = urllib.request.Request(
                raw_url,
                headers={"User-Agent": self.ua, "Referer": self.host or ""})
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read()
                final_url = resp.geturl()
                ct = resp.headers.get("Content-Type", "application/vnd.apple.mpegurl")
            try:
                text = body.decode("utf-8", "replace")
                if "#EXTM3U" in text:
                    text = self._rewrite_m3u8(text, final_url)
                    body = text.encode("utf-8")
                    ct = "application/vnd.apple.mpegurl"
                else:
                    return self._fallback_stream()
            except Exception:
                return self._fallback_stream()
            return [200, ct, body, None]
        except Exception:
            return self._fallback_stream()

    @staticmethod
    def _rewrite_m3u8(content, base_url):
        from urllib.parse import urljoin
        out = []
        for line in content.splitlines():
            s = line.strip()
            if not s:
                out.append(line)
                continue
            if s.startswith("#"):
                if 'URI="' in s:
                    line = re.sub(r'URI="([^"]*)"',
                                  lambda m: 'URI="' + urljoin(base_url, m.group(1)) + '"',
                                  line)
                out.append(line)
            else:
                out.append(urljoin(base_url, s))
        return "\n".join(out)

    def liveContent(self, url):
        """直播源入口（咕噜式）：全量台卡 → M3U（group-title=分组、tvg-name=台名），
        每台走 localProxy(fun=ap) 延迟解析，播放时才解析直出 URL，避免 token 过期。"""
        base_proxy = self.getProxyUrl() or ''
        use_proxy = bool(base_proxy)
        if use_proxy and not base_proxy.endswith(('?', '&')):
            base_proxy += '&'
        try:
            cards = self.categoryContent("23", "1", True, "").get("list") or []
        except Exception:
            cards = []
        lines = ["#EXTM3U"]
        for c in cards:
            vid = str(c.get("vod_id") or "")
            nm = str(c.get("vod_name") or "")
            grp = str(c.get("vod_remarks") or "直播")
            if not vid or not nm:
                continue
            if use_proxy:
                ch_url = base_proxy + "fun=ap&id=" + quote(vid)
            else:
                try:
                    d = self.detailContent([vid])
                    vod = (d.get("list") or [{}])[0]
                    eps = (vod.get("vod_play_url") or "").split("#")
                    ep = eps[0] if eps else ""
                    raw = ep.split("$", 1)[1] if "$" in ep else ep
                    ch_url = self.playerContent("", raw).get("url") or ""
                except Exception:
                    ch_url = ""
            if not ch_url:
                continue
            lines.append('#EXTINF:-1 tvg-name="%s" group-title="%s",%s' % (nm, grp, nm))
            lines.append(ch_url)
        return "\n".join(lines)


# ---------------- 模块级双入口（兼容 OK影视 / drpy） ----------------
import threading

_spider = None


def _get_spider():
    global _spider
    if _spider is None:
        _spider = Spider()
        try:
            _spider.init("")
        except Exception:
            pass
    return _spider


def homeContent(filter=False):
    return _get_spider().homeContent(filter)


def homeVideoContent():
    return _get_spider().homeVideoContent()


def categoryContent(tid, pg="1", filter=True, extend=""):
    return _get_spider().categoryContent(tid, pg, filter, extend)


def detailContent(ids, flags=None):
    return _get_spider().detailContent(ids, flags)


def searchContent(key, quick=False, pg="1"):
    return _get_spider().searchContent(key, quick, pg)


def playerContent(flag, id, vipFlags=None):
    return _get_spider().playerContent(flag, id, vipFlags)


def localProxy(param):
    return _get_spider().localProxy(param)


def liveContent(url):
    return _get_spider().liveContent(url)


def getDependence():
    return []


spider = Spider
