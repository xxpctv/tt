# -*- coding: utf-8 -*-
"""爱上音乐 (IY音乐台 / csp_Bili) 独立 py 源 —— 按原源形态复刻
数据: B站 (分类词即搜索词; 一个合集视频的分P即一首歌)

布局(与原源一致):
  顶排   : 16 个分类标签(不带 IY 字头), 演唱会带排序/歌手/时长三组筛选
  首页   : 音乐区最新投稿 → 「更新推荐」短视频卡
  分类页 : 该词搜索出的合集视频卡(备注=合集总时长)
  详情页 : 点卡给出该视频全部分P + 两条清晰度线路(清晰720P / 流畅360P)
  播放   : mp4 音画合一(durl) 直链, 失败回落 dash 音频
"""

import re
import json
import time
import threading

try:
    import requests as _requests
except Exception:
    _requests = None


# ==================== 搜索关键词本地过滤 ====================
# 规则: 关键词整体匹配(不拆词), 只查 标题/名称/导演/演员/作者 任一字段, 命中即保留;
#       简介(content/desc/intro)只作展示, 绝不参与命中; 条目里没有的字段直接跳过。
_KW_TITLE_KEYS = ("vod_name", "name", "title", "vod_title", "series_name", "series_title")
_KW_DIRECTOR_KEYS = ("vod_director", "director", "directors")
_KW_ACTOR_KEYS = ("vod_actor", "actor", "actors", "vod_actors", "star", "stars", "cast")
_KW_AUTHOR_KEYS = ("vod_author", "author", "author_name", "vod_writer", "writer",
                   "nickname", "singer", "artist", "artists", "uploader")


