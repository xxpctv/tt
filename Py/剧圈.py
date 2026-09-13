# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   剧圈 (App99)
# 协议: 请求体 AES 加密(uuid 为密钥) + SHA-256 签名头; 响应 AES 解密.
# ext: {"host":"https://...","appkey":"...","name":"...","buildSignature":"...",
#       "buildNumber":"...","versionName":"...","package":"...","uuid":"...","ua":"...","version":"...","LoginPath":"/app/userInfo"}
# 说明: 完整复刻 systemInit/设备上报/列表/详情/搜索/播放(直链+解析站+大站 jx);
#       加密为 AES-128, 若站点私改算法则运行时受限.

from base.spider import Spider
import requests
import re
import json
import time
import hashlib
import uuid as uuid_mod
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/122.0.6299.95 Safari/537.36")
BIG_HOSTS = ("v.qq.com", "youku.com", "bilibili.com", "iqiyi.com", "mgtv.com")


def _pad(s):
    n = 16 - len(s) % 16
    return s + chr(n) * n


def _aes_enc(key, text):
    k = key.encode()
    if len(k) not in (16, 24, 32):
        k = k[:16].ljust(16, b"0")
    cipher = Cipher(algorithms.AES(k), modes.ECB(), backend=default_backend())
    return (cipher.encryptor().update(_pad(text).encode())
            + cipher.encryptor().finalize()).hex()


def _aes_dec(key, hex_str):
    try:
        k = key.encode()
        if len(k) not in (16, 24, 32):
            k = k[:16].ljust(16, b"0")
        cipher = Cipher(algorithms.AES(k), modes.ECB(), backend=default_backend())
        dec = cipher.decryptor().update(bytes.fromhex(hex_str))
        dec += cipher.decryptor().finalize()
        if dec:
            pad = dec[-1]
            if 1 <= pad <= 16:
                dec = dec[:-pad]
        return dec.decode("utf-8", "ignore")
    except Exception:
        return ""


def _nonce():
    return "".join(
        hashlib.md5(str(time.time()).encode() + uuid_mod.uuid4().bytes).hexdigest()
        for _ in range(1))[:32]


