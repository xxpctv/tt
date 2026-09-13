# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   瓜子影视 (Gz360)
# 协议: 设备认证(RSA握手) -> 请求体 AES-CBC(hex) + RSA公钥封装 + MD5签名
#       -> 响应 RSA私钥解 keys -> AES 解 response_key
# 说明: 完整复刻 JAR 加密通信, 分类/搜索/详情/播放全可用; 每次运行自动认证获取 token.
#       播放地址为 gz2.{base64}, 引擎手动解析, 播放 header 带 Referer/UA.

from base.spider import Spider
import requests
import re
import json
import base64
import hashlib
import random
import time
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.serialization import load_der_public_key, load_der_private_key
from cryptography.hazmat.backends import default_backend

HOSTS = ["https://apinew.uozvr.com", "https://sdapi.e2wu4ht.com",
         "https://api.w32z7vtd.com", "https://api.6a7nnf7.com",
         "https://api.umygrx3.com", "https://api.rmedphk.com"]
RSA_PUB = ("MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDUM5+/y8sPsWkd1/RQS64X259EUwx"
           "FXFE5HlA65MqrxnPs0JqoSRojSDy5QhwvROlaD6TwRQHKMY2OAZ6SnQeUJsChTEFIR9qUkw"
           "rs3/MVUMxjsv6JS6Oe/juclyJGTgVmDhB55EafXsD0SQYVj/QXXsxR6ewR5E2kL52yAAD4yQIDAQAB")
RSA_PRI = ("MIICdgIBADANBgkqhkiG9w0BAQEFAASCAmAwggJcAgEAAoGAe6hKrWLi1zQmjTT1"
           "ozbE4QdFeJGNxubxld6GrFGximxfMsMB6BpJhpcTouAqywAFppiKetUBBbXwYsYU1wNr"
           "648XVmPmCMCy4rY8vdliFnbMUj086DU6Z+/oXBdWU3/b1G0DN3E9wULRSwcKZT3wj/cCI"
           "1vsCm3gj2R5SqkA9Y0CAwEAAQKBgAJH+4CxV0/zBVcLiBCHvSANm0l7HetybTh/j2p0Y"
           "1sTXro4ALwAaCTUeqdBjWiLSo9lNwDHFyq8zX90+gNxa7c5EqcWV9FmlVXr8VhfBzcZo"
           "1nXeNdXFT7tQ2yah/odtdcx+vRMSGJd1t/5k5bDd9wAvYdIDblMAg+wiKKZ5KcdAkEA"
           "1cCakEN4NexkF5tHPRrR6XOY/XHfkqXxEhMqmNbB9U34saTJnLWIHC8IXys6Qmzz30Tt"
           "zCjuOqKRRy+FMM4TdwJBAJQZFPjsGC+RqcG5UvVMiMPhnwe/bXEehShK86yJK/g/UiKr"
           "O87h3aEu5gcJqBygTq3BBBoH2md3pr/W+hUMWBsCQQChfhTIrdDinKi6lRxrdBnn0Ohj"
           "g2cwuqK5zzU9p/N+S9x7Ck8wUI53DKm8jUJE8WAG7WLj/oCOWEh+ic6NIwTdAkEAj0X"
           "8nhx6AXsgCYRql1klbqtVmL8+95KZK7PnLWG/IfjQUy3pPGoSaZ7fdquG8bq8oyf5+dzj"
           "E/oTXcByS+6XRQJAP/5ciy1bL3NhUhsaOVy55MHXnPjdcTX0FaLi+ybXZIfIQ2P4rb19m"
           "Vq1feMbCXhz+L1rG8oat5lYKfpe8k83ZA==")
SIGN_KEY = "*&zvdvdvddbfikkkumtmdwqppp?|4Y!s!2br"
SIZES = ["3840", "2160", "1080", "720", "480", "360", "240"]
CLASSES = [["1", "电影"], ["2", "电视剧"], ["3", "动漫"], ["4", "综艺"],
           ["64", "短剧"], ["72", "音乐"], ["74", "AI漫剧"], ["73", "电影解说"],
           ["71", "体育解说"], ["70", "电竞解说"]]
SUBS = {"1": "动作片:5,悬疑片:29,喜剧片:6,爱情片:7,科幻片:8,恐怖片:9,剧情片:10,战争片:11,动画片:36,纪录片:20,灾难片:38,犯罪片:61",
        "2": "国产剧:12,香港剧:13,台湾剧:14,欧美剧:15,日本剧:16,韩国剧:17,海外剧:18,泰国剧:19,新加坡剧:69",
        "3": "中国动漫:30,日本动漫:31,欧美动漫:33",
        "4": "大陆综艺:22,港台综艺:23,日韩综艺:24,欧美综艺:25"}
