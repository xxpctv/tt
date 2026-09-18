# -*- coding: utf-8 -*-
"""
AppV7 线路①（AppV7Fz·棠溪）独立版
协议：http://198.16.60.3:6688/nfenzhu.php /v7/logs 全链路（nav / video_list / rank_video_list /
      video_detail / secret_parse_api_url），抓包样本逐条回放验证。
加密：logEn = b64url( urandom16 + AES128CBC( key=MD5(buildTime + '^~!@#[-' + pkg)[:16],
      iv=urandom16, PKCS7(json) ) )；请求头固定 build-time / pk-id / version 等。
响应：nav/列表/排行明文 JSON；video_detail 为加密流（提示流 b64 + 密文），按 pos/v2/ivo 三重扫描 + K1 嗅探解密。
播放：云播壹/贰/叁号（ffm3u8/lzm3u8/rym3u8）为直链 m3u8；其余线路为加密 token，尝试服务器
      secret_parse_api_url 解析（响应为动态 key 加密，无法本地静态解出时提示切换直链线路）。
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

_BUILD_TIME = '1773893703246'
_PKG = 'com.zitibaohe.jianzhuzigejianli.szxja'
_BASE = 'http://198.16.60.3:6688/nfenzhu.php'
_PREFIX = '/v7/'
_SIGN_MD5 = 'd16074f47cceb00256ce9d9519d5a5c1'
_APK_LEN = 56877789
_APK_PATH = ('/data/app/~~AA8qe9si8QzRJHndrDtheI==/'
             'com.zitibaohe.jianzhuzigejianli.szxja-dM4vpQqtbZYdNHdNeBxmd8==/base.apk')
_HEADERS = {
    'User-Agent': 'Dart/3.11 (dart:io)',
    'build-time': _BUILD_TIME,
    'pk-id': _PKG,
    'version': '1.0.4',
    'version-number': '14',
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
    req = urllib.request.Request(_BASE + _PREFIX + 'logs', data=body.encode(), headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode('utf-8', 'replace')
    except Exception:
        return ''


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
    name = '①线秒播'
    siteKey = 'AppV7Fz'
    _codes = {}

    def init(self, extend=''):
        return ''

    # ================= 首页 =================
    def homeContent(self, filter):
        txt = _dec_resp(_post('nav', {'token': ''}))
        obj = _loads(txt)
        classes = []
        try:
            for it in obj.get('data') or []:
                classes.append({'type_id': str(it.get('type_id')),
                                'type_name': it.get('type_name', '')})
        except Exception:
            pass
        return {'class': classes, 'list': []}

    # ================= 分类 =================
    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid)
        if tid.startswith('rank_'):
            data = {'token': '', 'id': int(tid[5:])}
            method = 'rank_video_list'
        else:
            data = {'token': '', 'pg': int(pg or 1), 'tid': int(tid),
                    'class': '', 'area': '', 'lang': '', 'year': '', 'order': '最新'}
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
        data = {'token': '', 'sign_md5': _SIGN_MD5, 'apk_length': _APK_LEN,
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
            # 从 vod_url_with_player 构造
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
            'type_name': _pick(vod, 'type_name') or '',
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
        data = {'text': str(key), 'pg': int(pg or 1)}
        txt = _dec_resp(_post('search', data))
        obj = _loads(txt)
        items = []
        for it in obj.get('data') or []:
            items.append({
                'vod_id': str(it.get('vod_id', '')),
                'vod_name': it.get('vod_name', ''),
                'vod_pic': it.get('vod_pic', ''),
                'vod_remarks': it.get('vod_remarks', ''),
            })
        return {'list': items}

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
                'msg': '该线路需服务器解析，请切换云播壹/贰/叁号线路'}


class AppV7FzAmns(Spider):
    """OK影视 api=csp_AppV7Amns(ext=AppV7Fz) 别名类"""
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
                print('详情:', vod['vod_name'], '| 源:', vod['vod_play_from'][:60])
                eps = vod['vod_play_url'].split('$$$')[0].split('#')
                print('首个源集数:', len(eps), '首集:', eps[0][:60] if eps else '-')


if __name__ == '__main__':
    main()
