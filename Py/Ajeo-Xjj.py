# -*- coding: utf-8 -*-
"""Ajeo-Xjj 小姐姐（csp_Xjj）独立版
协议依据 aidaox/feimao jar 原版 com.github.catvod.spider.Xjj 全链路复现：
- 配置源：https://jk.catvod.site/jk/xjj/mm-api.enc（base64 + AES-CBC key=aidaoxXjjKey16!! iv=aidaoxXjjIv___16 → JSON apis，2026-07-13 版本已解密固化，运行期无需 AES）
- 分类：单分类 videos(我爱刷)；列表 = apis 入口卡片（原版从 index 1 遍历、黑名单 2 个跳过、nrzj http->https）+ 追加 海外(需梯)、其他随机
- 播放：detailContent 现场解析 api -> 真实视频 URL（302 Location 跟随 / JSON video_url|url / http 提取 / diskgirl 原样），无壳代理依赖
- 搜索：原版无 searchContent，返回空
"""
import io
import io
import json
import ssl
import sys
import urllib.error
import urllib.request
import urllib.error

UA = 'Mozilla/5.0 (Linux; Android 12; Mobile) AppleWebKit/537.36'
PIC = 'https://upload.xchina.io/series/63824a975d8ae.jpg'
PIC_HT = 'https://imgessl.kugou.com/stdmusic/20220929/20220929121204711562.jpg'

# 原版 b() 黑名单（Xjj.a 静态数组，跳过不展示）
BLACKLIST = [
    'https://api.dwo.cc/api/ksvideo',
    'https://api.cenguigui.cn/api/mp4/MP4_xiaojiejie.php',
]

# 已解密配置（mm-api.enc -> AES-CBC，version=1, updated=2026-07-13, source=hsya.top/static/js/mm-api.js）
API_LIST = [
    {"apiTitle": "高质量纯妹", "api": "http://api.yujn.cn/api/zzxjj.php?type=video", "type": "link", "data": ""},
    {"apiTitle": "黑丝", "api": "https://api.yujn.cn/api/heisis.php?type=video", "type": "link", "data": ""},
    {"apiTitle": "抖音萌妹", "api": "https://api.yujn.cn/api/nvda.php?type=video", "type": "link", "data": ""},
    {"apiTitle": "清纯萝莉", "api": "http://api.yujn.cn/api/zzxjj.php?temps=", "type": "random", "data": ""},
    {"apiTitle": "快手扭一扭", "api": "http://v.nrzj.vip/video.php?_t=", "type": "random", "data": ""},
    {"apiTitle": "妹纸", "api": "http://v.nrzj.vip/video.php", "type": "link", "data": ""},
    {"apiTitle": "清纯", "api": "http://api.yujn.cn/api/zzxjj.php?type=video", "type": "link", "data": ""},
    {"apiTitle": "甜妹", "api": "http://api.yujn.cn/api/xjj.php?type=video", "type": "link", "data": ""},
    {"apiTitle": "快手女大学生", "api": "https://api.yujn.cn/api/nvda.php?type=video", "type": "link", "data": ""},
    {"apiTitle": "黑丝系列", "api": "http://api.yujn.cn/api/heisis.php?type=video", "type": "link", "data": ""},
    {"apiTitle": "慢摇系列", "api": "http://api.yujn.cn/api/manyao.php?type=video", "type": "link", "data": ""},
    {"apiTitle": "吊带系列", "api": "http://api.yujn.cn/api/diaodai.php?type=video", "type": "link", "data": ""},
    {"apiTitle": "清纯系列", "api": "http://api.yujn.cn/api/qingchun.php?type=video", "type": "link", "data": ""},
    {"apiTitle": "女高系列", "api": "http://api.yujn.cn/api/nvgao.php?type=video", "type": "link", "data": ""},
    {"apiTitle": "快手变装系列", "api": "http://api.yujn.cn/api/ksbianzhuang.php?type=video", "type": "link", "data": ""},
    {"apiTitle": "甜妹系列", "api": "http://api.yujn.cn/api/tianmei.php?type=video", "type": "link", "data": ""},
    {"apiTitle": "欲梦视频", "api": "http://api.yujn.cn/api/ndym.php?type=video", "type": "link", "data": ""},
    {"apiTitle": "热舞视频", "api": "http://api.yujn.cn/api/rewu.php?type=video", "type": "link", "data": ""},
    {"apiTitle": "小姐姐视频", "api": "http://api.yujn.cn/api/ksxjjsp.php", "type": "link", "data": ""},
    {"apiTitle": "小姐姐", "api": "https://api.cenguigui.cn/api/mp4/MP4_xiaojiejie.php", "type": "link", "data": ""},
    {"apiTitle": "高质量", "api": "https://api.lolimi.cn/API/xjj/xjj.php", "type": "link", "data": ""},
    {"apiTitle": "随机小姐姐", "api": "https://v2.xxapi.cn/api/meinv", "type": "data", "data": "data"},
    {"apiTitle": "小姐姐", "api": "https://api.dwo.cc/api/ksvideo", "type": "link", "data": ""},
]

# 追加卡片（原版 b() 末尾 add(0)）
EXTRA = [
    ("海外(需梯)", "https://diskgirl.com/get/get1.php", PIC_HT),
    ("其他随机", "https://av.npcq.cn/api.php?action=next_video", PIC),
]

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def _g(s):
    """Wd.g 等价：https:// -> http://（对齐原版）"""
    if not s:
        return ''
    if s.startswith('https://'):
        return 'http://' + s[len('https://'):]
    return s