SUB_MAP = {"1": "5", "2": "12", "3": "30", "4": "22"}


def _rand_str(n=16):
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(random.choice(chars) for _ in range(n))


def _aes_cbc_enc_hex(text, key, iv):
    pad = 16 - len(text.encode()) % 16
    data = text.encode() + bytes([pad]) * pad
    cipher = Cipher(algorithms.AES(key.encode()), modes.CBC(iv.encode()),
                    backend=default_backend())
    enc = cipher.encryptor().update(data) + cipher.encryptor().finalize()
    return enc.hex().upper()


def _aes_cbc_dec_hex(hex_str, key, iv):
    try:
        data = bytes.fromhex(hex_str)
    except Exception:
        return ""
    try:
        cipher = Cipher(algorithms.AES(key.encode()), modes.CBC(iv.encode()),
                        backend=default_backend())
        dec = cipher.decryptor().update(data) + cipher.decryptor().finalize()
        pad = dec[-1] if dec else 0
        if 1 <= pad <= 16:
            dec = dec[:-pad]
        return dec.decode("utf-8", "ignore")
    except Exception:
        return ""


def _rsa_pub_enc(text):
    key = load_der_public_key(base64.b64decode(RSA_PUB), backend=default_backend())
    enc = key.encrypt(text.encode(), asym_padding.PKCS1v15())
    return base64.b64encode(enc).decode()


def _rsa_pri_dec(b64):
    key = load_der_private_key(base64.b64decode(RSA_PRI), None, backend=default_backend())
    out = b""
    data = base64.b64decode(b64)
    for i in range(0, len(data), 128):
        out += key.decrypt(data[i:i + 128], asym_padding.PKCS1v15())
    return out.decode("utf-8", "ignore")


def _md5_upper(s):
    return hashlib.md5(s.encode()).hexdigest().upper()


