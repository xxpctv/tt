# -*- coding: utf-8 -*-
"""
好看短剧
请求链：
  - 列表:  POST https://sv.baidu.com/haokan/ui-feed/playletTagsFeed?osbranch=a0
           body = {tag_id, rn:"20", pn}  -> res.data.list[]
  - 详情:  ①POST /appui/api?osbranch=a0  {"video/commonlist": innerParams}  -> 取 results[0].content.vid
           ②POST /haokan/ui-video/playlet/rec/detail?osbranch=a0  {"vid":vid,"playlet_id":id}  -> data.vid_list[]
  - 播放:  POST /appui/api?osbranch=a0  {"video/relate": innerParams}  -> data.cur_video.clarityUrl[]{title,url}
  - 搜索:  POST /haokan/ui-interact/playlet/search/sugs?osbranch=a0  {"search_word":wd}  -> data[]
签名：无算法签名，靠固定 Cookie(BAIDUCUID) + Talos 头 + 伪装 UA（haokan/7.80.0.18）
兼容：OK影视 / 影视仓（TVBox Python 引擎）
"""
import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider:
        pass

_HOST = 'https://sv.baidu.com'
_LIST = '/haokan/ui-feed/playletTagsFeed?osbranch=a0'
_DETAIL_LIST = '/appui/api?osbranch=a0'
_DETAIL = '/haokan/ui-video/playlet/rec/detail?osbranch=a0'
_PLAY = '/appui/api?osbranch=a0'
_SEARCH = '/haokan/ui-interact/playlet/search/sugs?osbranch=a0'

_UA = ('Mozilla/5.0 (Linux; Android 11; M2012K10C Build/RP1A.200720.011; wv) '
       'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/87.0.4280.141 Mobile Safari/537.36 '
       'haokan/7.80.0.18 (Baidu; P1 11)/imoaiX_03_11_C01K2102M/1043677m/'
       '5ACDB023CFB9D64743B08E51953F7C76%7CVSAJ32AVA/1/7.80.0.18/780001/1/immersiveMode/'
       'modeV4PlusWhite/isFirstInstall/bbqMode/bbqModeV2/blackStyle/isPlaylet Talos/1.8.7')

_HEADERS = {
    'User-Agent': _UA,
    'Talos-Module-Name': 'shortDrama',
    'Talos-Module-Version': '1.0.71.1',
    'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8',
    'Cookie': 'BAIDUCUID=giHCu0azv80G8SfQ0avU8gaaH8jfiv86ju2MugiR2i8-k3a35avAa1_mA',
}

_CLASSES = [
    ('1', '热播剧'), ('2', '新剧'), ('1001', '战神'), ('2001', '神豪'),
    ('1002', '神医'), ('1007', '甜宠'), ('1003', '赘婿'), ('2004', '穿越重生'),
    ('2005', '异能'), ('1006', '虐恋'), ('2006', '宫斗宅斗'), ('2009', '玄幻'),
]

# 清晰度排序（越高越优先）
_QUALITY_ORDER = {'4k': 0, '2k': 1, '高清': 2, '蓝光': 3, '超清': 4, '标清': 5}


