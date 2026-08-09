/*
 * 直播转点播 (Live to VOD) 爬虫
 * 由 live2vod.js (jsjiami.com.v6 加密) 反混淆还原而来
 *
 * 还原说明:
 *   - 原文件用 jsjiami.com.v6 混淆: 字符串集中放在数组 lIIIl1ll,
 *     通过 Ii1l1III(hexIndex) 取值; 顶部 IIFE 先 shift/pop 掉首尾
 *     的版本标记, 因此实际索引从 'okhttp/3.15' 开始.
 *   - 本文件已将所有 Ii1l1III('xx') 调用、\xXX 内联转义、变量名
 *     还原为可读形式, 逻辑与原文件完全一致.
 */

let headers = {
    'User-Agent': 'okhttp/3.15'
};
let classes = [];      // 首页分类列表 (type_id / type_name)
let cates = {};        // 每个分类下的影片列表缓存  cates[typeId] = [vod, ...]
let picUrl = '';       // 封面图模板 URL (可含 {name} / {cate} / <正则> 占位符)
let webPaths = {};     // typeId -> 该分类接口的目录前缀, 用于拼相对路径
// req 超时 (毫秒). TVBox/CatVod 的 req 支持 timeout 选项 (基于 okhttp call.timeout).
// 防止源挂掉时长时间阻塞; 不支持该选项的引擎会忽略, 无副作用.
let REQ_TIMEOUT = 8000;     // 常规访问超时
let SEARCH_TIMEOUT = 5000;  // 搜索冷启动用更短超时, 保证搜索快速响应, 挂掉的源快速跳过

// 入口: 解析站点配置串
//   配置串格式:  [baseUrl$$$]ext[#...][&&&picUrl]
//   - baseUrl$$$  : 可选, 站点根目录, 用于把相对路径补全
//   - &&&picUrl    : 可选, 封面图模板
//   - ext 主体以 '#' 分隔, 每段要么是 "名称$接口地址", 要么是一个 livesourcelist 接口地址
function init(ext) {
    let baseUrl = '';
    if (ext.indexOf('$$$') > 0) {
        baseUrl = ext.split('$$$')[0].trim();
        ext = ext.split('$$$')[1].trim();
    }
    if (ext.indexOf('&&&') > 0) {
        picUrl = ext.split('&&&')[1].trim();
        if (picUrl.indexOf('://') < 0) {
            picUrl = baseUrl + picUrl;
        }
        ext = ext.split('&&&')[0].trim();
    }
    console.log('picUrl: ' + picUrl);

    let parts = ext.split('#');
    for (const part of parts) {
        if (part.indexOf('$') > 0) {
            // "名称$接口地址" 形式的分类
            let typeId = part;
            let typeName = part.split('$')[0];
            if (typeId.indexOf('://') < 0) {
                typeId = typeId.replace('$', '$' + baseUrl);   // 给相对地址补 baseUrl
            }
            classes.push({
                'type_id': typeId,
                'type_name': typeName.replace('!!', '')        // '!!' 前缀用于标记需要 detail 阶段二次处理的分类
            });
        } else {
            // 一个 /file/livesourcelist 接口, 返回 [{name, url}, ...]
            let url = part;
            if (url.indexOf('://') < 0) {
                url = baseUrl + url;
            }
            url = url.replace('/file/livesourcelist', '/livesourcelist');
            let resp = req(url, {
                'method': 'GET',
                'headers': headers,
                'timeout': REQ_TIMEOUT
            });
            try {
                let list = JSON.parse(resp.content);
                let dir = url.substring(0, url.lastIndexOf('/') + 1);   // 接口所在目录
                for (const item of list) {
                    let name = item.name;
                    let itemUrl = item.url;
                    let typeId = name + '$' + (itemUrl.indexOf('://') < 0 ? dir : '') + itemUrl;
                    classes.push({
                        'type_id': typeId,
                        'type_name': name.replace('!!', '')
                    });
                    webPaths[typeId] = dir;
                }
            } catch (e) {
                console.log('==== >>> ' + e);
            }
        }
    }
}

// 首页分类
function home(filter) {
    return JSON.stringify({
        'class': classes,
        'filters': null
    });
}

