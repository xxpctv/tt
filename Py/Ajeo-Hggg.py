# -*- coding: utf-8 -*-
"""Ajeo-Hggg：短剧热榜 / 漫剧热榜 / 短剧推荐（csp_HgggAmns / csp_HgdhAmns）
协议：字节跳动 fqnovel 短剧系（与果果同后端）
  - 列表:   POST /reading/distribution/category/landpage/v1/  (无签名)
  - 推荐:   GET  /reading/bookapi/bookmall/cell/change/v:version/ (无签名)
  - 详情:   POST /novel/player/video_detail/v1/  (X-Gorgon, 作者签名服务器)
  - 播放:   POST /novel/player/video_model/v1/  (X-Gorgon) -> CENC MP4 本地代理解密
  - 搜索:   GET  /reading/bookapi/search/schema_landing/v (无签名)
兼容：OK影视 / 影视仓（TVBox Python 引擎）
"""
import base64
import hashlib
import hmac
import json
import re
import time
import uuid
import urllib.request
import urllib.parse
import ssl

# ---------------- 常量（从 aowu jar 解串提取） ----------------
HOST = 'https://api5-normal-sinfonlineb.fqnovel.com'
SIGN_HOST = 'https://jk.catvod.site/jk/hg'
HMAC_KEY = bytes.fromhex('203611e7fbb53a20b5e87164ea59dfb7505d4032eb5f810f6827676f40cdd8cc')
UA = 'AVDML_2.1.252.61-novel_ANDROID,ShortPlay,MDLTaskPreload'
UA_PLAY = 'com.phoenix.read/72732 (Linux; U; Android 13; zh_CN; Mi 10; Build/TKQ1.221114.001)'
DEVICE_ID = '4425983911541328'
IID = '2204975347841795'
VERSION_CODE = '7.3.6.32'
AID = '8662'
CTX = ssl.create_default_context()

HOME_CATES = [
    ('short_play', '短剧'),
    ('ai_series', 'AI短剧'),
    ('comic_series', '漫剧'),
]


# ---------------- 基础工具 ----------------
def _http(url, data=None, headers=None, timeout=20):
    req = urllib.request.Request(url, data=data, headers=headers or {},
                                 method='POST' if data is not None else 'GET')
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read()


def _device_query():
    p = {'device_id': DEVICE_ID, 'iid': IID, 'aid': AID, 'app_name': 'novelread',
         'version_code': VERSION_CODE, 'version_name': '7.2.7.32', 'device_platform': 'android',
         'os': 'android', 'ssmix': 'a', 'device_type': 'Mi 10', 'device_brand': 'Xiaomi',
         'language': 'zh', 'os_api': '33', 'os_version': '13', 'manifest_version_code': VERSION_CODE,
         'resolution': '1080*2206', 'dpi': '440', 'update_version_code': VERSION_CODE,
         '_rticket': str(int(time.time() * 1000)), 'host_abi': 'arm64-v8a',
         'dragon_device_type': 'phone', 'channel': 'update_64', 'ac': 'wifi',
         'cdid': str(uuid.uuid4())}
    return urllib.parse.urlencode(p)


def _device_query_for_sign():
    q = [('aid', AID), ('device_platform', 'android'), ('os_version', '13'), ('version_code', VERSION_CODE),
         ('version_name', '7.2.7.32'), ('update_version_code', VERSION_CODE), ('app_name', 'novelread'),
         ('channel', 'seo_laxin_pc_android'), ('device_id', DEVICE_ID), ('iid', IID),
         ('device_type', 'Mi 10'), ('device_brand', 'Xiaomi'), ('language', 'zh'),
         ('resolution', '1080*2206'), ('dpi', '440'), ('host_abi', 'arm64-v8a'), ('dragon_device_type', 'phone')]
    return urllib.parse.urlencode(q)


