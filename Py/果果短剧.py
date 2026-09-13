# -*- coding: utf-8 -*-
# 果果短剧 - 独立可用版
# 来源: aidaox-20260829.jar csp_GuoGuo（已解密去混淆, 签名/ECDH/解密全链路实测通过）
# 兼容: OK影视 / 影视仓（TVBox Python 引擎）
# 数据: 字节跳动短剧 fqnovel API（无签名列表/搜索, 签名剧集/播放参数）
# 签名: 作者签名服务器 https://jk.catvod.site/jk/hg (HMAC-SHA256) + ECDH P-256 + AES-GCM 派生播放key
# 播放: CDN MP4 (CENC AES-CTR 加密) -> 本地代理解密后输出
# 依赖: requests + cryptography（OK影视/影视仓 Python 引擎自带）

from base.spider import Spider
import requests
import base64
import hashlib
import hmac
import json
import re
import struct
import time
import uuid
import urllib.parse

# ---------------- 常量 ----------------
HMAC_KEY = bytes.fromhex('203611e7fbb53a20b5e87164ea59dfb7505d4032eb5f810f6827676f40cdd8cc')
SIGN_HOST = 'https://jk.catvod.site/jk/hg'
UA = 'com.phoenix.read/72732 (Linux; U; Android 13; zh_CN; Mi 10; Build/TKQ1.221114.001)'
HOSTS = ['https://api5-normal-sinfonlineb.fqnovel.com', 'https://api5-normal.fqnovel.com',
         'https://api5-normal-sinfonlinec.fqnovel.com', 'https://reading.snssdk.com']
DEVICE_ID = '1677186774376987'
IID = '4351204728771643'
CATES = [
    ('short_play', '短剧'), ('comic_series', '动漫短剧'), ('ai_series', 'AI短剧'),
]


# ---------------- HTTP 基础 ----------------
def _http(url, data=None, headers=None, timeout=20):
    r = requests.post(url, data=data, headers=headers or {}, timeout=timeout) if data is not None \
        else requests.get(url, headers=headers or {}, timeout=timeout)
    r.raise_for_status()
    return r.content


def _device_query():
    p = {'device_id': DEVICE_ID, 'iid': IID, 'aid': '8662', 'app_name': 'novelread',
         'version_code': '72732', 'version_name': '7.2.7.32', 'device_platform': 'android',
         'os': 'android', 'ssmix': 'a', 'device_type': 'Mi 10', 'device_brand': 'Xiaomi',
         'language': 'zh', 'os_api': '33', 'os_version': '13', 'manifest_version_code': '72732',
         'resolution': '1080*2206', 'dpi': '440', 'update_version_code': '72732',
         '_rticket': str(int(time.time() * 1000)), 'host_abi': 'arm64-v8a',
         'dragon_device_type': 'phone', 'channel': 'update_64', 'ac': 'wifi', 'cdid': str(uuid.uuid4())}
    return urllib.parse.urlencode(p)


def _device_query_for_sign():
    q = [('aid', '8662'), ('device_platform', 'android'), ('os_version', '13'), ('version_code', '72732'),
         ('version_name', '7.2.7.32'), ('update_version_code', '72732'), ('app_name', 'novelread'),
         ('channel', 'seo_laxin_pc_android'), ('device_id', DEVICE_ID), ('iid', IID),
         ('device_type', 'Mi 10'), ('device_brand', 'Xiaomi'), ('language', 'zh'),
         ('resolution', '1080*2206'), ('dpi', '440'), ('host_abi', 'arm64-v8a'), ('dragon_device_type', 'phone')]
    return urllib.parse.urlencode(q)


def _hmac_sign(method, path, body_bytes, ts, nonce):
    msg = ('%s|%s|%s|%d|%s' % (method, path, hashlib.sha256(body_bytes).hexdigest(), ts, nonce)).encode()
    return hmac.new(HMAC_KEY, msg, hashlib.sha256).hexdigest()


