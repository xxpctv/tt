# -*- coding: utf-8 -*-
"""
豪堪短剧 
协议：百度好看短剧（sv.baidu.com）四接口全链路实测 200
  - 首页/分类/搜索: POST /haokan/ui-feed/playletShelfFeed (osbranch=a0 [+tag_id/+search_word])
  - 详情:          POST /haokan/ui-video/playlet/rec/detail (playlet_id=vid=剧集id)
  - 播放:          POST /appui/api?osbranch=a0 body=video/relate=<urlencoded form> -> cur_video.video_src 直链
兼容：OK影视 / 影视仓（TVBox Python 引擎）
"""
import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider:
        pass

_UA = ('Mozilla/5.0 (Linux; Android 11; M2012K10C Build/RP1A.200720.011) '
       'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/107.0.0.0 Safari/537.36')

_FEED = 'https://sv.baidu.com/haokan/ui-feed/playletShelfFeed'
# 分类：playletTagsFeed 按 tag_id 返回（ShelfFeed 是首页聚合，忽略 tag_id）
_TAG_FEED = 'https://sv.baidu.com/haokan/ui-feed/playletTagsFeed?osbranch=a0'
# 搜索：search/sugs 独立搜索接口（ShelfFeed + search_word 不生效）
_SEARCH = 'https://sv.baidu.com/haokan/ui-interact/playlet/search/sugs?osbranch=a0'
_DETAIL = 'https://sv.baidu.com/haokan/ui-video/playlet/rec/detail'
_RELATE = 'https://sv.baidu.com/appui/api'

_HEADERS = {
    'User-Agent': _UA,
    'Talos-Module-Name': 'shortDrama',
    'Talos-Module-Version': '1.0.71.1',
    'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8',
    'Cookie': 'BAIDUCUID=giHCu0azv80G8SfQ0avU8gaaH8jfiv86ju2MugiR2i8-k3a35avAa1_mA',
}

_PLAY_FORM = ('method=post&vid=%s&immersive_mode=v4_5&tplname=feed_small_video'
              '&tag=playlet_talos&tab=detail&external_from=&is_dp_video=0'
              '&immersive_square_type=3&video_set_id=%s&play_screen_type=1')