def _hmac_sign(method, path, body_bytes, ts, nonce):
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    msg = ('%s|%s|%s|%d|%s' % (method, path, body_hash, ts, nonce)).encode()
    return hmac.new(HMAC_KEY, msg, hashlib.sha256).hexdigest()


def _post_signed(path, body_obj):
    data = json.dumps(body_obj, separators=(',', ':')).encode()
    ts = int(time.time())
    nonce = str(uuid.uuid4())
    sig = _hmac_sign('POST', path, data, ts, nonce)
    req = urllib.request.Request(SIGN_HOST + path, method='POST', data=data, headers={
        'Content-Type': 'application/json', 'X-App-Id': 'guoguo-t4',
        'X-App-Ts': str(ts), 'X-App-Nonce': nonce, 'X-App-Sign': sig})
    with urllib.request.urlopen(req, timeout=10, context=CTX) as r:
        return json.loads(r.read())


def _fqnovel_post(path, body_obj):
    body_str = json.dumps(body_obj, separators=(',', ':')).replace(' ', '')
    md5u = hashlib.md5(body_str.encode()).hexdigest().upper()
    query = _device_query_for_sign()
    ts = int(time.time())
    try:
        sg = _post_signed('/v1/sign', {'query': query, 'body_md5': md5u, 'cookie': '', 'khronos': str(ts)})
        xg = sg.get('x_gorgon', '')
        xk = sg.get('x_khronos', str(ts))
    except Exception:
        xg, xk = '', str(ts)
    headers = {'User-Agent': UA_PLAY, 'Content-Type': 'application/json; charset=utf-8',
               'Accept': 'application/json', 'x-ss-dp': AID, 'x-ss-stub': md5u}
    if xg:
        headers['X-Gorgon'] = xg
        headers['X-Khronos'] = xk
    return json.loads(_http(HOST + path + '?' + query, body_str.encode(), headers))


# ---------------- 列表（landpage：Hggg 格式） ----------------
def _landpage(tid, offset=0, limit=18, extend=None):
    extend = extend or {}
    sel = {
        'category_dim_epoch': extend.get('category_dim_epoch') or [],
        'online_time': extend.get('online_time') or [],
        'gender': extend.get('gender') or [],
        'category_dim_role': extend.get('category_dim_role') or [],
        'category_dim_theme': extend.get('category_dim_theme') or [],
        'genre': [tid] if tid not in ('', 'default') else [],
        'sort': extend.get('sort') or [],
    }
    body = {'filter_ids': '', 'req_scene': tid if tid not in ('', 'default') else 'default',
            'offset': int(offset or 0), 'need_selector_panel': False, 'limit': int(limit or 18),
            'select_item': sel, 'session_id': '', 'req_type': 'only_content', 'client_req_type': 1}
    url = HOST + '/reading/distribution/category/landpage/v1/?' + _device_query()
    data = _http(url, json.dumps(body, separators=(',', ':')).encode(),
                 {'User-Agent': UA, 'Content-Type': 'application/json; charset=utf-8',
                  'Accept': 'application/json', 'x-ss-dp': AID})
    return json.loads(data)


# ---------------- 推荐流（Hgdh：bookmall cell/change） ----------------
def _rank(selected='', sub='', offset=0, session_id=''):
    q = {'cell_id': '7470092475068071998', 'client_req_type': '2', 'client_template': '2',
         'tab_type': '26', 'screen_width_px': '1080', 'selected_items': selected, 'sub_selected_items': sub,
         'session_uuid': str(uuid.uuid4()), 'panel_selected_items': '', 'background_selected_items': '',
         'celebrity_user_id': '', 'filter_ids': '', 'unlimited_selector_change_type': '2',
         'session_id': session_id or '', 'rank_version': ''}
    if offset:
        q['offset'] = str(offset)
        q['unlimited_selector_change_type'] = '1'
    url = HOST + '/reading/bookapi/bookmall/cell/change/v:version/?' + _device_query() + '&' + urllib.parse.urlencode(q)
    return json.loads(_http(url, headers={'User-Agent': UA, 'Accept': 'application/json', 'x-ss-dp': AID}))


