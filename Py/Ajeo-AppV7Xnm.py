# -*- coding: utf-8 -*-
"""
AppV7 线路⑤（AppV7Xnm）独立版
协议：http://198.16.32.138:12345/nxnm.php /v7/logs 全链路（nav / video_list / rank_video_list /
      video_detail / secret_parse_api_url），frida 直调 init 实取凭据 + 本机回放验证。
加密：logEn = b64url( urandom16 + AES128CBC( key=MD5(buildTime + '^~!@#[-' + pkg)[:16],
      iv=urandom16, PKCS7(json) ) )；请求头固定 build-time / pk-id / version 等。
响应：nav/列表/排行明文 JSON；video_detail 为加密流（提示流 b64 + 密文），按 pos/v2/ivo 三重扫描解密。
播放：该线路所有源（lzm3u8/rym3u8/dyttm3u8/bfzym3u8/1080zyk/jsm3u8）为直链 m3u8，
      parse=0 直链播放；异常源尝试服务器 secret_parse_api_url 解析，失败提示切换线路。
兼容：OK影视 / 影视仓（TVBox Python 引擎）
"""
import json
import os
import re
import time
import base64
import urllib.request

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider:
        pass

try:
    from Crypto.Cipher import AES
    _HAVE_AES = True
except Exception:
    _HAVE_AES = False

_BUILD_TIME = '1776948802285'
_PKG = 'com.jinrisyxj.measure.xnmc'
_BASE = 'http://198.16.32.138:12345/nxnm.php'
_PREFIX = '/v7/'
_SIGN_MD5 = '920e81f0303b6079cb3a94d1f390bb97'
_APK_LEN = 53872826
_APK_PATH = ('/data/app/~~WIc7MtfakyvWJtXcdZnPEe==/'
             'com.jinrisyxj.measure.xnmc-iVDeKbxrylKTFJ8bxJEWPZ==/base.apk')
# 服务器池（frida init 第二次 extDe 返回），主 host 不通时自动切换
_HOSTS = ['http://198.16.32.138:12345/nxnm.php',
          'http://162.209.166.60:12345/nxnm.php']
_HEADERS = {
    'User-Agent': 'Dart/3.11 (dart:io)',
    'build-time': _BUILD_TIME,
    'pk-id': _PKG,
    'version': '2.0.9',
    'version-number': '109',
    'platform': 'android',
    'platform-version': 'TP1A.220624.014',
    'Content-Type': 'text/plain',
}


def _md5(b):
    import hashlib
    return hashlib.md5(b).digest()


def _key():
    return _md5(_BUILD_TIME.encode() + b'^~!@#[-' + _PKG.encode())[:16]