def _post(url, body):
    """POST form-urlencoded body（聚合 js 该源走 form 编码，JSON 编码服务端返回空列表）"""
    data = urllib.parse.urlencode(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
        return json.loads(raw.decode('utf-8', 'replace'))
    except Exception:
        return {}


def _fmt_hot(h):
    """热度文本统一：纯数字(原始值)>=1万 -> x.x万，非数字保持原样"""
    try:
        f = float(h)
        if f >= 10000:
            s = ('%.1f' % (f / 10000)).rstrip('0').rstrip('.')
            return s + '万'
        return str(int(f)) if f == int(f) else str(f)
    except Exception:
        return h


def _actor_of(it):
    """从搜索/列表项提取演员字符串（响应无演员字段时返回空）"""
    for k in ('actor', 'actors', 'star', 'stars', 'starring', 'performer', 'protagonist', 'actorList'):
        v = it.get(k)
        if v:
            if isinstance(v, list):
                return ' '.join(str(x) for x in v)
            return str(v)
    return ''


class Spider(_BaseSpider):
    name = '好看短剧'
    siteKey = 'Haokan'

    def init(self, extend=''):
        return ''

    def homeContent(self, filter):
        return {'class': [{'type_id': i, 'type_name': n} for i, n in _CLASSES]}

    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid or '1')
        # 规则6：filter 是布尔开关，筛选值在 extend
        if extend and not isinstance(extend, dict):
            try:
                extend = json.loads(str(extend))
            except Exception:
                extend = None
        if isinstance(extend, dict) and extend.get('area'):
            tid = str(extend['area'])
        body = {'tag_id': tid, 'rn': '20', 'pn': str(pg or 1)}
        j = _post(_HOST + _LIST, body)
        items = (j.get('data') or {}).get('list') or []
        lst = []
        for it in items:
            tags = it.get('tags') or []
            ep = it.get('episodes_num_text') or ('%s集' % it.get('episodes_num') if it.get('episodes_num') else '')
            hot = it.get('hot_value') or ''
            # 卡片备注：去来源名（聚合才需要）；统一格式「状态｜集数｜热度」，热度固定最右
            if it.get('is_end'):
                core = '已完结｜%s' % ep if ep else '已完结'
            elif ep:
                core = '更新至%s' % ep
            else:
                core = ''
            if hot:
                remarks = '%s｜%s' % (core, hot) if core else str(hot)
            else:
                remarks = core
            lst.append({
                'vod_id': str(it.get('playlet_id', '')),
                'vod_name': it.get('playlet_title', ''),
                'vod_pic': it.get('playlet_poster', ''),
                'vod_remarks': remarks,
                'vod_content': '·'.join(str(t) for t in tags) if tags else '',
            })
        return {'list': lst, 'page': pg, 'pagecount': int(pg or 1) + 1}

    def detailContent(self, ids):
        did = str(ids[0] if isinstance(ids, list) else ids)
        # ① 先取 vid
        commonlist_id = str(int(time.time() * 1000))[:13]
        inner = ('enable_enter_playlet=0&seek_time=0&hotspot=0&auto_show_hot_point_panel=0'
                 '&type=playlet&commonlist_id=%s&scene=&vid=&enable_atlas=0&mark_pn=&uk='
                 '&ctime=0&from=playlet_new&id=%s&rn=10&pn=1&direction=3') % (commonlist_id, did)
        j1 = _post(_HOST + _DETAIL_LIST, {'video/commonlist': inner})
        first = (((j1.get('video/commonlist') or {}).get('data') or {}).get('results') or [None])[0]
        vid = (first or {}).get('content', {}).get('vid', '') if first else ''
        # ② 详情
        j2 = _post(_HOST + _DETAIL, {'vid': vid, 'playlet_id': did})
        d = j2.get('data') or {}
        vid_list = d.get('vid_list') or []
        if not vid_list and d.get('results'):
            vid_list = [x.get('vid') for x in d.get('results')]
        eps = []
        for i, v in enumerate(vid_list, 1):
            eps.append('第%s集$%s@%s' % (i, did, v))
        vod = {
            'vod_id': did,
            'vod_name': d.get('playlet_title') or '',
            'vod_pic': d.get('playlet_poster') or '',
            'vod_remarks': '%s播放·%s集' % (d.get('hot_value') or '', d.get('episodes_num') or ''),
            'vod_content': d.get('description') or '',
            'vod_play_from': '好看短剧',
            'vod_play_url': '#'.join(eps) or '暂无播放地址$0',
        }
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        try:
            parts = str(id).split('@')
            playlet_id = parts[0]
            vid = parts[1] if len(parts) > 1 else parts[0]
            inner = ('method=post&vid=%s&immersive_mode=v4_5&tplname=feed_small_video'
                     '&tag=playlet_talos&tab=detail&external_from=&is_dp_video=0'
                     '&immersive_square_type=3&video_set_id=%s&play_screen_type=1'
                     '&play_volume_type=2&play_external_device_type=1') % (vid, playlet_id)
            j = _post(_HOST + _PLAY, {'video/relate': inner})
            cur = ((j.get('video/relate') or {}).get('data') or {}).get('cur_video') or {}
            url_map = {}
            for c in cur.get('clarityUrl') or []:
                if c.get('title') and c.get('url'):
                    url_map[c['title']] = c['url']
            vl = cur.get('video_list') or {}
            if isinstance(vl, dict):
                for k, v in vl.items():
                    if k not in url_map and v:
                        url_map[k] = v
            if url_map:
                qs = sorted(url_map.keys(), key=lambda k: _QUALITY_ORDER.get(k, 999))
                urls = []
                for q in qs:
                    urls.append(q)
                    urls.append(url_map[q])
                return {'parse': 0, 'url': urls}
        except Exception:
            pass
        return {'parse': 0, 'url': id}

    def searchContent(self, key, quick=True, pg=1):
        k = str(key or '').strip()
        j = _post(_HOST + _SEARCH, {'search_word': k})
        items = j.get('data') or []
        lst = []
        for it in items:
            title = str(it.get('title') or '')
            # 搜索范围：标题 或 演员 包含关键词（不匹配简介/详情）
            actor = _actor_of(it)
            if k and k not in title and k not in actor:
                continue
            tag = str(it.get('tag') or '').replace('/', '·')
            lst.append({
                'vod_id': str(it.get('id', '')),
                'vod_name': title,
                'vod_pic': it.get('cover_url') or '',
                'vod_remarks': tag,
                'vod_content': '',
            })
        # 搜索接口无 集数/热度 → 并发补查详情（热度为真实数据；详情接口无完结字段）
        if lst:
            metas = {}
            with ThreadPoolExecutor(max_workers=5) as ex:
                futs = {ex.submit(self._fetch_hot, v['vod_id']): v for v in lst[:10]}
                for fu in futs:
                    metas[id(futs[fu])] = fu.result()
            for v in lst:
                if id(v) in metas:
                    ep, hot = metas[id(v)]
                    m = ''
                    if ep:
                        m = '%s集' % ep
                    if hot:
                        m = (m + '｜' if m else '') + hot
                    if m:
                        v['vod_remarks'] = m
        return {'list': lst}

    @staticmethod
    def _fetch_hot(pid):
        """补查单条 集数/热度（详情接口 rec/detail），失败返回空串"""
        try:
            j = _post(_HOST + _DETAIL, {'vid': pid, 'playlet_id': pid})
            d = j.get('data') or {}
            return str(d.get('episodes_num') or ''), _fmt_hot(d.get('hot_value') or '')
        except Exception:
            return '', ''

    # 兼容别名
    def quickSearch(self, key):
        return self.searchContent(key, True)

    def search(self, key):
        return self.searchContent(key, True)