def _get(url, follow=False, timeout=15):
    """不跟随重定向 GET，返回 (status, headers, body, final_url)；失败返回 (0, {}, '', url)"""
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Cache-Control': 'no-cache'})

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read().decode('utf-8', 'ignore'), r.geturl()
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode('utf-8', 'ignore') if e.fp else ''
        except Exception:
            body = ''
        return e.code, dict(e.headers), body, url
    except Exception:
        return 0, {}, '', url


def _c(url, follow=True):
    """Wd.c 等价：GET -> 302 Location / JSON video_url|url / http 提取 / diskgirl 原样"""
    st, hdrs, body, _ = _get(url, follow=False)
    if st in (301, 302, 307, 308):
        loc = hdrs.get('Location') or ''
        loc = _g(loc.strip())
        if not loc:
            return ''
        if '.php' in loc and follow:
            return _c(loc, True)
        if loc.startswith('http') and '.php' not in loc:
            return loc
        return ''
    if st == 200:
        b = body.strip()
        if b.startswith('{'):
            try:
                j = json.loads(b)
                v = j.get('video_url') or j.get('url') or ''
                return _g(v)
            except Exception:
                pass
        if 'diskgirl' in url:
            return _g(b)
        if b.startswith('http'):
            return _g(b)
        if 'http' in b:
            i = b.index('http')
            v = b[i:].strip()
            nl = v.find('\n')
            if nl > 0:
                v = v[:nl]
            return _g(v)
        return url
    return ''


def _resolve(url):
    """Wd.k + Wd.d 等价：解析 api -> 真实视频 URL"""
    if url == 'https://v2.xxapi.cn/api/meinv':
        return url
    if 'av.npcq.cn' in url and 'format=json' not in url:
        url += ('&' if '?' in url else '?') + 'format=json'
    return _c(url, True)


class Spider:
    _headers = {'User-Agent': UA}
    _proxy = True

    def init(self, context, ext):
        # ext: {proxy:true, socks5:""} —— py 直连，proxy 概念内联
        try:
            self._proxy = bool(ext.get('proxy', True))
        except Exception:
            pass

    def homeContent(self, filterable=False):
        return json.dumps({'class': [{'type_id': 'videos', 'type_name': '我爱刷'}]}, ensure_ascii=False)

    def categoryContent(self, tid, pg, filterable=False, extend=None):
        try:
            vods = []
            # 原版 b()：从 index 1 遍历，黑名单跳过，nrzj http->https
            for it in API_LIST[1:]:
                api = (it or {}).get('api') or ''
                title = (it or {}).get('apiTitle') or '随机'
                if not api:
                    continue
                if api in BLACKLIST:
                    continue
                api = api.replace('http://v.nrzj.vip/', 'https://v.nrzj.vip/')
                vods.append({'vod_id': api, 'vod_name': title, 'vod_pic': PIC, 'vod_remarks': ''})
            # 追加：海外(需梯)、其他随机 插最前（对齐 add(0) 顺序）
            for title, api, pic in reversed(EXTRA):
                vods.insert(0, {'vod_id': api, 'vod_name': title, 'vod_pic': pic, 'vod_remarks': ''})
            return json.dumps({'page': 1, 'pagecount': 1, 'limit': len(vods), 'total': len(vods), 'list': vods},
                              ensure_ascii=False)
        except Exception:
            return json.dumps({'page': 1, 'pagecount': 1, 'limit': 0, 'total': 0, 'list': []}, ensure_ascii=False)

    def detailContent(self, ids):
        try:
            api = str(ids[0])
            name = api
            for it in API_LIST:
                if (it or {}).get('api') == api:
                    name = (it or {}).get('apiTitle') or name
                    break
            if api == 'https://av.npcq.cn/api.php?action=next_video':
                name = '其他随机'
            elif api == 'https://diskgirl.com/get/get1.php':
                name = '海外(需梯)'
            real = _resolve(api)
            if not real:
                real = api  # 兜底直连（302 型接口播放器仍可处理）
            vod = {'vod_id': api, 'vod_name': name, 'vod_pic': PIC,
                   'vod_play_from': '小姐姐', 'vod_play_url': real}
            return json.dumps({'list': [vod]}, ensure_ascii=False)
        except Exception:
            return json.dumps({'list': []}, ensure_ascii=False)

    def playerContent(self, flag, id, vipFlags):
        u = str(id)
        if u.startswith('http://') or u.startswith('https://'):
            return json.dumps({'parse': 0, 'playUrl': u}, ensure_ascii=False)
        return json.dumps({'parse': 0, 'playUrl': u}, ensure_ascii=False)

    def searchContent(self, key, quick=False, pg=1):
        # 原版 Xjj 无 searchContent（无内容索引），返回空
        return json.dumps({'page': 1, 'pagecount': 1, 'limit': 20, 'total': 0, 'list': []}, ensure_ascii=False)


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sp = Spider()
    sp.init(None, {'proxy': True, 'socks5': ''})
    home = json.loads(sp.homeContent())
    print('home:', home['class'])
    cat = json.loads(sp.categoryContent('videos', 1))
    print('category 卡片数:', len(cat['list']))
    for v in cat['list'][:6]:
        print('  ', v['vod_name'], '|', v['vod_id'][:60])
    for v in cat['list'][-3:]:
        print('  ', v['vod_name'], '|', v['vod_id'][:60])
    print('--- 解析测试 ---')
    for v in cat['list'][:5] + cat['list'][-2:]:
        real = _resolve(v['vod_id'])
        print('解析', v['vod_name'], '->', real[:90] if real else '(空)')