# ---------------- 提取 ----------------
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


def _extract_rows_videos(obj, out=None):
    """Hggg landpage video_data 列表（series_id/title/cover/episode_cnt）"""
    if out is None:
        out = []
    try:
        data = obj.get('data') or {}
        vd = data.get('video_data')
        if isinstance(vd, list):
            for it in vd:
                sid = it.get('series_id') or ''
                title = it.get('title') or ''
                if sid and title:
                    out.append(it)
    except Exception:
        pass
    return out


def _episode_vids(series_id, vid):
    body = {'series_id': series_id, 'vid': vid, 'content_type': 1}
    j = _fqnovel_post('/novel/player/video_detail/v1/', body)
    if not j or j.get('code') != 0:
        return []
    vd = (j.get('data') or {}).get('video_data') or {}
    vl = vd.get('video_list') or []
    items = []
    for i, it in enumerate(vl):
        v = it.get('vid') or it.get('video_id') or ''
        if v and re.match(r'^\d+$', v):
            items.append((it.get('vid_index') or (i + 1), v))
    items.sort(key=lambda x: x[0])
    return [v for _, v in items] or ([vid] if re.match(r'^\d+$', vid) else [])


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
            vm = None
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


# ---------------- MP4 CENC 解密 ----------------
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
    out2 = bytearray(len(sample))
    pos = 0
    dp = 0
    dec = _ctr_decrypt(key, iv, b''.join(sample[p:p + e] for (_, e) in subs))
    for (cl, en) in subs:
        out2[pos:pos + cl] = sample[pos:pos + cl]
        pos += cl
        out2[pos:pos + en] = dec[dp:dp + en]
        dp += en
        pos += en
    return bytes(out2)


def _sample_offsets(data, stbl):
    stsz = _find(stbl, 'stsz')
    stsc = _find(stbl, 'stsc')
    stco = _find(stbl, 'stco')
    co64 = _find(stbl, 'co64')
    is64 = 1 if stco is None else 0
    loc = co64 if is64 else stco
    if not stsz or not stsc or not loc:
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


def _cenc_decrypt(data, key_hex):
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
            dec = _decrypt_sample(key, ivs[i], sample, subss[i])
            buf[off:off + sz] = dec
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