def _b64u(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def _b64d(x):
    x = x.replace('-', '+').replace('_', '/')
    x = ''.join(ch for ch in x if ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')
    x = x.rstrip('=')
    pad = (4 - len(x) % 4) % 4
    return base64.b64decode(x + '=' * pad)


def _enc_req(method, data):
    iv = os.urandom(16)
    plain = json.dumps({'method': method, 'data': data, 'csrf': int(time.time() * 1000)},
                       separators=(',', ':')).encode()
    pad = 16 - len(plain) % 16
    plain += bytes([pad]) * pad
    ct = AES.new(_key(), AES.MODE_CBC, iv).encrypt(plain)
    return _b64u(iv + ct)


def _post(method, data):
    body = _enc_req(method, data)
    last = ''
    for host in _HOSTS:
        try:
            req = urllib.request.Request(host + _PREFIX + 'logs', data=body.encode(), headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception as e:
            last = str(e)
    return 'ERR:' + last


def _try_dec(cip):
    key = _key()
    L = len(cip)
    for pos in range(0, min(400, L)):
        c = cip[pos:]
        for v2 in range(0, 25):
            n = len(c) - v2
            if n < 0x22:
                continue
            if not (((n - 0x11) % 16 == 0) or ((n - 0x10) % 16 == 0) or (n % 16 == 0)):
                continue
            for ivo in range(0, 33):
                if ivo + 16 > n:
                    break
                iv = c[ivo:ivo + 16]
                ct = c[ivo + 16:n]
                nct = (len(ct) // 16) * 16
                if nct < 16:
                    continue
                try:
                    p = AES.new(key, AES.MODE_CBC, iv).decrypt(ct[:nct])
                except Exception:
                    continue
                if b'{' not in p[:60]:
                    continue
                if b'"' in p[:200] and (b'url' in p[:1000] or b'vod' in p[:1000] or b'msg' in p[:300]):
                    return p
    return None


def _dec_resp(text):
    s = (text or '').strip()
    if not s:
        return ''
    if s.startswith('{'):
        return s
    if s.startswith('ERR:'):
        return ''
    m = re.search(r'(eGRkYXBwc2VjcmV0a2V5[A-Za-z0-9+/=]+)$', s)
    p1 = s[:m.start()] if m else s
    eq = p1.find('=')
    if eq >= 0:
        k = eq
        while k < len(p1) and p1[k] == '=':
            k += 1
        try:
            cip = _b64d(p1[k:])
        except Exception:
            return ''
    else:
        try:
            cip = _b64d(p1)
        except Exception:
            return ''
    p = _try_dec(cip)
    if p:
        return p.decode('utf-8', 'replace')
    return ''


def _loads(text):
    try:
        return json.loads(text)
    except Exception:
        return {}


def _pick(obj, *keys):
    for k in keys:
        if isinstance(obj, dict):
            v = obj.get(k)
            if v not in (None, ''):
                return v
        elif isinstance(obj, list):
            for it in obj:
                r = _pick(it, *keys)
                if r not in (None, ''):
                    return r
    return ''


# 排序筛选（与原版 AppV7 homeContent 硬编码一致：最新/最热/好评，无"全部"）
_ORDER_FILTER = {'key': 'order', 'name': '排序',
                 'value': [{'n': '最新', 'v': '最新'},
                           {'n': '最热', 'v': '最热'},
                           {'n': '好评', 'v': '好评'}]}

# 动态筛选维度：key=nav type_extend 字段名 / name=UI 显示名
_EXT_FILTER_KEYS = (('class', '分类'), ('area', '地区'), ('lang', '语言'), ('year', '年份'))


def _build_filters(te):
    """由 nav 响应单个分类的 type_extend 构造 OK影视 filters 列表（含 order 固定项）"""
    fl = [dict(_ORDER_FILTER)]
    if not isinstance(te, dict):
        return fl
    for key, label in _EXT_FILTER_KEYS:
        raw = str(te.get(key) or '')
        vals = [{'n': t, 'v': t} for t in raw.split(',') if t.strip()]
        if vals:
            fl.append({'key': key, 'name': label,
                       'value': [{'n': '全部', 'v': ''}] + vals})
    return fl


def _extract_vod_info(txt):
    """从解密明文（可能丢失 code/msg 前导）中定位完整 vod_info JSON"""
    idx = txt.find('"vod_info":')
    if idx < 0:
        return None
    j = txt.find('{', idx)
    if j < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(j, len(txt)):
        ch = txt[i]
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(txt[j:i + 1])
                except Exception:
                    return None
    return None


class Spider(_BaseSpider):
    name = '⑤线秒播'
    siteKey = 'AppV7Xnm'
    _codes = {}

    def init(self, extend=''):
        return ''

    # ================= 首页 =================
    def homeContent(self, filter):
        txt = _dec_resp(_post('nav', {'token': ''}))
        obj = _loads(txt)
        classes = []
        filters = {}
        try:
            for it in obj.get('data') or []:
                tid = str(it.get('type_id'))
                name = it.get('type_name', '')
                classes.append({'type_id': tid, 'type_name': name})
                # 原版 filters 动态来自 type_extend（class/area/lang/year 逗号列表）
                filters[tid] = _build_filters(it.get('type_extend') or {})
        except Exception:
            pass
        return {'class': classes, 'filters': filters, 'list': []}

    # ================= 分类 =================
    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid)
        # OK影视 契约：filter 是布尔开关，筛选值在 extend（可能为 JSON 字符串）
        if extend and not isinstance(extend, dict):
            try:
                extend = json.loads(str(extend))
            except Exception:
                extend = None
        if tid.startswith('rank_'):
            data = {'token': '', 'id': int(tid[5:])}
            method = 'rank_video_list'
        else:
            data = {'token': '', 'pg': int(pg or 1), 'tid': int(tid),
                    'class': '', 'area': '', 'lang': '', 'year': '', 'order': '最新'}
            if extend and isinstance(extend, dict):
                # 与原版 extend.getOrDefault(key, default) 一致；v='' 的"全部"不覆盖
                for k in ('class', 'area', 'lang', 'year', 'order'):
                    v = extend.get(k)
                    if v:
                        data[k] = str(v)
            method = 'video_list'
        txt = _dec_resp(_post(method, data))
        obj = _loads(txt)
        items = []
        for it in obj.get('data') or []:
            items.append({
                'vod_id': str(it.get('vod_id', '')),
                'vod_name': it.get('vod_name', ''),
                'vod_pic': it.get('vod_pic', ''),
                'vod_remarks': it.get('vod_remarks', ''),
                'vod_content': it.get('vod_content', ''),
            })
        page = int(obj.get('page') or pg or 1)
        pc = int(obj.get('pagecount') or 1)
        total = int(obj.get('total') or len(items))
        return {'page': page, 'pagecount': pc if pc > 0 else 9999,
                'limit': 90, 'total': total, 'list': items}

    # ================= 详情 =================
    def detailContent(self, ids):
        vid = str(ids[0])
        data = {'sign_md5': _SIGN_MD5, 'apk_length': _APK_LEN,
                'apk_path': _APK_PATH, 'id': int(vid)}
        txt = _dec_resp(_post('video_detail', data))
        vod = _extract_vod_info(txt)
        if not vod:
            vod = _loads(txt).get('data') or {}
            if 'vod_info' in vod:
                vod = vod['vod_info']
        vp = vod.get('vod_play_url') or ''
        vf = vod.get('vod_play_from') or '播放'
        if not vp:
            # 从 vod_url_with_player 构造（该线路真实地址都在此）
            srcs = vod.get('vod_url_with_player') or []
            vf_list = []
            url_list = []
            self._codes = {}
            for s in srcs:
                nm = s.get('name') or s.get('code') or '播放'
                u = s.get('url') or ''
                code = s.get('code') or nm
                self._codes[nm] = code
                vf_list.append(nm)
                url_list.append(u)
            if url_list:
                vf = '$$$'.join(vf_list)
                vp = '$$$'.join(url_list)
        name = _pick(vod, 'vod_name') or vid
        vod_obj = {
            'vod_id': vid,
            'vod_name': name,
            'vod_pic': _pick(vod, 'vod_pic') or '',
            'type_name': _pick(vod, 'type_name', 'vod_class') or '',
            'vod_remarks': _pick(vod, 'vod_remarks') or '',
            'vod_area': _pick(vod, 'vod_area') or '',
            'vod_year': _pick(vod, 'vod_year') or '',
            'vod_director': _pick(vod, 'vod_director') or '',
            'vod_actor': _pick(vod, 'vod_actor') or '',
            'vod_content': _pick(vod, 'vod_content', 'vod_blurb') or '',
            'vod_play_from': vf,
            'vod_play_url': vp,
        }
        return {'list': [vod_obj]}

    # ================= 搜索 =================
    def searchContent(self, key, quick=True, pg=1):
        # 独立接口搜索规则：3 参签名 + pg 翻页 + 标题/演员整体匹配（不含详情）
        data = {'text': str(key), 'pg': int(pg or 1)}
        txt = _dec_resp(_post('search', data))
        obj = _loads(txt)
        k = str(key or '')
        items = []
        for it in obj.get('data') or []:
            # 规则 2c：剥离标题高亮标签
            title = re.sub(r'<[^>]+>', '', str(it.get('vod_name') or '')).strip()
            # 规则 2a/2b：标题 + 演员（vod_actor），整体子串匹配，不含简介
            actor = str(it.get('vod_actor') or '')
            if k and k not in title and k not in actor:
                continue
            items.append({
                'vod_id': str(it.get('vod_id', '')),
                'vod_name': title,
                'vod_pic': it.get('vod_pic', ''),
                'vod_remarks': it.get('vod_remarks', ''),
            })
        return {'page': int(obj.get('page') or pg or 1),
                'pagecount': int(obj.get('pagecount') or 1),
                'limit': int(obj.get('limit') or 90),
                'total': int(obj.get('total') or len(items)),
                'list': items}

    # 规则 5：OK影视 快搜入口
    def quickSearch(self, key, quick=True, pg=1):
        return self.searchContent(key, True, pg)

    # ================= 播放 =================
    def playerContent(self, flag, id, vipFlags):
        u = str(id)
        if u.startswith('http://') or u.startswith('https://'):
            return {'parse': 0, 'playUrl': u}
        code = self._codes.get(str(flag), str(flag))
        resp = _post('secret_parse_api_url', {'token': '', 'url': u, 'player_code': code})
        txt = _dec_resp(resp)
        obj = _loads(txt)
        url = _pick(obj, 'url', 'playUrl', 'play_url', 'data')
        if isinstance(url, dict):
            url = _pick(url, 'url', 'playUrl', 'play_url')
        if url and str(url).startswith('http'):
            return {'parse': 0, 'playUrl': str(url)}
        return {'parse': 1, 'playUrl': u,
                'msg': '该线路需服务器解析，请切换其它线路'}


class AppV7XnmAmns(Spider):
    """OK影视 api=csp_AppV7Amns(ext=AppV7Xyz) 别名类"""
    pass


def main():
    s = Spider()
    h = s.homeContent(False)
    print('首页分类:', [c['type_name'] for c in h['class']][:12])
    if h['class']:
        c = s.categoryContent(h['class'][0]['type_id'], 1, None, None)
        print('分类[%s]条数:' % h['class'][0]['type_name'], len(c['list']))
        if c['list']:
            v = c['list'][0]
            print('列表首项:', v['vod_name'], v['vod_remarks'])
            d = s.detailContent([v['vod_id']])
            if d['list']:
                vod = d['list'][0]
                print('详情:', vod['vod_name'], '| 源:', vod['vod_play_from'][:80])
                eps = vod['vod_play_url'].split('$$$')[0].split('#')
                print('首个源集数:', len(eps), '首集:', eps[0][:80] if eps else '-')


if __name__ == '__main__':
    main()