// 解析 M3U 直播源, 按 group-title 分组, 输出 "组名,#genre#\n名称,地址" 文本
function parseM3u(content, cate) {
    let groups = {};
    let regex = /(#EXTINF:.+?),([^,]+?)\s*\n(.+?)\s*\n/g;
    let m = null;
    while ((m = regex.exec(content)) != null) {
        let extinf = m[1];
        let name = m[2];
        let url = m[3];
        if (name == null || url == null || name == '' || url == '') {
            continue;
        }
        name = name.trim();
        url = url.trim();
        let group = cate;
        let groupRegex = /group-title="(.*?)"/;
        if (groupRegex.test(extinf)) {
            group = extinf.match(groupRegex)[1];
        }
        if (!groups[group]) {
            groups[group] = [];
        }
        groups[group].push(name + ',' + url);
    }
    let result = '';
    for (const group in groups) {
        result += group + '\n';
        for (const item of groups[group]) {
            result += item + '\n';
        }
    }
    return result;
}

// 解析 "频道" 格式 JSON: [{name, urls:[{name, urls:[...]]}]
function parseFm(content) {
    let result = '';
    let json = JSON.parse(content);
    for (const channel of json) {
        let name = channel.name;
        let urls = channel.urls;
        result += name + ',#genre#\n';
        for (const item of urls) {
            let itemName = item.name;
            let itemUrls = item.urls;
            for (const u of itemUrls) {
                result += itemName + ',' + u + '\n';
            }
        }
    }
    return result;
}

// 解析 "省份" 格式 JSON: {data:{list:[{prov, line:[{name, urls:[{line, url}]}]}]}}
function parseLu(content) {
    let result = '';
    let data = JSON.parse(content).data;
    for (const prov of data.list) {
        let provName = prov.prov;
        let lines = prov.line;
        result += provName + ',#genre#\n';
        for (const line of lines) {
            let lineName = line.name;
            let urls = line.urls;
            for (const u of urls) {
                result += lineName + '---' + u.line + ',' + u.url + '\n';
            }
        }
    }
    return result;
}

// 取某个分类下的影片列表 (带缓存)
//   typeId 形如:  "分类名$接口地址[|urlencoded额外headers][&&&封面图模板]"
function getCateData(typeId, timeout) {
    let pic = picUrl;
    if (typeId.indexOf('&&&') > 0) {
        pic = typeId.split('&&&')[1].trim();
        if (pic.indexOf('://') < 0 && webPaths[typeId]) {
            pic = webPaths[typeId] + pic;
        }
        typeId = typeId.split('&&&')[0].trim();
    }
    console.log('webPicUrl: ' + pic);

    let url = typeId.split('$')[1];
    let cateName = typeId.split('$')[0];

    if (!cates[typeId]) {
        cates[typeId] = [];

        // 接口地址后可用 "|key1=val1&key2=val2" 追加自定义请求头 (urlencoded)
        let reqHeaders = headers;
        if (url.indexOf('|') > 0) {
            let headerStr = decodeURIComponent(url.split('|')[1]);
            url = url.split('|')[0];
            for (const h of headerStr.split('&')) {
                if (h.indexOf('=') > 0) {
                    let key = h.split('=')[0];
                    let val = h.split('=')[1];
                    reqHeaders[key] = val;
                }
            }
        }

        let resp = req(url, {
            'method': 'GET',
            'headers': reqHeaders,
            'timeout': timeout || REQ_TIMEOUT
        });
        resp = resp.content.trim();
        // trim() 会去掉末尾换行, 导致 parseM3u 正则匹配不到最后一条频道
        // (parseM3u 正则要求每条 URL 后都有 \n), 这里补一个换行兜底
        resp += '\n';

        // 根据返回内容自动选择解析器
        if (resp.indexOf('#EXTM3U') >= 0) {
            resp = parseM3u(resp, cateName);
        } else if (resp.indexOf('"channel"') > 0 && resp.indexOf('"urls"') > 0) {
            resp = parseFm(resp);
        } else if (resp.indexOf('"datalist"') > 0 && resp.indexOf('"urls"') > 0) {
            resp = parseLu(resp);
        }

        // 逐行解析成影片:  组名行 -> "名称,地址" 行
        let lines = (cateName + '\n' + resp.replace('\r', '')).split('\n');
        let vodName = cateName;
        let playUrl = '';

        for (let i = 0; i < lines.length; i++) {
            let line = lines[i].replace(/\s+/g, '');
            // 组名行: 不含 "://" 且 (不含逗号 或 含 "#genre#")
            if (line != '' && line.indexOf('://') < 0 && (line.indexOf(',') < 0 || line.indexOf('#genre#') > 0)) {
                if (playUrl != '') {
                    let finalPic = resolvePic(pic, vodName, cateName);
                    console.log(vodName + ', ' + finalPic);
                    cates[typeId].push({
                        'vod_id': typeId + '$$$' + cates[typeId].length,
                        'vod_name': vodName,
                        'vod_pic': finalPic,
                        'vod_remarks': '',
                        'type_name': '直播列表',
                        'vod_year': '',
                        'vod_area': '',
                        'vod_actor': '',
                        'vod_director': '',
                        'vod_content': '',
                        'vod_play_from': cateName,
                        'vod_play_url': playUrl
                    });
                }
                vodName = line.split(',')[0].trim();
                playUrl = '';
            } else if (line.indexOf(',') > 0 && /http|rtmp|rtsp|rsp/.test(line)) {
                // 播放地址行: "名称,地址"  -> 拼成 "名称$地址" 并以 '#' 分隔
                let seg = line.split(',');
                if (playUrl != '') {
                    playUrl += '#';
                }
                playUrl += seg[0].trim() + '$' + seg[1].trim();
            }
        }

        // 收尾: 最后一组
        if (playUrl != '') {
            let finalPic = resolvePic(pic, vodName, cateName);
            cates[typeId].push({
                'vod_id': typeId + '$$$' + cates[typeId].length,
                'vod_name': vodName,
                'vod_pic': finalPic,
                'vod_remarks': '',
                'type_name': '直播列表',
                'vod_year': '',
                'vod_area': '',
                'vod_actor': '',
                'vod_director': '',
                'vod_content': '',
                'vod_play_from': cateName,
                'vod_play_url': playUrl
            });
        }
    }
    return cates[typeId];
}

// 解析封面图模板:
//   - 替换 {name} / {cate} 占位符 (urlencoded)
//   - 支持 "<正则>" 占位符: 从 vodName 中用该正则提取第一个捕获组填入
//     (匹配不到时填 'null')
function resolvePic(picTemplate, vodName, cateName) {
    let pic = picTemplate
        .replace('{name}', encodeURIComponent(vodName))
        .replace('{cate}', encodeURIComponent(cateName));
    let lt = pic.indexOf('<');
    let gt = pic.lastIndexOf('>');
    if (lt > -1 && gt > lt) {
        let placeholder = pic.substring(lt, gt + 1);            // 形如 <正则>
        let re = new RegExp(placeholder.replace(/<|>/g, ''));   // 去掉 < > 得到正则体
        let extracted = re.test(vodName) ? vodName.match(re)[1] : 'null';
        pic = pic.replace(placeholder, extracted);
    }
    return pic;
}

// 首页推荐
function homeVod(filter) {
    let list = getCateData(classes[0].type_id);
    return JSON.stringify({
        'list': list
    });
}

// 分类页 (仅第一页返回数据, 其余页空)
function category(tid, page, limit, extend) {
    let list = [];
    if (page == 1) {
        list = getCateData(tid);
    }
    return JSON.stringify({
        'list': list
    });
}

// 详情: 把同一影片的多条线路拆成多播放源
//   仅当分类名带 '!!' 标记时做二次拆分 (播放项里 "名称---线路" 形式)
function detail(ids) {
    let parts = ids.split('$$$');
    let typeId = parts[0];
    let cateName = typeId.split('$')[0];
    let index = parseInt(parts[1]);
    let vod = getCateData(typeId)[index];
    console.log(JSON.stringify(vod));

    if (cateName.indexOf('!!') >= 0) {
        cateName = cateName.replace('!!', '');
        const playUrls = vod.vod_play_url.split('#');
        console.log(JSON.stringify(playUrls));

        let countMap = {};    // 每个剧集名出现次数, 用于同名线路加序号
        let groupMap = {};    // 线路名 -> [剧集$地址, ...]

        for (const playUrl of playUrls) {
            let episode = playUrl.split('$')[0];
            let playFrom = cateName;
            if (episode.indexOf('---') > 0) {
                playFrom = episode.split('---')[1];      // "名称---线路" 中的线路
                episode = episode.split('---')[0];
            }
            if (!countMap.hasOwnProperty(episode)) {
                countMap[episode] = 1;
            } else {
                countMap[episode]++;
            }
            playFrom = cateName + (countMap[episode] > 1 ? ' ' + countMap[episode] : '');

            if (!groupMap.hasOwnProperty(playFrom)) {
                groupMap[playFrom] = [];
            }
            groupMap[playFrom].push(episode + '$' + playUrl.split('$')[1]);
        }

        let playFromList = [];
        let playUrlList = [];
        for (let key in groupMap) {
            playFromList.push(key);
            playUrlList.push(groupMap[key].join('#'));
        }
        vod.vod_play_from = playFromList.join('$$$');
        vod.vod_play_url = playUrlList.join('$$$');
    }

    return JSON.stringify({
        'list': [vod]
    });
}

// 播放: 直接返回原地址, 不走解析
function play(flag, id, vipFlags) {
    return JSON.stringify({
        'parse': 0,
        'url': id
    });
}

// 搜索: 对已接入的 M3U/JSON 源做本地关键字搜索
//   实现思路:
//   1. 大小写不敏感: keyword 和被搜文本都 toLowerCase() 后做子串匹配
//   2. 双层匹配: 既匹配 vod_name (分组名), 也匹配 vod_play_url 里的每个频道名
//      (live2vod 的点播粒度是"分组", 一个分组=一集影片, 组内多频道=多播放线路,
//       所以只搜 vod_name 会漏掉组内的具体频道名, 比如 "CCTV-1" 在 "央视" 分组里)
//   3. 冷启动兜底: 遍历所有"未缓存"的分类调 getCateData() 填充缓存,
//      用 SEARCH_TIMEOUT 短超时 (5s), 某个源挂掉时快速跳过不影响整体搜索;
//      已缓存 (含失败后置空的 []) 不会重试, 避免每次搜索都重试挂掉的源
//   4. 去重: 按"播放地址"去重 —— 同名不同地址都保留 (方便用户挑选线路),
//      地址相同的才去重 (无论频道名相同与否, 同一地址只返回一条)
//   5. 多关键词 AND: keyword 以空格分隔时, 要求每个词都命中
//   6. 命中具体频道时, 把该频道的名称作为 vod_name 返回 (而不是分组名),
//      并把 vod_play_url 裁剪为只含命中的那一条线路, 方便用户直接点播
function search(keyword, quick) {
    let kw = (keyword || '').trim();
    if (!kw) {
        return JSON.stringify({ list: [] });
    }
    // 多关键词 AND 匹配: 空格分隔, 每个词都要包含
    let kws = kw.toLowerCase().split(/\s+/).filter(k => k.length > 0);

    // 检查一段文本是否包含所有关键词 (AND)
    function matchAll(text) {
        if (!text) return false;
        let t = text.toLowerCase();
        for (const k of kws) {
            if (t.indexOf(k) < 0) return false;
        }
        return true;
    }

    // 冷启动兜底: 遍历所有"未缓存"的分类填充缓存 (用较短超时).
    // 某个源挂掉/超时会抛异常被 catch 跳过, 该分类本次搜不到, 不影响其它分类.
    // 已缓存 (含失败后置空的 []) 不会重试, 避免每次搜索都重试挂掉的源.
    for (const cls of classes) {
        if (!cates[cls.type_id]) {
            try {
                getCateData(cls.type_id, SEARCH_TIMEOUT);
            } catch (e) {
                // 单个分类失败 (超时/网络错误) 不影响整体搜索
            }
        }
    }

    let results = [];
    // 按播放地址去重: 同地址只保留一条 (不管频道名是否相同);
    // 同名不同地址都保留, 方便用户在多条线路间挑选
    let seenUrls = new Set();

    for (const typeId in cates) {
        let list = cates[typeId];
        if (!Array.isArray(list)) continue;
        for (const vod of list) {
            let groupName = vod.vod_name || '';
            let playUrl = vod.vod_play_url || '';

            // 优先匹配 vod_play_url 里的每个频道名 (粒度更精确)
            // vod_play_url 格式: "频道名1$地址1#频道名2$地址2#..."
            let episodes = playUrl.split('#');
            let hitEpisodes = [];
            for (const ep of episodes) {
                let parts = ep.split('$');
                let epName = parts[0] || '';
                if (matchAll(epName)) {
                    hitEpisodes.push(ep);
                }
            }

            if (hitEpisodes.length > 0) {
                // 命中了具体频道: 每个命中频道作为独立结果返回
                // 去重 key 用播放地址, 同地址只留一条; 同名不同地址都保留
                for (const ep of hitEpisodes) {
                    let parts = ep.split('$');
                    let epName = parts[0];
                    let epUrl = parts[1] || '';
                    if (!seenUrls.has(epUrl)) {
                        seenUrls.add(epUrl);
                        results.push({
                            vod_id:       vod.vod_id,    // 保持原 id, detail 仍走原分组
                            vod_name:     epName,
                            vod_pic:      vod.vod_pic || picUrl,
                            vod_remarks:  '直播',
                            vod_play_from: vod.vod_play_from,
                            vod_play_url:  ep     // 只返回这一条线路
                        });
                    }
                }
            } else if (matchAll(groupName)) {
                // 没命中具体频道, 但分组名命中了: 返回整个分组
                // 分组级去重 key 用完整 vod_play_url (所有线路地址的组合),
                // 地址组合完全相同才去重
                if (!seenUrls.has(playUrl)) {
                    seenUrls.add(playUrl);
                    results.push({
                        vod_id:       vod.vod_id,
                        vod_name:     groupName,
                        vod_pic:      vod.vod_pic || picUrl,
                        vod_remarks:  '直播',
                        vod_play_from: vod.vod_play_from,
                        vod_play_url:  vod.vod_play_url
                    });
                }
            }
        }
    }

    return JSON.stringify({ list: results });
}

__JS_SPIDER__ = {
    'init': init,
    'home': home,
    'homeVod': homeVod,
    'category': category,
    'detail': detail,
    'play': play,
    'search': search
};