# ================= Spider =================
class Spider:
    def __init__(self):
        self.genre = 'short_play'

    def init(self, cfg):
        try:
            ext = cfg.get('ext') or {}
            self.genre = ext.get('genre') or 'short_play'
        except Exception:
            pass

    def homeContent(self, filter):
        try:
            j = _landpage('default')
            classes = []
            try:
                data = j.get('data') or {}
                rows = data.get('selector_rows') or []
                for row in rows:
                    if (row.get('type') or '') != 'genre':
                        continue
                    for it in (row.get('items') or []):
                        sid = it.get('selector_item_id') or ''
                        nm = it.get('show_name') or ''
                        if sid and nm:
                            classes.append({'type_id': sid, 'type_name': nm})
            except Exception:
                pass
            if not classes:
                classes = [{'type_id': cid, 'type_name': name} for cid, name in HOME_CATES]
            videos = []
            for it in _extract_rows_videos(j):
                videos.append({
                    'vod_id': it.get('series_id') or '',
                    'vod_name': it.get('title') or '',
                    'vod_pic': it.get('cover') or '',
                    'vod_remarks': str(it.get('episode_cnt') or ''),
                    'vod_content': ''
                })
            return {'class': classes, 'filters': {}, 'list': videos[:40]}
        except Exception:
            return {'class': [{'type_id': cid, 'type_name': name} for cid, name in HOME_CATES],
                    'filters': {}, 'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        result = {'list': [], 'page': pg, 'pagecount': 9999, 'limit': 18, 'total': 999999}
        try:
            tid = tid or 'default'
            extend = extend or {}
            j = _landpage(tid, (int(pg) - 1) * 18, 18, extend)
            for it in _extract_rows_videos(j):
                result['list'].append({
                    'vod_id': it.get('series_id') or '',
                    'vod_name': it.get('title') or '',
                    'vod_pic': it.get('cover') or '',
                    'vod_remarks': str(it.get('episode_cnt') or ''),
                    'vod_content': ''
                })
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        rid = ids[0] if isinstance(ids, (list, tuple)) else ids
        try:
            rid = str(rid)
            if '|' in rid:
                series_id, vid = rid.split('|', 1)
            else:
                series_id, vid = rid, rid
            eps = _episode_vids(series_id, vid)
            play_url = '#'.join(['第%d集$%s' % (i + 1, v) for i, v in enumerate(eps)])
            vod = {'vod_id': rid, 'vod_name': series_id,
                   'vod_pic': '', 'vod_content': '共 %d 集' % len(eps),
                   'vod_remarks': '%d 集' % len(eps),
                   'vod_actor': 'Hggg', 'vod_play_from': '主线$$$备用',
                   'vod_play_url': play_url}
            return {'list': [vod]}
        except Exception as e:
            return {'list': [{'vod_id': rid, 'vod_name': '加载失败',
                              'vod_content': '加载失败: %s' % e, 'vod_remarks': '加载失败',
                              'vod_actor': '', 'vod_play_from': '主线$$$备用',
                              'vod_play_url': '', 'vod_pic': ''}]}

    def playerContent(self, flag, id, vipFlags):
        vid = str(id).strip()
        try:
            vm = _video_model(vid)
            if not vm:
                return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': {}, 'pic': '', 'name': ''}
            vl = vm.get('video_list') or []
            if isinstance(vl, dict):
                vl = list(vl.values())
            if not vl:
                return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': {}, 'pic': '', 'name': ''}
            item = None
            h_map = {}
            for it in vl:
                meta = it.get('video_meta') or {}
                h = meta.get('vheight') or meta.get('vwidth') or 0
                h_map.setdefault(int(h), it)
            item = h_map[max(h_map)] if h_map else vl[0]
            main_url = _decode_main_url(item.get('main_url'))
            enc = item.get('encrypt_info') or {}
            encrypted = bool(enc.get('encrypt') or item.get('encrypt'))
            if not main_url:
                return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': {}, 'pic': '', 'name': ''}
            if encrypted:
                spade_a = enc.get('spade_a') or item.get('spade_a') or ''
                key = _derive_key(spade_a)
                if not key:
                    return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': {}, 'pic': '', 'name': ''}
                u = base64.urlsafe_b64encode(main_url.encode()).decode().rstrip('=')
                k = base64.urlsafe_b64encode(key.encode()).decode().rstrip('=')
                q = urllib.parse.urlencode({'do': 'py', 'type': 'Ajeo-Hggg', 'url': u, 'key': k})
                return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': 'http://127.0.0.1:9978/proxy?%s' % q,
                        'header': {}, 'pic': '', 'name': ''}
            return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': main_url,
                    'header': {'User-Agent': UA_PLAY, 'Referer': 'https://www.douyin.com/'},
                    'pic': '', 'name': ''}
        except Exception:
            return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': {}, 'pic': '', 'name': ''}

    def searchContent(self, key, quick):
        result = {'list': [], 'page': 1, 'pagecount': 1, 'limit': 20, 'total': 0}
        try:
            key = (key or '').strip()
            if not key:
                return result
            # schema_landing 现为空：改用 landpage 流式搜索（与果果实践一致）
            tags = ['short_play', 'ai_series', 'comic_series']
            pages = [1] if quick else [1, 2]
            seen = set()
            for tag in tags:
                if len(result['list']) >= 40:
                    break
                for pg in pages:
                    try:
                        j = _landpage(tag, (pg - 1) * 18, 18)
                    except Exception:
                        continue
                    for it in _extract_rows_videos(j):
                        sid = it.get('series_id') or ''
                        title = it.get('title') or ''
                        if not sid or sid in seen:
                            continue
                        seen.add(sid)
                        if key not in title:
                            continue
                        result['list'].append({
                            'vod_id': sid, 'vod_name': title,
                            'vod_pic': it.get('cover') or '',
                            'vod_remarks': str(it.get('episode_cnt') or ''),
                            'vod_content': ''
                        })
                    if result['list'] and quick:
                        break
            result['total'] = len(result['list'])
        except Exception:
            pass
        return result

    def localProxy(self, param):
        def _q(v):
            return v[0] if isinstance(v, (list, tuple)) and v else v

        def _b64d(s):
            s = s.strip()
            try:
                return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))
            except Exception:
                return base64.b64decode(s + '=' * (-len(s) % 4))
        try:
            u = _q(param.get('url', '')) or ''
            main_url = u if u.startswith('http') else _b64d(u).decode()
            k = _q(param.get('key', '')) or ''
            key = _b64d(k).decode()
            data = _http(main_url, headers={'User-Agent': UA_PLAY,
                                            'Referer': 'https://www.douyin.com/'})
            dec = _cenc_decrypt(data, key)
            return {'status': 1, 'body': bytes(dec), 'headers': {'Content-Type': 'video/mp4'}}
        except Exception:
            return {'status': 0, 'body': b'', 'headers': {}}