def _kw_norm(value):
    """统一小写并去掉全部空白, 仅用于子串比较."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        value = " ".join(str(x) for x in value if x)
    return "".join(str(value).split()).lower()


def _kw_hit(item, key):
    """整词命中判断: 只查标题/名称/导演/演员/作者, 简介不参与."""
    kw = _kw_norm(key)
    if not kw or not isinstance(item, dict):
        return True
    pool = []
    for k in _KW_TITLE_KEYS + _KW_DIRECTOR_KEYS + _KW_ACTOR_KEYS + _KW_AUTHOR_KEYS:
        s = _kw_norm(item.get(k))
        if s:
            pool.append(s)
    if not pool:
        return True  # 该条没有可匹配字段 → 忽略, 不误杀
    return any(kw in s for s in pool)


def _kw_filter(items, key):
    """按关键词过滤搜索结果列表."""
    return [it for it in (items or []) if _kw_hit(it, key)]


# ============================ Cookie 配置（改这里就行） ============================
# 优先级: COOKIE_TEXT 非空就用它; 否则去 COOKIE_URL 拉取(内容是纯文本 cookie, 扩展名是 png)
# 原作者 cookie 失效后: 把浏览器里自己的 B站 cookie 整段粘进 COOKIE_TEXT, 或换成自己的 URL
COOKIE_URL = "https://gh-proxy.com/https://raw.githubusercontent.com/IY-CPU/IY/main/lib/blc.png"
COOKIE_TEXT = (
    "SESSDATA=8f3ff69f%2C1794310143%2C53c01%2A52CjBX4vniMP8UbH-FHHxtImWyVMCf_NkAmIFpLXuK3B9TH1uSPOG3A5ST5nKXpP5b06gSVmx2Q2FWY0xPY19yaGxqOUNoRnZuLVhselJhVXU5UWlQb093RnprU2xpLVk5bmpwWjZ6bEhLZWt2RTIwbVpHaFJsYXJVeGtGRnFMcTd1OHRoZ24zN2ZRIIEC; "
    "bili_jct=27dfcc874d1a3c0fe39b9651ca436394; "
    "DedeUserID=3546629682497943; "
    "DedeUserID__ckMd5=b11f007e7707c2a6; "
    "sid=pey664gw; "
    "b_lsid=922FAEA2_19E263F56EF;"
)
# =================================================================================


class Spider:
    _is_vod_source = True      # 纯点播型子源, 供聚合器识别

    # 16 个分类: (搜索词, 显示名) —— 搜索词不变, 显示名与顺序按用户要求排列
    CATS = [
        ("2026年音乐热榜", "2026年热榜"),
        ("抖音热歌", "抖音热歌"),
        ("DJ合集", "车载DJ"),
        ("纯音乐合集", "纯音乐"),
        ("禅修音乐", "禅修音乐"),
        ("MV合集", "MV合集"),
        ("国语歌曲合集", "国语金曲"),
        ("粤语歌曲合集", "粤语金曲"),
        ("英语歌曲合集", "欧美金曲"),
        ("古风歌曲", "古风歌曲"),
        ("演唱会超清", "演唱会"),
        ("日韩歌曲合集", "日韩合集"),
        ("女团现场", "女团现场"),
        ("经典老歌合集", "经典老歌"),
        ("一人一首成名曲", "一人一首"),
        ("国乐合集", "国乐大典"),
    ]

    # 「演唱会筛选」的 3 组筛选(排序 / 分类151位歌手 / 时长) —— 与原源 iyyy.png 云配置逐项一致
    CONC_TID = [
        ("全部", "演唱会超清"),
        ("A阿杜", "阿杜演唱会超清"),
        ("A阿黛尔", "阿黛尔演唱会超清"),
        ("BBeyond", "Beyond演唱会超清"),
        ("BBy2", "By2演唱会超清"),
        ("BBIGBANG", "BIGBANG演唱会超清"),
        ("B布兰妮", "布兰妮演唱会超清"),
        ("B坂井泉水", "坂井泉水演唱会超清"),
        ("C陈奕迅", "陈奕迅演唱会超清"),
        ("C蔡依林", "蔡依林演唱会超清"),
        ("C初音未来", "初音未来演唱会超清"),
        ("C蔡健雅", "蔡健雅演唱会超清"),
        ("C陈小春", "陈小春演唱会超清"),
        ("C草蜢", "草蜢演唱会超清"),
        ("C陈慧娴", "陈慧娴演唱会超清"),
        ("C崔健", "崔健演唱会超清"),
        ("C仓木麻衣", "仓木麻衣演唱会超清"),
        ("D戴荃", "戴荃演唱会超清"),
        ("D动力火车", "动力火车演唱会超清"),
        ("D邓丽君", "邓丽君演唱会超清"),
        ("D丁当", "丁当演唱会超清"),
        ("D刀郎", "刀郎演唱会超清"),
        ("D邓紫棋", "邓紫棋演唱会超清"),
        ("D戴佩妮", "戴佩妮演唱会超清"),
        ("D邓丽君", "邓丽君演唱会超清"),
        ("F飞儿乐队", "飞儿乐队演唱会超清"),
        ("F费玉清", "费玉清演唱会超清"),
        ("F费翔", "费翔演唱会超清"),
        ("F方大同", "方大同演唱会超清"),
        ("F房东的猫", "房东的猫演唱会超清"),
        ("F凤飞飞", "凤飞飞演唱会超清"),
        ("F凤凰传奇", "凤凰传奇演唱会超清"),
        ("G郭采洁", "郭采洁演唱会超清"),
        ("G光良", "光良演唱会超清"),
        ("G郭静", "郭静演唱会超清"),
        ("G郭富城", "郭富城演唱会超清"),
        ("H胡彦斌", "胡彦斌演唱会超清"),
        ("H胡夏", "胡夏演唱会超清"),
        ("H韩红", "韩红演唱会超清"),
        ("H黄品源", "黄品源演唱会超清"),
        ("H黄小琥", "黄小琥演唱会超清"),
        ("H花儿乐队", "花儿乐队演唱会超清"),
        ("H黄家强", "黄家强演唱会超清"),
        ("H后街男孩", "后街男孩演唱会超清"),
        ("J经典老歌", "经典老歌演唱会超清"),
        ("J贾斯丁比伯", "贾斯丁比伯演唱会超清"),
        ("J金池", "金池演唱会超清"),
        ("J金志文", "金志文演唱会超清"),
        ("J焦迈奇", "焦迈奇演唱会超清"),
        ("K筷子兄弟", "筷子兄弟演唱会超清"),
        ("L李玟", "李玟演唱会超清"),
        ("L林忆莲", "林忆莲演唱会超清"),
        ("L李克勤", "李克勤演唱会超清"),
        ("L刘宪华", "刘宪华演唱会超清"),
        ("L李圣杰", "李圣杰演唱会超清"),
        ("L林宥嘉", "林宥嘉演唱会超清"),
        ("L梁静茹", "梁静茹演唱会超清"),
        ("L李健", "李健演唱会超清"),
        ("L林俊杰", "林俊杰演唱会超清"),
        ("L李玉刚", "李玉刚演唱会超清"),
        ("L林志炫", "林志炫演唱会超清"),
        ("L李荣浩", "李荣浩演唱会超清"),
        ("L李宇春", "李宇春演唱会超清"),
        ("L洛天依", "洛天依演唱会超清"),
        ("L林子祥", "林子祥演唱会超清"),
        ("L李宗盛", "李宗盛演唱会超清"),
        ("L黎明", "黎明演唱会超清"),
        ("L刘德华", "刘德华演唱会超清"),
        ("L罗大佑", "罗大佑演唱会超清"),
        ("L林肯公园", "林肯公园演唱会超清"),
        ("LLadyGaga", "LadyGaga演唱会超清"),
        ("L旅行团乐队", "旅行团乐队演唱会超清"),
        ("M莫文蔚", "莫文蔚演唱会超清"),
        ("M毛不易", "毛不易演唱会超清"),
        ("M梅艳芳", "梅艳芳演唱会超清"),
        ("M迈克尔杰克逊", "迈克尔杰克逊演唱会超清"),
        ("N南拳妈妈", "南拳妈妈演唱会超清"),
        ("P朴树", "朴树演唱会超清"),
        ("Q齐秦", "齐秦演唱会超清"),
        ("Q青鸟飞鱼", "青鸟飞鱼演唱会超清"),
        ("R容祖儿", "容祖儿演唱会超清"),
        ("R任贤齐", "任贤齐演唱会超清"),
        ("S水木年华", "水木年华演唱会超清"),
        ("S孙燕姿", "孙燕姿演唱会超清"),
        ("S苏打绿", "苏打绿演唱会超清"),
        ("SSHE", "SHE演唱会超清"),
        ("S孙楠", "孙楠演唱会超清"),
        ("T陶喆", "陶喆演唱会超清"),
        ("T谭咏麟", "谭咏麟演唱会超清"),
        ("T田馥甄", "田馥甄演唱会超清"),
        ("T谭维维", "谭维维演唱会超清"),
        ("T逃跑计划", "逃跑计划演唱会超清"),
        ("T田震", "田震演唱会超清"),
        ("T谭晶", "谭晶演唱会超清"),
        ("T屠洪刚", "屠洪刚演唱会超清"),
        ("T泰勒·斯威夫特", "泰勒·斯威夫特演唱会超清"),
        ("W王力宏", "王力宏演唱会超清"),
        ("W王杰", "王杰演唱会超清"),
        ("W吴克群", "吴克群演唱会超清"),
        ("W王心凌", "王心凌演唱会超清"),
        ("W王靖雯", "好声音王靖雯演唱会超清"),
        ("W汪峰", "汪峰演唱会超清"),
        ("W伍佰", "伍佰演唱会超清"),
        ("W王菲", "王菲演唱会超清"),
        ("W五月天", "五月天演唱会超清"),
        ("W汪苏泷", "汪苏泷演唱会超清"),
        ("X徐佳莹", "徐佳莹演唱会超清"),
        ("X弦子", "弦子演唱会超清"),
        ("X萧亚轩", "萧亚轩演唱会超清"),
        ("X许巍", "许巍演唱会超清"),
        ("X薛之谦", "薛之谦演唱会超清"),
        ("X许嵩", "许嵩演唱会超清"),
        ("X小虎队", "小虎队演唱会超清"),
        ("X萧敬腾", "萧敬腾演唱会超清"),
        ("X谢霆锋", "谢霆锋演唱会超清"),
        ("X徐小凤", "徐小凤演唱会超清"),
        ("X信乐队", "信乐队演唱会超清"),
        ("Y夜愿乐队", "夜愿乐队演唱会超清"),
        ("Y羽泉", "羽泉演唱会超清"),
        ("Y郁可唯", "郁可唯演唱会超清"),
        ("Y叶倩文", "叶倩文演唱会超清"),
        ("Y杨坤", "杨坤演唱会超清"),
        ("Y庾澄庆", "庾澄庆演唱会超清"),
        ("Y尤长靖", "尤长靖演唱会超清"),
        ("Y易烊千玺", "易烊千玺演唱会超清"),
        ("Y袁娅维", "袁娅维演唱会超清"),
        ("Y杨丞琳", "杨丞琳演唱会超清"),
        ("Y杨千嬅", "杨千嬅演唱会超清"),
        ("Y杨宗纬", "杨宗纬演唱会超清"),
        ("Z郑秀文", "郑秀文演唱会超清"),
        ("Z周杰伦", "周杰伦演唱会超清"),
        ("Z张学友", "张学友演唱会超清"),
        ("Z张信哲", "张信哲演唱会超清"),
        ("Z张宇", "张宇演唱会超清"),
        ("Z周华健", "周华健演唱会超清"),
        ("Z张韶涵", "张韶涵演唱会超清"),
        ("Z周深", "周深演唱会超清"),
        ("Z纵贯线", "纵贯线演唱会超清"),
        ("Z赵雷", "赵雷演唱会超清"),
        ("Z周传雄", "周传雄演唱会超清"),
        ("Z张国荣", "张国荣演唱会超清"),
        ("Z周慧敏", "周慧敏演唱会超清"),
        ("Z张惠妹", "张惠妹演唱会超清"),
        ("Z周笔畅", "周笔畅演唱会超清"),
        ("Z郑中基", "郑中基演唱会超清"),
        ("Z张艺兴", "张艺兴演唱会超清"),
        ("Z张震岳", "张震岳演唱会超清"),
        ("Z张雨生", "张雨生演唱会超清"),
        ("Z郑智化", "郑智化演唱会超清"),
        ("Z卓依婷", "卓依婷演唱会超清"),
        ("Z中岛美雪", "中岛美雪演唱会超清"),
    ]
    CONC_DUR = [("全部", "0"), ("60分钟以上", "4"), ("30~60分钟", "3"), ("10~30分钟", "2"), ("10分钟以下", "1")]
    FILTERS = {
        "演唱会超清": [
            {"key": "order", "name": "排序", "value": [
                {"n": "综合排序", "v": "0"},
                {"n": "最多点击", "v": "click"},
                {"n": "最新发布", "v": "pubdate"},
                {"n": "最多弹幕", "v": "dm"},
                {"n": "最多收藏", "v": "stow"},
            ]},
            {"key": "tid", "name": "分类", "value": [{"n": n, "v": v} for n, v in CONC_TID]},
            {"key": "duration", "name": "时长", "value": [{"n": n, "v": v} for n, v in CONC_DUR]},
        ],
    }
    # 播放线路: (线路名, B站 qn) —— mp4 音画合一, 64=720P 16=360P
    LINES = [("清晰720P", 64), ("流畅360P", 16)]
    FALLBACK_QN = (64, 32, 16)

    PAGE_SIZE = 20
    AREA_RID = 3               # B站 音乐区

    def __init__(self):
        self.site = "https://www.bilibili.com"
        self.name = "爱上音乐"
        # mp4(durl) 直链只认桌面 UA, 移动 UA 会 403 —— 全局统一桌面 Chrome
        self.header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        self.s = self.session = self.sess = _requests.Session() if _requests else None
        self._defpic = "https://www.bilibili.com/favicon.ico"
        self._cookie = {}
        self._ck_lock = threading.Lock()
        self._cookie_url = COOKIE_URL

    # ---------------- 基础 ----------------

    def getName(self):
        return self.name

    def init(self, extend=""):
        """extend 可传 {"cookie": "https://.../blc.png"}; 不传则用头部常量"""
        txt = ""
        try:
            if isinstance(extend, dict):
                txt = extend.get("cookie") or ""
            elif extend:
                s = str(extend)
                try:
                    j = json.loads(s)
                    txt = (j.get("cookie") or "") if isinstance(j, dict) else ""
                except Exception:
                    txt = ""
        except Exception:
            txt = ""
        if txt and str(txt).startswith("http"):
            self._cookie_url = str(txt).strip()

    def getDependence(self):
        return []

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        if not url:
            return False
        u = str(url).lower()
        return u.endswith((".m3u8", ".mp4", ".m4s", ".flv", ".mkv", ".mp3", ".m4a")) or "m3u8" in u

    def destroy(self):
        pass

    def action(self, action):
        return {}

    # ---------------- Cookie / 请求 ----------------

    def _parse_cookie(self, txt):
        """'SESSDATA=..; bili_jct=..' 或 {"buvid3": ".."} 都吃"""
        txt = (txt or "").strip()
        if not txt:
            return
        try:
            j = json.loads(txt)
            if isinstance(j, dict):
                for k, v in j.items():
                    if isinstance(v, str):
                        self._cookie[str(k)] = v
                return
        except Exception:
            pass
        for seg in re.split(r"[;\n\r]+", txt):
            if "=" in seg:
                k, v = seg.split("=", 1)
                k = k.strip().replace("Cookie:", "").replace("cookie:", "")
                if k and v.strip():
                    self._cookie[k] = v.strip()

    def _ensure_cookie(self):
        if self._cookie.get("buvid3") or self._cookie.get("SESSDATA"):
            if self._cookie.get("buvid3"):
                return True
        with self._ck_lock:
            if self._cookie.get("buvid3"):
                return True
            # 1) 头部硬编码 cookie(优先), 否则按 URL 拉一次
            if not self._cookie.get("SESSDATA"):
                if COOKIE_TEXT.strip():
                    self._parse_cookie(COOKIE_TEXT)
                elif self._cookie_url:
                    u, self._cookie_url = self._cookie_url, ""
                    try:
                        self._parse_cookie(self._get(u, referer="https://www.bilibili.com/",
                                                    quiet=True) or "")
                    except Exception:
                        pass
            # 2) 补 buvid(过 412 风控必需)
            if not self._cookie.get("buvid3"):
                try:
                    j = json.loads(self._get("https://api.bilibili.com/x/frontend/finger/spi",
                                             referer="https://www.bilibili.com/", quiet=True) or "{}")
                    d = j.get("data") or {}
                    if d.get("b_3"):
                        self._cookie["buvid3"] = d["b_3"]
                    if d.get("b_4"):
                        self._cookie["buvid4"] = d["b_4"]
                    if d.get("b_3"):
                        self._cookie.setdefault("buvid_fp", "0")
                        self._cookie.setdefault("b_nut", str(int(time.time())))
                except Exception:
                    pass
            return bool(self._cookie.get("buvid3") or self._cookie.get("SESSDATA"))

    def _headers(self, referer=None, with_cookie=True):
        h = dict(self.header)
        if referer:
            h["Referer"] = referer
        if with_cookie:
            self._ensure_cookie()
            if self._cookie:
                h["Cookie"] = "; ".join("%s=%s" % (k, v) for k, v in self._cookie.items())
        return h

    def _get(self, url, referer=None, timeout=8, quiet=False):
        h = self._headers(referer, with_cookie=not quiet)
        for attempt in range(2):
            txt = ""
            try:
                if self.s is not None:
                    r = self.s.get(url, headers=h, timeout=timeout, allow_redirects=True)
                    txt = r.text if r.status_code < 400 else ""
                else:
                    import urllib.request
                    req = urllib.request.Request(url, headers=h)
                    with urllib.request.urlopen(req, timeout=timeout) as resp:
                        txt = resp.read().decode("utf-8", "ignore")
            except Exception:
                txt = ""
            if txt:
                return txt
            if attempt == 0:
                with self._ck_lock:
                    self._cookie.pop("buvid3", None)
                time.sleep(0.5)
                h = self._headers(referer, with_cookie=not quiet)
        return ""

    def _getj(self, url, referer=None, timeout=8):
        try:
            return json.loads(self._get(url, referer=referer, timeout=timeout) or "")
        except Exception:
            return {}

    # ---------------- 工具 ----------------

    def _clean(self, s):
        if not s:
            return ""
        s = re.sub(r"<[^>]+>", "", str(s))
        try:
            import html as _html
            s = _html.unescape(s)
        except Exception:
            s = (s.replace("&amp;", "&").replace("&quot;", '"').replace("&lt;", "<")
                  .replace("&gt;", ">").replace("&#x27;", "'").replace("&#39;", "'"))
        s = s.replace("\xa0", " ").replace("\n", " ").strip()
        return s

    def _safe_name(self, s):
        s = self._clean(s).replace("$", "").replace("#", "").replace("|", "").strip()
        return s or "歌曲"

    def _u(self, u):
        if not u:
            return ""
        u = str(u).strip()
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http"):
            return u
        return "https://" + u.lstrip("/")

    def _dur_mins(self, dur):
        """'667:37' / 秒数 → '667分钟'"""
        if not dur:
            return ""
        if isinstance(dur, (int, float)):
            m = int(dur / 60)
            return ("%d分钟" % m) if m else ""
        try:
            parts = [int(x) for x in str(dur).split(":")]
        except Exception:
            return ""
        if len(parts) == 2:
            m = parts[0]
        elif len(parts) == 3:
            m = parts[0] * 60 + parts[1]
        else:
            return ""
        return ("%d分钟" % m) if m else ""

    def _item(self, v):
        return {
            "vod_id": "bv:" + v["bvid"],
            "vod_name": v["title"][:40] or v["bvid"],
            "vod_pic": v["pic"] or self._defpic,
            "vod_remarks": self._dur_mins(v["dur"]),
            # UP主/作者: 仅参与搜索关键词命中, 不在列表卡上显示
            "vod_actor": self._clean(v.get("author") or ""),
        }

    # ---------------- B站接口 ----------------

    def _search(self, kw, pg=1, order="totalrank", duration=""):
        try:
            from urllib.parse import quote
        except Exception:
            return []
        url = ("https://api.bilibili.com/x/web-interface/search/type?search_type=video"
               "&keyword=%s&page=%s&page_size=%d&order=%s"
               % (quote(str(kw)), pg, self.PAGE_SIZE, order or "totalrank"))
        d0 = str(duration or "").strip()
        if d0 and d0 not in ("0", "全部") and d0.isdigit():
            url += "&duration=" + d0
        d = self._getj(url, referer="https://search.bilibili.com/")
        arr = ((d.get("data") or {}).get("result")) or []
        out = []
        for it in arr:
            bv = str(it.get("bvid") or "")
            if not bv:
                continue
            out.append({
                "bvid": bv,
                "title": self._clean(it.get("title")),
                "pic": self._u(it.get("pic")),
                "dur": it.get("duration") or "",
                "play": it.get("play") or 0,
                "author": self._clean(it.get("author") or it.get("up_name") or ""),
            })
        return out

    def _region(self, rid=None, ps=20, pg=1):
        """音乐区最新投稿 → 首页「更新推荐」"""
        d = self._getj("https://api.bilibili.com/x/web-interface/dynamic/region?rid=%s&ps=%s&pn=%s"
                       % (rid or self.AREA_RID, ps, pg),
                       referer="https://www.bilibili.com/")
        arr = ((d.get("data") or {}).get("archives")) or []
        out = []
        for it in arr:
            bv = str(it.get("bvid") or "")
            if not bv:
                continue
            out.append({
                "bvid": bv,
                "title": self._clean(it.get("title")),
                "pic": self._u(it.get("pic")),
                "dur": it.get("duration") or 0,
                "play": ((it.get("stat") or {}).get("view")) or 0,
            })
        return out

    def _view(self, bvid):
        d = self._getj("https://api.bilibili.com/x/web-interface/view?bvid=%s" % bvid,
                       referer="https://www.bilibili.com/video/%s" % bvid)
        v = d.get("data") or {}
        pages = []
        for p in (v.get("pages") or []):
            cid = p.get("cid")
            if cid:
                pages.append({
                    "cid": str(cid),
                    "part": self._clean(p.get("part") or ""),
                    "dur": p.get("duration") or 0,
                })
        return {
            "title": self._clean(v.get("title") or ""),
            "pic": self._u(v.get("pic") or ""),
            "desc": self._clean(v.get("desc") or ""),
            "pages": pages,
        }

    def _playurl(self, bvid, cid, qn=64, want="mp4"):
        """want=mp4 → durl 音画合一; want=audio → dash 最高码率(回落 durl)"""
        fnval = 1 if want == "mp4" else 16
        url = ("https://api.bilibili.com/x/player/playurl?bvid=%s&cid=%s&qn=%s"
               "&fnval=%s&fnver=0&fourk=1" % (bvid, cid, qn, fnval))
        d = self._getj(url, referer="https://www.bilibili.com/video/%s" % bvid, timeout=10)
        data = d.get("data") or {}
        du = data.get("durl") or []
        if want == "mp4":
            return (du[0].get("url") or "") if du else ""
        best, bw = "", -1
        for a in (((data.get("dash") or {}).get("audio")) or []):
            u = a.get("baseUrl") or a.get("base_url") or ""
            if u and (a.get("bandwidth") or 0) > bw:
                bw = a.get("bandwidth") or 0
                best = u
        if best:
            return best
        return (du[0].get("url") or "") if du else ""

    def _stream(self, bvid, cid, qn=64):
        """取播放直链: 先 mp4(当前档→逐档回落), 再回落 dash 音频"""
        for q in [qn] + [x for x in self.FALLBACK_QN if x != qn]:
            for _ in range(2):
                try:
                    u = self._playurl(bvid, cid, q, "mp4")
                except Exception:
                    u = ""
                if u:
                    return u
                time.sleep(0.2)
        try:
            return self._playurl(bvid, cid, 80, "audio")
        except Exception:
            return ""

    # ---------------- 契约 ----------------

    def homeContent(self, filter=None):
        cls = [{"type_id": kw, "type_name": name} for kw, name in self.CATS]
        return {"class": cls, "filters": self.FILTERS, "list": []}

    def homeVideoContent(self):
        try:
            items = self._region(self.AREA_RID, 20)
        except Exception:
            items = []
        if not items:
            try:
                items = self._search("音乐现场", 1, "pubdate")
            except Exception:
                items = []
        return {"list": [self._item(v) for v in items[:20]]}

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        try:
            pg = max(1, int(pg))
        except Exception:
            pg = 1

        def _pick(d, k):
            if isinstance(d, dict):
                v = d.get(k)
                if isinstance(v, list):
                    return v[0] if v else ""
                if v:
                    return v
            return ""

        order = _pick(filter, "order") or _pick(extend, "order") or "totalrank"
        if isinstance(filter, str) and filter:
            order = filter
        # 演唱会筛选: tid(歌手二级分类) 直接当搜索词, duration 透传给 B站
        kw = _pick(filter, "tid") or _pick(extend, "tid") or ""
        dur = _pick(filter, "duration") or _pick(extend, "duration") or ""
        kw = str(kw or tid).strip() or str(tid)
        if order in ("0", "全部", "totalrank", ""):
            order = "totalrank"
        try:
            res = self._search(kw, pg, order, dur)
        except Exception:
            res = []
        return {"list": [self._item(v) for v in res],
                "page": pg, "pagecount": pg + 1, "limit": self.PAGE_SIZE, "total": 100}

    def detailContent(self, ids):
        """点卡 → 全部分P, 每条给「清晰720P / 流畅360P」两条线路"""
        vid = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        vid = str(vid or "").strip()
        bvid = vid[3:] if vid.startswith("bv:") else ""
        if not bvid and vid.startswith("bplay:"):
            bvid = (vid.split(":") + ["", ""])[1]
        if not bvid:
            return {"list": []}
        info = self._view(bvid)
        pages = info.get("pages") or []
        if not pages:
            return {"list": [{
                "vod_id": "bv:" + bvid,
                "vod_name": info.get("title") or bvid,
                "vod_pic": info.get("pic") or self._defpic,
                "vod_content": (info.get("desc") or "")[:400],
                "vod_play_from": self.name,
                "vod_play_url": "",
            }], "parse": 0, "jx": 0}
        grp, flags = [], []
        for lname, q in self.LINES:
            eps = []
            for i, p in enumerate(pages):
                # 分P 原名直接用(它自带 001. 这类编号), 不再加自造序号
                nm = p["part"] or ("P%d" % (i + 1))
                eps.append("%s$bplay:%s:%s:%d" % (self._safe_name(nm), bvid, p["cid"], q))
            grp.append("#".join(eps))
            flags.append(lname)
        return {"list": [{
            "vod_id": "bv:" + bvid,
            "vod_name": info.get("title") or bvid,
            "vod_pic": info.get("pic") or self._defpic,
            "vod_class": "音乐",
            "vod_remarks": "%d首" % len(pages),
            "vod_content": (info.get("desc") or "")[:400],
            "vod_play_from": "$$$".join(flags),
            "vod_play_url": "$$$".join(grp),
        }], "parse": 0, "jx": 0}

    def playerContent(self, flag, ids, vipFlags=None):
        vid = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        vid = str(vid or "").strip()
        bvid, cid, qn = "", "", 64
        if vid.startswith("bplay:"):
            parts = vid.split(":")
            bvid = parts[1] if len(parts) > 1 else ""
            cid = parts[2] if len(parts) > 2 else ""
            if len(parts) > 3 and str(parts[3]).isdigit():
                qn = int(parts[3])
        url = self._stream(bvid, cid, qn) if (bvid and cid) else ""
        return {"parse": 0, "jx": 0, "url": url,
                "header": {"User-Agent": self.header["User-Agent"],
                           "Referer": "https://www.bilibili.com/video/%s" % (bvid or "")}}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            p = int(pg)
        except Exception:
            p = 1
        try:
            res = self._search(str(key), p)
        except Exception:
            res = []
        # 服务端会拆词、也会搜简介, 这里按整词在标题/UP主(作者)上二次过滤
        vods = _kw_filter([self._item(v) for v in res], key)
        return {"list": vods}

    def localProxy(self, param):
        u = param.get("url", "") if isinstance(param, dict) else ""
        if not u:
            return [403, "text/plain", b"", None]
        if self.s is not None:
            try:
                r = self.s.get(u, headers=self.header, timeout=15)
                return [200, r.headers.get("Content-Type", "application/octet-stream"), r.content, None]
            except Exception:
                pass
        return [403, "text/plain", b"", None]