class Spider(Spider):
    def __init__(self):
        super().__init__()
        self.host = HOSTS[0]
        self.device_key = ""
        self.device_id = ""
        self.token = ""
        self.token_id = ""
        self.play_ref = "http://WJiZxLXA2.com/"
        self.ready = False

    def getName(self):
        return "瓜子影视"

    def init(self, extend=""):
        self.device_key = "".join(random.choice("0123456789ABCDEF") for _ in range(40))
        self.device_id = str(random.randint(0, 9999) + 864150060000000)
        try:
            self._auth()
            self.ready = True
        except Exception:
            pass

    def isVideoFormat(self, url):
        u = (url or "").lower()
        return any(x in u for x in (".m3u8", ".mp4", ".ts", "/proxy?do=gz360"))

    def manualVideoCheck(self):
        return True

    def _auth(self):
        # 先 refresh(空 token) -> 失败则 注册/登录
        try:
            r = self._req("/App/Authentication/Authenticator/refresh", "{}", auth=True)
            self._apply_token(r)
            return
        except Exception:
            pass
        body = json.dumps({"new_key": self.device_key, "old_key": "aLFBMWpxBrIDAD1Si/KVvm41"})
        try:
            r = self._req("/App/Authentication/Device/signIn", body, auth=True)
        except Exception:
            body = json.dumps({"new_key": self.device_key, "old_key": "aLFBMWpxBrIDAD1Si/KVvm41",
                               "phone_type": 1, "code": ""})
            r = self._req("/App/Authentication/Device/signUp", body, auth=True)
        self._apply_token(r)
        try:
            r = self._req("/App/Authentication/Authenticator/refresh", "{}", auth=True)
            self._apply_token(r)
        except Exception:
            pass

    def _apply_token(self, j):
        t = str(j.get("token") or "")
        if not t:
            raise Exception("认证失败，无 token")
        self.token = t
        if j.get("app_user_id"):
            self.token_id = str(j["app_user_id"])

    def _req(self, path, body, auth=False):
        if not auth and not self.token:
            self._auth()
        aes_key = _rand_str()
        aes_iv = _rand_str()
        enc_hex = _aes_cbc_enc_hex(body, aes_key, aes_iv)
        keys_json = json.dumps({"iv": aes_iv, "key": aes_key}, separators=(",", ":"))
        rsa_b64 = _rsa_pub_enc(keys_json)
        ts = str(int(time.time()))
        sign = _md5_upper(
            f"token_id={self.token_id},token={self.token},phone_type=1,"
            f"request_key={enc_hex},app_id=1,time={ts},keys={rsa_b64}{SIGN_KEY}")
        form = {"token_id": self.token_id, "token": self.token, "phone_type": "1",
                "request_key": enc_hex, "app_id": "1", "time": ts,
                "keys": rsa_b64, "signature": sign,
                "phone_model": "xiaomi-22081212c", "ad_version": "1"}
        headers = {"User-Agent": "okhttp/3.12.0",
                   "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                   "Ver": "3.0.4.8", "Version": "2606029", "api-ver": "3.0.4.8",
                   "PackageName": "com.v54f07a912.t4ee50f184.dbb1e7669f20260721",
                   "code": "GZ0313", "deviceId": self.device_id,
                   "lang": "zh_cn", "Cache-Control": "no-cache", "Referer": self.host}
        last_err = None
        for i in range(6):
            host = HOSTS[(HOSTS.index(self.host) + i) % 6]
            try:
                r = requests.post(host + path, data=form, headers=headers, timeout=15)
                text = r.text or ""
                root = json.loads(text) if text else {}
                if root.get("code") not in (None, 200):
                    raise Exception(f"业务错误 code={root.get('code')}")
                data = root.get("data") or {}
                if not data.get("keys") or not data.get("response_key"):
                    raise Exception("缺加密封装")
                keyinfo = json.loads(_rsa_pri_dec(data["keys"]))
                return json.loads(_aes_cbc_dec_hex(data["response_key"],
                                                   keyinfo["key"], keyinfo["iv"]))
            except Exception as e:
                last_err = e
                self.host = host
                if "code=" in str(e):
                    self.token = ""
                    self.token_id = ""
                    self._auth()
                    raise
        raise last_err or Exception("请求失败")

    def _vod_list(self, j):
        out = []
        for it in (j.get("list") or []):
            if not isinstance(it, dict):
                continue
            vid = str(it.get("vod_id") or "")
            name = str(it.get("vod_name") or "")
            if not vid or not name:
                continue
            cont = str(it.get("vod_continu") or "")
            score = str(it.get("vod_scroe") or "")
            remark = f"更新至{cont}集" if cont and cont != "0" else score
            out.append({"vod_id": vid, "vod_name": name,
                        "vod_pic": str(it.get("vod_pic") or ""),
                        "vod_year": str(it.get("vod_year") or ""),
                        "vod_remarks": remark})
        return out

    def homeContent(self, filter):
        cats = [{"type_id": cid, "type_name": name} for cid, name in CLASSES]
        fts = {}
        for cid, sub in SUBS.items():
            fts[cid] = [{"key": "sub", "name": "类型",
                         "value": [{"n": n, "v": v} for pair in sub.split(",")
                                   for n, v in [pair.split(":")] if len(pair.split(":")) > 1]}]
        lst = []
        try:
            j = self._req("/App/IndexList/index",
                          json.dumps({"ns": "", "nt": str(int(time.time())), "pid": "1"}))
            for sec in (j.get("list") or [])[1:]:
                if isinstance(sec, dict):
                    lst.extend(self._vod_list(sec))
        except Exception:
            pass
        return {"class": cats, "filters": fts, "list": lst}

    def homeVideoContent(self):
        return {"list": self.homeContent(False)["list"]}

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 30, "total": 0}
        try:
            pg = str(pg) if str(pg).strip().isdigit() else "1"
            ex = extend or {}
            sub = str(ex.get("sub") or "").strip() or SUB_MAP.get(str(tid), "")
            body = {"area": str(ex.get("area") or "0"),
                    "sub": sub,
                    "year": str(ex.get("year") or "0"),
                    "sort": str(ex.get("sort") or "d_id"),
                    "page": pg, "pageSize": "30", "tid": str(tid)}
            j = self._req("/App/IndexList/indexList", json.dumps(body))
            lst = self._vod_list(j)
            result["list"] = lst
            n = int(pg) if pg.isdigit() else 1
            result["page"] = n
            result["pagecount"] = n + 1 if len(lst) >= 30 else n
            result["total"] = 0
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0])
            body = {"token_id": self.token_id, "vod_id": vid,
                    "mobile_time": str(int(time.time())), "token": self.token}
            j = self._req("/App/IndexPlay/playInfo", json.dumps(body))
            vi = j.get("vodInfo") or {}
            if not vi:
                return {"list": [], "error": "详情获取失败"}
            r2 = self._req("/App/Resource/Vurl/show",
                           json.dumps({"vurl_cloud_id": "2", "vod_d_id": vid}))
            eps = []
            for i, it in enumerate(r2.get("list") or []):
                title = str(it.get("title") or "") or f"第{i + 1}集"
                play = it.get("play") or {}
                best, avail = "", []
                for size in SIZES:
                    p = play.get(size)
                    if not isinstance(p, dict):
                        continue
                    if str(p.get("show_type")) == "2":
                        continue
                    param = str(p.get("param") or "")
                    if not param:
                        continue
                    avail.append(size)
                    if not best:
                        best = param
                if not best:
                    continue
                u = best + "&_client_ts=" + str(time.time_ns())
                if avail:
                    u += "||" + "@".join(avail)
                eps.append(f"{title}${'gz2.' + base64.b64encode(u.encode()).decode()}")
            vod = {"vod_id": vid,
                   "vod_name": str(vi.get("vod_name") or ""),
                   "vod_pic": str(vi.get("vod_pic") or ""),
                   "vod_content": str(vi.get("vod_use_content") or ""),
                   "vod_actor": str(vi.get("vod_actor") or ""),
                   "vod_director": str(vi.get("vod_director") or ""),
                   "vod_area": str(vi.get("vod_area") or ""),
                   "vod_year": str(vi.get("vod_year") or ""),
                   "vod_remarks": str(vi.get("vod_scroe") or "")}
            if eps:
                vod["vod_play_from"] = "瓜子"
                vod["vod_play_url"] = "#".join(eps)
        except Exception:
            pass
        return {"list": [vod] if vod else []}

    def playerContent(self, flag, playId, vipFlags):
        try:
            pid = (playId or "").strip()
            if not pid:
                return {"parse": 0, "url": "", "header": {}, "error": "瓜子播放参数错误"}
            if pid.startswith("gz2."):
                raw = base64.b64decode(pid[4:]).decode("utf-8", "ignore")
            elif pid.startswith("gz1."):
                raw = base64.b64decode(pid[4:]).decode("utf-8", "ignore")
            else:
                raw = pid
            # 分离 清晰度列表
            res_list = []
            if "||" in raw:
                raw, _, tail = raw.partition("||")
                res_list = [s for s in tail.split("@") if s]
            params = {}
            for kv in raw.replace(";;", "&").split("&"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    if k and v and k not in params:
                        params[k] = v
            if not params:
                return {"parse": 0, "url": "", "header": {}, "error": "瓜子播放参数错误"}
            if "vod_d_id" in params and not params.get("vod_id"):
                params["vod_id"] = params.pop("vod_d_id")
            else:
                params.pop("vod_d_id", None)
            params["_client_ts"] = str(time.time_ns())
            params["mobile_time"] = str(int(time.time()))
            params["rand"] = str(abs(random.getrandbits(31)))
            resolution = params.get("resolution") or "1080"
            if res_list:
                best = max(res_list, key=lambda s: int(re.sub(r"\D+", "", s) or 0))
                resolution = best
            params["resolution"] = resolution
            params["type"] = "play"
            body = {k: v for k, v in params.items() if k and v}
            if not body:
                return {"parse": 0, "url": "", "header": {}, "error": "瓜子播放参数错误"}
            j = self._req("/App/Resource/VurlDetail/showOne", json.dumps(body))
            url = str(j.get("m3u8") or "")
            if url == "1" or not url:
                url = str(j.get("vurl") or "")
            if not url:
                url = str(j.get("url") or "")
            if not url or not url.startswith("http"):
                return {"parse": 0, "url": "", "header": {}, "error": "播放链接解析失败"}
            try:
                ui = self._req("/App/UserInfo/getUserInfo", "{}")
                pr = str(ui.get("playRef") or "").strip()
                if pr.startswith("http"):
                    self.play_ref = pr
            except Exception:
                pass
            header = {"User-Agent": "Lavf/57.83.100", "Referer": self.play_ref}
            return {"parse": 0, "url": url, "header": header}
        except Exception:
            return {"parse": 0, "url": "", "header": {}, "error": "播放链接解析失败"}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            body = {"keywords": key, "ns": "", "nt": str(int(time.time())),
                    "order_val": "1"}
            j = self._req("/App/Index/findMoreVod", json.dumps(body))
            result["list"] = self._vod_list(j)
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