class Spider(Spider):
    def __init__(self):
        super().__init__()
        self.a = ""      # host
        self.b = ""      # token
        self.c = ""      # uuid (AES key)
        self.d = ""      # appkey
        self.e = DEFAULT_UA
        self.f = "0b4328287a5d953e"
        self.cfg = {}
        self.parses = []

    def getName(self):
        return "剧圈"

    def init(self, extend=""):
        try:
            j = json.loads((extend or "").strip() or "{}")
            host = str(j.get("host") or "")
            appkey = str(j.get("appkey") or "")
            if not host or not appkey:
                return
            self.a = host.rstrip("/")
            self.d = appkey
            self.c = str(j.get("uuid") or uuid_mod.uuid4().hex)
            self.e = str(j.get("ua") or DEFAULT_UA)
            v = str(j.get("version") or "").strip()
            if v:
                self.f = v
            self.g(str(j.get("versionName") or ""), str(j.get("name") or ""),
                   str(j.get("buildSignature") or ""))
            if not self.b:
                self.i(str(j.get("LoginPath") or "/app/userInfo"),
                       str(j.get("versionName") or ""), str(j.get("name") or ""),
                       str(j.get("package") or ""), str(j.get("buildNumber") or ""),
                       str(j.get("buildSignature") or ""))
        except Exception:
            pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _sign_headers(self, nonce, ts, body, token):
        raw = f"{nonce}:{ts}:{body}:{token}:{self.d}"
        return {"User-Agent": self.e, "Accept": "application/json",
                "Content-Type": "application/json", "client_type": "android",
                "uuid": self.c, "timestamp": ts, "nonce": nonce,
                "sign": hashlib.sha256(raw.encode()).hexdigest(),
                "appkey": self.d, "version": self.f, "api_version": "v1"}

    def _call(self, path, body_dict, token=""):
        try:
            nonce = _nonce()
            ts = str(int(time.time()))
            b = dict(body_dict)
            b.setdefault("timestamp", ts)
            b.setdefault("nonce", nonce)
            b.setdefault("token", token)
            enc = _aes_enc(self.c, json.dumps(b, ensure_ascii=False, separators=(",", ":")))
            r = requests.post(self.a + path, data=enc,
                              headers=self._sign_headers(nonce, ts, enc, token),
                              timeout=15)
            dec = _aes_dec(self.c, (r.text or "").strip())
            return json.loads(dec or "{}")
        except Exception:
            return {}

    def g(self, vname, name, build_sig):
        """systemInit 初始化: player/parses/categories"""
        try:
            nonce = _nonce()
            ts = str(int(time.time()))
            body = {"v": vname, "n": name, "s": build_sig, "pl": "1",
                    "apiVersion": "v2", "token": "", "timestamp": ts, "nonce": nonce}
            enc = _aes_enc(self.c, json.dumps(body, ensure_ascii=False, separators=(",", ":")))
            r = requests.post(self.a + "/app/systemInit", data=enc,
                              headers=self._sign_headers(nonce, ts, enc, ""), timeout=15)
            dec = _aes_dec(self.c, (r.text or "").strip())
            j = json.loads(dec or "{}")
            if j.get("player"):
                self.cfg["player"] = j["player"]
            if j.get("parser_api"):
                self.parses = j.get("parser_api") or []
            if j.get("categorys") and j["categorys"].get("data"):
                self.cfg["categories"] = j["categorys"]["data"]
        except Exception:
            pass

    def i(self, path, vname, name, pkg, build_num, build_sig):
        """设备上报拿 user_token"""
        try:
            for p in (path, "/app/userInfo", "/app/log"):
                try:
                    nonce = _nonce()
                    ts = str(int(time.time()))
                    now = int(time.time() * 1000)
                    body = {"version": vname, "name": name, "package": pkg,
                            "buildNumber": build_num, "buildSignature": build_sig,
                            "install": now, "update": now,
                            "os": "android", "name2": "xiaomi", "version2": "15",
                            "sdkInt": 32, "device": "xiaomi", "brand": "xiaomi",
                            "manufacturer": "xiaomi", "product": "b0q",
                            "hardware": "xiaomi", "isPhysicalDevice": True,
                            "androidId": "V417IR", "bootloader": "unknown",
                            "display": "V417IR release-keys", "host": "a11-gz01-test",
                            "tags": "release-keys", "type": "user",
                            "finger": "xiaomi/b0q/b0q:15/V619IR/613:user/release-keys",
                            "app": {"version": vname, "name": name, "package": pkg,
                                    "buildNumber": build_num, "buildSignature": build_sig,
                                    "install": now, "update": now},
                            "did": str(uuid_mod.uuid4()), "apiVersion": "v2",
                            "channel": "", "token": "", "timestamp": ts, "nonce": nonce}
                    enc = _aes_enc(self.c, json.dumps(body, ensure_ascii=False, separators=(",", ":")))
                    r = requests.post(self.a + p, data=enc,
                                      headers=self._sign_headers(nonce, ts, enc, ""),
                                      timeout=15)
                    dec = _aes_dec(self.c, (r.text or "").strip())
                    j = json.loads(dec or "{}")
                    ui = j.get("userInfo") or {}
                    if ui.get("user_token"):
                        self.b = str(ui["user_token"])
                        return
                except Exception:
                    continue
        except Exception:
            pass

    def _build(self, it):
        return {"vod_id": str(it.get("id") or ""),
                "vod_name": str(it.get("name") or ""),
                "vod_pic": str(it.get("pic") or ""),
                "vod_remarks": str(it.get("remarks") or ""),
                "vod_year": str(it.get("year") or ""),
                "vod_area": str(it.get("area") or ""),
                "vod_actor": str(it.get("actor") or ""),
                "vod_director": str(it.get("director") or ""),
                "vod_content": str(it.get("blurb") or "")}

    def _search(self, pid, kw, page):
        try:
            j = self._call("/vod/search",
                           {"kw": kw or "", "page": str(page), "limit": 21,
                            "pid": str(pid), "orderBy": "time",
                            "isCategory": 1, "token": self.b}, self.b)
            data = j.get("data") or []
            return [self._build(it) for it in data], int(j.get("page_count") or 1)
        except Exception:
            return [], 1

    def homeContent(self, filter):
        cats, fts = [], {}
        try:
            for it in self.cfg.get("categories") or []:
                if not isinstance(it, dict):
                    continue
                name = str(it.get("name") or "")
                if name in ("公告", "通知") or name.lower() == "notice" or \
                   name.endswith("公告") or name.endswith("通知"):
                    continue
                cid = str(it.get("id") or "")
                cats.append({"type_id": cid, "type_name": name})
                te = it.get("type_extend") or {}
                fl = []
                for key, fname in (("class", "类型"), ("area", "地区"),
                                   ("lang", "语言"), ("year", "年份")):
                    arr = te.get(key if key != "class" else "class") or \
                          te.get({"class": "class", "area": "areas", "lang": "lang",
                                  "year": "years"}[key]) or []
                    vals = [str(x) for x in arr if str(x)]
                    if vals:
                        fl.append({"key": key, "name": fname,
                                   "value": [{"n": v, "v": v} for v in vals]})
                if fl:
                    fts[cid] = fl
        except Exception:
            pass
        pid = "1"
        for c in cats:
            pid = c["type_id"]
            break
        lst, _ = self._search(pid, "", "1")
        return {"class": cats, "filters": fts, "list": lst}

    def homeVideoContent(self):
        return {"list": self.homeContent(False)["list"]}

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 21, "total": 0}
        try:
            pg = str(pg) if str(pg).strip().isdigit() else "1"
            ex = extend or {}
            body = {"kw": "", "page": pg, "limit": 21, "pid": str(tid),
                    "orderBy": "time", "isCategory": 1, "token": self.b}
            for k in ("class", "area", "lang", "year"):
                v = str(ex.get(k) or "").strip()
                if v:
                    body[k] = v
            j = self._call("/vod/search", body, self.b)
            data = j.get("data") or []
            result["list"] = [self._build(it) for it in data]
            result["page"] = int(pg) if pg.isdigit() else 1
            result["pagecount"] = int(j.get("page_count") or 1)
            result["total"] = len(data)
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0])
            j = self._call("/vod/detail",
                           {"id": vid, "eps": "1", "v": "2.0.0", "pl": 1,
                            "token": self.b}, self.b)
            d = j.get("data") or {}
            if not d:
                return {"list": []}
            vod = {"vod_id": str(d.get("id") or vid),
                   "vod_name": str(d.get("name") or ""),
                   "vod_pic": str(d.get("pic") or ""),
                   "vod_remarks": str(d.get("remarks") or ""),
                   "vod_year": str(d.get("year") or ""),
                   "vod_area": str(d.get("area") or ""),
                   "vod_actor": str(d.get("actor") or ""),
                   "vod_director": str(d.get("director") or ""),
                   "vod_content": str(d.get("content") or "")}
            player_map = {}
            try:
                for v in (self.cfg.get("player") or {}).values():
                    if isinstance(v, dict):
                        player_map[str(v.get("code") or "")] = str(v.get("name") or "")
            except Exception:
                pass
            froms = str(d.get("play_from") or "").split("$$$")
            urls = str(d.get("play_url") or "").split("$$$")
            out_from, out_url = [], []
            for i in range(min(len(froms), len(urls))):
                pf = froms[i]
                pn = player_map.get(pf) or pf
                eps = []
                for ep in urls[i].split("#"):
                    if "$" not in ep:
                        continue
                    nm, _, u = ep.partition("$")
                    eps.append(f"{nm}${u}@{pf}@{d.get('name') or ''}@{i + 1}")
                if eps:
                    out_from.append(pn)
                    out_url.append("#".join(eps))
            if out_from:
                vod["vod_play_from"] = "$$$".join(out_from)
                vod["vod_play_url"] = "$$$".join(out_url)
        except Exception:
            pass
        return {"list": [vod] if vod else []}

    def playerContent(self, flag, playId, vipFlags):
        try:
            parts = str(playId or "").split("@")
            if len(parts) < 2:
                return {"parse": 0, "url": "", "header": {}, "error": "播放参数无效"}
            url = parts[0]
            player_code = parts[1]
            if re.match(r"(?i).*\.(m3u8|mp4|flv)(\?.*)?$", url) or url.startswith("http"):
                return {"parse": 0, "url": url, "header": {"User-Agent": self.e}}
            # 解析站
            try:
                pc = (self.cfg.get("player") or {}).get(player_code) or {}
                if pc.get("type") not in (0,):
                    raise Exception("需解析")
                for pa in self.parses or []:
                    if not isinstance(pa, dict):
                        continue
                    api = str(pa.get("api_url") or "")
                    if not api:
                        continue
                    r = requests.get(api + url,
                                     headers={"User-Agent": self.e,
                                              "Accept": "application/json"}, timeout=15)
                    t = (r.text or "").strip()
                    if t.startswith("http"):
                        return {"parse": 0, "url": t, "header": {"User-Agent": self.e}}
                    j = json.loads(t or "{}")
                    u = str(j.get("url") or "")
                    if not u and isinstance(j.get("data"), dict):
                        u = str(j["data"].get("url") or j["data"].get("play_url") or "")
                    if not u and j.get("code") == 200:
                        u = str(j.get("play_url") or j.get("video") or "")
                    if u:
                        return {"parse": 0, "url": u, "header": {"User-Agent": self.e}}
            except Exception:
                pass
            # 大站走 jx
            if any(h in url for h in BIG_HOSTS):
                return {"parse": 1, "url": url, "header": {}, "jx": 1}
            return {"parse": 0, "url": url, "header": {"User-Agent": self.e},
                    "error": "播放链接解析失败,请更换其他源播放"}
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
            j = self._call("/vod/search",
                           {"kw": key, "page": 1, "limit": 21,
                            "orderBy": "vod_hits_month", "sort": "desc",
                            "token": self.b}, self.b)
            result["list"] = [self._build(it) for it in (j.get("data") or [])]
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