def _post_signed(path, body_obj):
    data = json.dumps(body_obj, separators=(',', ':')).encode()
    ts = int(time.time())
    nonce = str(uuid.uuid4())
    headers = {
        'Content-Type': 'application/json', 'X-App-Id': 'guoguo-t4',
        'X-App-Ts': str(ts), 'X-App-Nonce': nonce, 'X-App-Sign': _hmac_sign('POST', path, data, ts, nonce)}
    r = requests.post(SIGN_HOST + path, data=data, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()


def _fqnovel_post(path, body_obj):
    body_str = json.dumps(body_obj, separators=(',', ':')).replace(' ', '')
    md5u = hashlib.md5(body_str.encode()).hexdigest().upper()
    query = _device_query_for_sign()
    ts = int(time.time())
    sg = _post_signed('/v1/sign', {'query': query, 'body_md5': md5u, 'cookie': '', 'khronos': str(ts)})
    xg = sg.get('x_gorgon') or ''
    xk = sg.get('x_khronos') or str(ts)
    if not xg:
        return None
    headers = {'User-Agent': UA, 'Content-Type': 'application/json; charset=utf-8', 'Accept': 'application/json',
               'x-ss-dp': '8662', 'x-ss-stub': md5u, 'X-Gorgon': xg, 'X-Khronos': xk}
    last = None
    for host in HOSTS:
        try:
            return json.loads(_http(host + path + '?' + query, body_str.encode(), headers))
        except Exception as e:
            last = e
    raise last


# ---------------- 数据接口 ----------------
def _landpage(genre, offset, limit=18):
    body = {'filter_ids': '', 'req_scene': 'default', 'offset': offset, 'need_selector_panel': False,
            'limit': limit,
            'select_items': {'category_dim_epoch': [], 'online_time': [], 'gender': [],
                             'category_dim_role': [], 'genre': [genre], 'sort': [], 'category_dim_theme': []},
            'session_id': '', 'req_type': 'only_content', 'client_req_type': 1}
    url = HOSTS[0] + '/reading/distribution/category/landpage/v1/?' + _device_query()
    data = _http(url, json.dumps(body, separators=(',', ':')).encode(),
                 {'User-Agent': UA, 'Content-Type': 'application/json', 'Accept': 'application/json', 'x-ss-dp': '8662'})
    return json.loads(data)


def _extract_videos(obj, out=None):
    if out is None:
        out = []
    if isinstance(obj, dict):
        if 'series_id' in obj and 'title' in obj and ('vid' in obj or 'video_id' in obj):
            out.append(obj)
        for v in obj.values():
            _extract_videos(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _extract_videos(v, out)
    return out


def _episode_vids(series_id, vid):
    j = _fqnovel_post('/novel/player/video_detail/v1/',
                      {'series_id': series_id, 'vid': vid, 'content_type': 1})
    if not j or j.get('code') != 0:
        return []
    vl = ((j.get('data') or {}).get('video_data') or {}).get('video_list') or []
    items = []
    for i, it in enumerate(vl):
        v = it.get('vid') or it.get('video_id') or ''
        if v and re.match(r'^\d+$', v):
            items.append((it.get('vid_index') or (i + 1), v))
    items.sort(key=lambda x: x[0])
    return [v for _, v in items]


def _search_cue(keyword):
    """搜索联想词（data.text + data_v1[0..2]，最多3个）"""
    q = urllib.parse.urlencode({'query': keyword})
    url = HOSTS[0] + '/reading/bookapi/search/cue/v?' + _device_query() + '&' + q
    data = _http(url, headers={'User-Agent': UA, 'Accept': 'application/json', 'x-ss-dp': '8662'})
    j = json.loads(data)
    words = []
    d = j.get('data') or {}
    if d.get('text'):
        words.append(d['text'])
    for it in (j.get('data_v1') or [])[:3]:
        if len(words) >= 3:
            break
        if it.get('text'):
            words.append(it['text'])
    return words


def _search_landing(keyword, offset=0, count=20):
    q = urllib.parse.urlencode({'query': keyword, 'offset': str(offset), 'count': str(count)})
    url = HOSTS[0] + '/reading/bookapi/search/schema_landing/v?' + _device_query() + '&' + q
    data = _http(url, headers={'User-Agent': UA, 'Accept': 'application/json', 'x-ss-dp': '8662'})
    return json.loads(data)


def _search(keyword):
    """完整搜索：cue 联想词(≤3) -> schema_landing；不足12条补原文/原文+短剧"""
    words = _search_cue(keyword)
    if not words:
        words.append(keyword)
        if '短剧' not in keyword:
            words.append(keyword + '短剧')
    out = []
    seen = set()
    for w in words:
        if len(out) >= 12:
            break
        try:
            j = _search_landing(w)
        except Exception:
            continue
        for v in _extract_videos(j):
            sid = v.get('series_id')
            if sid and sid not in seen:
                out.append(v)
                seen.add(sid)
    # 兜底：补搜原文
    if len(out) < 12 and keyword not in words:
        try:
            j = _search_landing(keyword)
            for v in _extract_videos(j):
                sid = v.get('series_id')
                if sid and sid not in seen:
                    out.append(v)
                    seen.add(sid)
        except Exception:
            pass
    return out


def _video_model(vid):
    body = {'biz_param': {'detail_page_version': 0, 'device_level': 3, 'disable_digg_stat': False,
                          'disable_video_relate_book': False, 'from_video_id': '',
                          'need_all_video_definition': True, 'need_mp4_align': False,
                          'use_os_player': False, 'use_server_dns': True,
                          'use_server_dns_scene': 'cold_start_stage', 'video_platform': 0},
            'content_type': 1, 'video_id': vid}
    j = _fqnovel_post('/novel/player/video_model/v1/', body)
    if not j or j.get('code') != 0:
        return None
    vm = (j.get('data') or {}).get('video_model')
    if isinstance(vm, str):
        try:
            vm = json.loads(vm)
        except Exception:
            return None
    return vm or None


def _decode_main_url(s):
    s = (s or '').strip()
    if s.startswith('//'):
        return 'https:' + s
    if s.startswith('http://') or s.startswith('https://'):
        return s
    try:
        s = base64.b64decode(s).decode().strip()
    except Exception:
        return ''
    if s.startswith('//'):
        return 'https:' + s
    return s if s.startswith('http') else ''


def _derive_key(spade_a):
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.serialization import load_der_public_key
    priv = ec.generate_private_key(ec.SECP256R1())
    pub_b64 = base64.b64encode(priv.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
    j = _post_signed('/v1/derive', {'spade_a': spade_a, 'client_pub': pub_b64})
    server_pub, key_enc = j.get('server_pub'), j.get('key_enc')
    if not server_pub or not key_enc:
        return None
    srv = load_der_public_key(base64.b64decode(server_pub))
    shared = priv.exchange(ec.ECDH(), srv)
    aeskey = hashlib.sha256(shared).digest()
    enc = base64.b64decode(key_enc)
    plain = AESGCM(aeskey).decrypt(enc[:12], enc[12:], None)
    return plain.hex()


# ---------------- MP4 CENC 解密 (GuoGuoCenc 移植) ----------------
_CONTAINER = {'moov', 'trak', 'mdia', 'minf', 'stbl', 'sinf', 'schi'}


def _u(data, off, n):
    v = 0
    for i in range(n):
        v = (v << 8) | (data[off + i] & 0xFF)
    return v


def _typ(data, off):
    return ''.join(chr(data[off + i] & 0xFF) for i in range(4))


def _parse(data, start, end):
    boxes = []
    pos = start
    while pos + 8 <= end:
        size = _u(data, pos, 4)
        typ = _typ(data, pos + 4)
        if size == 1:
            size = _u(data, pos + 8, 8)
            hdr = 16
        else:
            hdr = 8
            if size == 0:
                size = end - pos
        if size < 8 or pos + size > end:
            break
        box = {'typ': typ, 'start': pos, 'hdr': hdr, 'size': size, 'a': []}
        body_start = pos + hdr
        if typ in _CONTAINER:
            box['a'] = _parse(data, body_start, pos + size)
        elif typ == 'stsd':
            box['a'] = _parse(data, body_start + 8, pos + size)
        elif typ in ('encv', 'hvc1', 'hev1', 'avc1'):
            box['a'] = _parse(data, body_start + 78, pos + size)
        elif typ in ('enca', 'mp4a'):
            box['a'] = _parse(data, body_start + 28, pos + size)
        boxes.append(box)
        pos += size
    return boxes


def _find(boxes, typ):
    for b in boxes:
        if b['typ'] == typ:
            return b
        r = _find(b.get('a', []), typ)
        if r is not None:
            return r
    return None


def _find_all(boxes, typ, out):
    for b in boxes:
        if b['typ'] == typ:
            out.append(b)
        _find_all(b.get('a', []), typ, out)


def _ctr_decrypt(key, iv, data):
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    if len(iv) < 16:
        iv = iv + b'\x00' * (16 - len(iv))
    c = Cipher(algorithms.AES(key), modes.CTR(iv)).decryptor()
    return c.update(data) + c.finalize()


def _decrypt_sample(key, iv, sample, subs):
    if not subs:
        return _ctr_decrypt(key, iv, sample)
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    if len(iv) < 16:
        iv = iv + b'\x00' * (16 - len(iv))
    out = bytearray(len(sample))
    pos = 0
    enc_parts = []
    for clear_len, enc_len in subs:
        out[pos:pos + clear_len] = sample[pos:pos + clear_len]
        pos += clear_len
        enc_parts.append(sample[pos:pos + enc_len])
        pos += enc_len
    dec = _ctr_decrypt(key, iv, b''.join(enc_parts))
    pos = 0
    dp = 0
    for clear_len, enc_len in subs:
        pos += clear_len
        out[pos:pos + enc_len] = dec[dp:dp + enc_len]
        dp += enc_len
        pos += enc_len
    return bytes(out)


def _sample_offsets(data, stbl):
    stsz = _find(stbl, 'stsz')
    stsc = _find(stbl, 'stsc')
    stco = _find(stbl, 'stco')
    co64 = _find(stbl, 'co64')
    if not stsz or not stsc:
        return []
    is64 = stco is None
    loc = co64 if is64 else stco
    if not loc:
        return []
    p = stsz['start'] + stsz['hdr'] + 4
    sample_size = _u(data, p, 4)
    count = _u(data, p + 4, 4)
    sizes = [sample_size] * count if sample_size else [_u(data, p + 8 + i * 4, 4) for i in range(count)]
    p = stsc['start'] + stsc['hdr'] + 4
    entry = _u(data, p, 4)
    first_chunk = [0] * entry
    samples_per_chunk = [0] * entry
    for i in range(entry):
        q = p + 4 + i * 12
        first_chunk[i] = _u(data, q, 4)
        samples_per_chunk[i] = _u(data, q + 4, 4)
    p = loc['start'] + loc['hdr'] + 4
    chunk_count = _u(data, p, 4)
    offsets = [_u(data, p + 4 + i * (8 if is64 else 4), 8 if is64 else 4) for i in range(chunk_count)]
    spc = []
    for i in range(entry):
        last = first_chunk[i + 1] - 1 if i + 1 < entry else chunk_count
        spc += [samples_per_chunk[i]] * (last - first_chunk[i] + 1)
    out = []
    si = 0
    for ci in range(chunk_count):
        n = spc[ci] if ci < len(spc) else (spc[-1] if spc else 0)
        off = offsets[ci]
        for _ in range(n):
            if si >= count:
                break
            out.append([off, sizes[si]])
            off += sizes[si]
            si += 1
    return out


def _parse_senc(data, senc, iv_len, ivs, subss):
    p = senc['start'] + senc['hdr']
    flags = _u(data, p + 1, 3)
    n = _u(data, p + 4, 4)
    p += 8
    for _ in range(n):
        ivs.append(data[p:p + iv_len])
        p += iv_len
        if flags & 2:
            k = _u(data, p, 2)
            p += 2
            subs = []
            for _ in range(k):
                subs.append((_u(data, p, 2), _u(data, p + 2, 4)))
                p += 6
            subss.append(subs)
        else:
            subss.append([])


def cenc_decrypt(data, key_hex):
    key = bytes.fromhex(key_hex)
    if len(key) != 16:
        raise ValueError('content key must 16B')
    buf = bytearray(data)
    boxes = _parse(buf, 0, len(buf))
    moov = _find(boxes, 'moov')
    if moov is None:
        raise ValueError('no moov')
    traks = []
    _find_all(moov.get('a', []), 'trak', traks)
    for trak in traks:
        stbl = _find(trak.get('a', []), 'stbl')
        senc = _find(trak.get('a', []), 'senc')
        if stbl is None or senc is None:
            continue
        tenc = _find(trak.get('a', []), 'tenc')
        iv_len = (buf[tenc['start'] + tenc['hdr'] + 7] & 0xFF) if tenc else 8
        frma = _find(trak.get('a', []), 'frma')
        orig = bytes(buf[frma['start'] + frma['hdr']:frma['start'] + frma['hdr'] + 4]) if frma else None
        offsets = _sample_offsets(buf, stbl.get('a', []))
        ivs, subss = [], []
        _parse_senc(buf, senc, iv_len, ivs, subss)
        n = min(len(offsets), len(ivs), len(subss))
        for i in range(n):
            off, sz = offsets[i]
            sample = bytes(buf[off:off + sz])
            buf[off:off + sz] = _decrypt_sample(key, ivs[i], sample, subss[i])
        if orig:
            for t in ('encv', 'enca'):
                b = _find(trak.get('a', []), t)
                if b:
                    buf[b['start'] + 4:b['start'] + 8] = orig
        for t in ('sinf', 'senc', 'saio', 'saiz'):
            b = _find(trak.get('a', []), t)
            if b:
                buf[b['start'] + 4:b['start'] + 8] = b'free'
    return bytes(buf)


# ---------------- Spider ----------------
class Spider(Spider):
    def getName(self):
        return "果果短剧"

    def init(self, extend=""):
        global SIGN_HOST
        try:
            j = json.loads((extend or '').strip() or '{}')
            host = str(j.get('signHost') or '').strip()
            if host:
                SIGN_HOST = host.rstrip('/')
        except Exception:
            pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    # ---------- 首页 ----------
    def homeContent(self, filter):
        return {'class': [{'type_id': cid, 'type_name': name} for cid, name in CATES],
                'filters': {}}

    def homeVideoContent(self):
        return self.categoryContent('short_play', 1, False, {})

    # ---------- 分类列表 ----------
    def categoryContent(self, tid, pg, filter, extend):
        result = {'list': [], 'page': pg, 'pagecount': 9999, 'limit': 18, 'total': 999999}
        try:
            j = _landpage(tid, (int(pg) - 1) * 18)
            videos = []
            for v in _extract_videos(j):
                videos.append({
                    'vod_id': '%s|%s' % (v.get('series_id', ''), v.get('vid') or v.get('video_id', '')),
                    'vod_name': v.get('title', ''),
                    'vod_pic': v.get('cover') or v.get('thumb') or '',
                    'vod_remarks': v.get('episode_total') or v.get('episode_count') or '',
                    'vod_content': v.get('abstract') or v.get('description') or ''
                })
            result['list'] = videos
        except Exception:
            pass
        return result

    # ---------- 详情 ----------
    def detailContent(self, ids):
        rid = ids[0] if isinstance(ids, (list, tuple)) else ids
        try:
            parts = str(rid).split('|')
            series_id = parts[0]
            vid = parts[1] if len(parts) > 1 else parts[0]
            eps = _episode_vids(series_id, vid)
            play_url = '#'.join(['第%d集$%s' % (i + 1, v) for i, v in enumerate(eps)])
            vod = {
                'vod_id': rid,
                'vod_name': series_id,
                'vod_pic': '',
                'vod_content': '共 %d 集' % len(eps),
                'vod_remarks': '%d 集' % len(eps),
                'vod_actor': '果果短剧',
                'vod_play_from': '果果',
                'vod_play_url': play_url
            }
            return {'list': [vod]}
        except Exception as e:
            return {'list': [{
                'vod_id': rid, 'vod_name': '加载失败', 'vod_content': '加载失败: %s' % e,
                'vod_remarks': '加载失败', 'vod_actor': '', 'vod_play_from': '果果',
                'vod_play_url': '', 'vod_pic': ''
            }]}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags):
        vid = str(id).strip()
        try:
            vm = _video_model(vid)
            if not vm:
                return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': {}, 'pic': '', 'name': ''}
            vl = vm.get('video_list') or []
            if not vl:
                return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': {}, 'pic': '', 'name': ''}
            # 选最高清晰度
            item = None
            h_map = {}
            for it in vl:
                meta = it.get('video_meta') or {}
                h = meta.get('vheight') or meta.get('vwidth') or 0
                h_map.setdefault(int(h), it)
            item = h_map[max(h_map)] if h_map else vl[0]
            main_url = _decode_main_url(item.get('main_url'))
            enc = item.get('encrypt_info') or {}
            if not main_url:
                return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': {}, 'pic': '', 'name': ''}
            if enc.get('encrypt'):
                spade_a = enc.get('spade_a') or ''
                key = _derive_key(spade_a)
                if not key:
                    return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': {}, 'pic': '', 'name': ''}
                # 本地代理解密: /proxy?do=guoguo&vid=..&url=<b64>&key=<b64>
                q = urllib.parse.urlencode({
                    'do': 'guoguo', 'vid': vid,
                    'url': base64.b64encode(main_url.encode()).decode(),
                    'key': base64.b64encode(key.encode()).decode()})
                return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': 'http://127.0.0.1:9978/proxy?%s' % q,
                        'header': {}, 'pic': '', 'name': ''}
            else:
                # 未加密直接播
                return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': main_url,
                        'header': {'User-Agent': UA, 'Referer': 'https://www.douyin.com/'},
                        'pic': '', 'name': ''}
        except Exception:
            return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': {}, 'pic': '', 'name': ''}

    # ---------- 本地代理: 下载 + CENC 解密 ----------
    def localProxy(self, param):
        def _q(v):
            return v[0] if isinstance(v, (list, tuple)) and v else v
        try:
            main_url = base64.b64decode(_q(param.get('url', ''))).decode()
            key = base64.b64decode(_q(param.get('key', ''))).decode()
            data = _http(main_url, headers={'User-Agent': UA, 'Referer': 'https://www.douyin.com/'})
            body = cenc_decrypt(data, key)
            # OK影视/影视仓 标准四元组: [status, contentType, headers, body]
            return [200, 'video/mp4', [['Content-Type', 'video/mp4']], body]
        except Exception:
            return [200, 'video/mp4', [['Content-Type', 'video/mp4']], b'']

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, pg=1):
        result = {'list': [], 'page': pg, 'pagecount': 9999, 'limit': 20, 'total': 999999}
        try:
            videos = []
            for v in _search(key):
                videos.append({
                    'vod_id': '%s|%s' % (v.get('series_id', ''), v.get('vid') or v.get('video_id', '')),
                    'vod_name': v.get('title', ''),
                    'vod_pic': v.get('cover') or v.get('thumb') or '',
                    'vod_remarks': v.get('episode_total') or ''
                })
            result['list'] = videos
        except Exception:
            pass
        return result

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)