# ================= API 别名类 =================
class HgggAmns(Spider):
    """短剧热榜 / 漫剧热榜（csp_HgggAmns，ext: short_play / comic_series / ai_series）"""
    pass


class HgdhAmns(Spider):
    """短剧推荐（csp_HgdhAmns）—— 推荐流走 bookmall cell/change"""
    def categoryContent(self, tid, pg, filter, extend):
        result = {'list': [], 'page': pg, 'pagecount': 9999, 'limit': 18, 'total': 999999}
        try:
            j = _rank(tid, '', (int(pg) - 1) * 18)
            for it in _extract_rows_videos(j):
                result['list'].append({
                    'vod_id': it.get('series_id') or '',
                    'vod_name': it.get('title') or '',
                    'vod_pic': it.get('cover') or '',
                    'vod_remarks': str(it.get('episode_cnt') or ''),
                    'vod_content': ''
                })
            if not result['list']:
                for it in _extract_videos(j):
                    sid = it.get('series_id') or ''
                    if not sid:
                        continue
                    result['list'].append({
                        'vod_id': sid,
                        'vod_name': it.get('title') or '',
                        'vod_pic': it.get('cover') or it.get('thumb') or '',
                        'vod_remarks': str(it.get('episode_cnt') or ''),
                        'vod_content': ''
                    })
        except Exception:
            pass
        return result


def main():
    s = Spider()
    h = s.homeContent(False)
    print('首页分类:', [c['type_name'] for c in h['class']][:8])
    print('首页列表条数:', len(h['list']), '首项:', h['list'][0]['vod_name'] if h['list'] else '-')
    if h['class']:
        c = s.categoryContent(h['class'][0]['type_id'], 1, None, None)
        print('分类[%s]条数:' % h['class'][0]['type_name'], len(c['list']))
    if h['list']:
        d = s.detailContent([h['list'][0]['vod_id']])
        if d['list']:
            vod = d['list'][0]
            print('详情:', vod['vod_name'], vod['vod_remarks'], '集数:', len(vod['vod_play_url'].split('#')))
            ep0 = vod['vod_play_url'].split('#')[0]
            eid = ep0.split('$')[1]
            p = s.playerContent('', eid, [])
            print('播放:', p['url'][:100])
    r = s.searchContent('离婚', False)
    print('搜索条数:', len(r['list']))


if __name__ == '__main__':
    main()