def _post(url, params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, headers={
        'User-Agent': _UA, 'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode('utf-8', 'replace')
    except Exception:
        return ''


def _post_json(url, params):
    """POST form-urlencoded -> dict（分类/搜索用，带完整请求头）"""
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode('utf-8', 'replace'))
    except Exception:
        return {}


def _actor_of(it):
    """从列表项提取演员字符串（响应无演员字段时返回空）"""
    for k in ('actor', 'actors', 'star', 'stars', 'starring', 'performer', 'protagonist', 'actorList'):
        v = it.get(k)
        if v:
            if isinstance(v, list):
                return ' '.join(str(x) for x in v)
            return str(v)
    return ''


def _fetch_hot(pid):
    """补查单条 集数/热度（详情接口 rec/detail），失败返回空串"""
    try:
        d = _post_json(_DETAIL, {'playlet_id': pid, 'vid': pid})
        dd = d.get('data') or {}
        return str(dd.get('episodes_num') or ''), _fmt_hot(dd.get('hot_value') or '')
    except Exception:
        return '', ''


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


def _tag_list(obj):
    """data.list -> OK影视 列表项（playletTagsFeed 分类结构）"""
    out = []
    try:
        items = obj['data']['list']
    except Exception:
        return out
    for it in items or []:
        ep = it.get('episodes_num_text') or (
            '%s集' % it.get('episodes_num') if it.get('episodes_num') else '')
        hot = it.get('hot_value') or ''
        # 卡片备注：状态｜集数｜热度，热度固定最右
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
        out.append({
            'vod_id': str(it.get('playlet_id', '')),
            'vod_name': it.get('playlet_title', ''),
            'vod_pic': it.get('playlet_poster', ''),
            'vod_remarks': remarks,
            'vod_content': '',
        })
    return out


def _post_body(url, body):
    req = urllib.request.Request(url, data=body.encode(), headers={
        'User-Agent': _UA, 'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode('utf-8', 'replace')
    except Exception:
        return ''


def _feed_list(obj):
    """data.playlet_feed_tags.list -> OK影视 列表项"""
    out = []
    try:
        tags = obj['data']['playlet_feed_tags']['list']
    except Exception:
        return out
    for it in tags or []:
        out.append({
            'vod_id': str(it.get('playlet_id', '')),
            'vod_name': it.get('playlet_title', ''),
            'vod_pic': it.get('playlet_poster', ''),
            'vod_remarks': it.get('episodes_num_text', ''),
            'vod_content': it.get('description', ''),
        })
    return out


class Spider(_BaseSpider):
    name = '豪堪短剧'
    siteKey = 'HHkk'

    def init(self, extend=''):
        return ''

    # ================= 首页 =================
    def homeContent(self, filter):
        body = _post(_FEED, {'osbranch': 'a0'})
        try:
            obj = json.loads(body)
        except Exception:
            return {'class': [], 'list': []}
        classes = []
        try:
            for t in obj['data'].get('playlet_tags') or []:
                classes.append({'type_id': str(t.get('tag_id')), 'type_name': t.get('name', '')})
        except Exception:
            pass
        return {'class': classes, 'list': _feed_list(obj)}

    # ================= 分类 =================
    def categoryContent(self, tid, pg, filter, extend):
        # 用 playletTagsFeed 按 tag_id 取分类列表（ShelfFeed 忽略 tag_id 导致各分类相同）
        obj = _post_json(_TAG_FEED, {'tag_id': str(tid), 'rn': '20', 'pn': str(pg or 1)})
        return {'page': int(pg or 1), 'pagecount': 9999, 'limit': 90, 'total': 9999, 'list': _tag_list(obj)}

    # ================= 详情 =================
    def detailContent(self, ids):
        vid = str(ids[0])
        body = _post(_DETAIL, {'playlet_id': vid, 'vid': vid})
        try:
            d = json.loads(body).get('data', {})
        except Exception:
            d = {}
        vid_list = d.get('vid_list') or []
        vids = [str(v) for v in vid_list if v]
        eps = []
        for i, v in enumerate(vids, 1):
            eps.append('第%s集$%s|%s' % (i, v, vid))
        vod = {
            'vod_id': vid,
            'vod_name': d.get('playlet_title') or vid,
            'vod_pic': d.get('playlet_poster') or '',
            'type_name': d.get('tag_text') or '',
            'vod_remarks': ('%s集' % d.get('episodes_num')) if d.get('episodes_num') else '',
            'vod_content': d.get('description') or '',
            'vod_play_from': '百度短剧',
            'vod_play_url': '#'.join(eps),
        }
        return {'list': [vod]}

    # ================= 搜索 =================
    def searchContent(self, key, quick=True, pg=1):
        # OK影视 5.1.6 传 3 参(key, quick, page)；2 参会被 TypeError 静默跳过
        # 用独立搜索接口 search/sugs（ShelfFeed + search_word 服务端不执行搜索）
        k = str(key or '').strip()
        j = _post_json(_SEARCH, {'search_word': k})
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
                futs = {ex.submit(_fetch_hot, v['vod_id']): v for v in lst[:10]}
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

    # 兼容别名：OK影视 快搜入口
    def quickSearch(self, key, quick=True, pg=1):
        return self.searchContent(key, True, pg)

    # ================= 播放（id=vid|playlet_id） =================
    def playerContent(self, flag, id, vipFlags):
        parts = str(id).split('|')
        v = parts[0]
        sid = parts[1] if len(parts) > 1 else v
        body = _post_body(_RELATE + '?osbranch=a0',
                          'video/relate=' + urllib.parse.quote_plus(_PLAY_FORM % (v, sid)))
        url = ''
        try:
            rel = json.loads(body).get('video/relate') or {}
            url = ((rel.get('data') or {}).get('cur_video') or {}).get('video_src', '')
        except Exception:
            pass
        if not url:
            url = id
        return {'parse': 0, 'playUrl': url, 'header': {'User-Agent': _UA}}


class HHkkAmns(Spider):
    """OK影视 api=csp_HHkkAmns 别名类"""
    pass


def main():
    s = Spider()
    h = s.homeContent(False)
    print('首页分类:', [c['type_name'] for c in h['class']][:5])
    print('首页列表条数:', len(h['list']), '首项:', h['list'][0]['vod_name'] if h['list'] else '-')
    if h['class']:
        c = s.categoryContent(h['class'][0]['type_id'], 1, None, None)
        print('分类[%s]条数:' % h['class'][0]['type_name'], len(c['list']))
    d = s.detailContent([h['list'][0]['vod_id']]) if h['list'] else {'list': []}
    if d['list']:
        vod = d['list'][0]
        print('详情:', vod['vod_name'], vod['vod_remarks'], '集数:', len(vod['vod_play_url'].split('#')))
        ep0 = vod['vod_play_url'].split('#')[0]
        eid = ep0.split('$')[1]
        p = s.playerContent('', eid, [])
        print('播放:', p['playUrl'][:100])


if __name__ == '__main__':
    main()
