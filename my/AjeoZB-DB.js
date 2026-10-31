var globalHeaders = [];
var classes = [];
var categories = {};
var picUrl = 'https://d.kstore.dev/download/8043/BJ/bj-2.jpg';
var webPaths = {};
var sourceHeaders = {};
var sourceConfigs = {};
var vodSourceConfigs = {};
var globalHostHeaders = {};
var processedHosts = new Set();

// req 超时 (毫秒). TVBox/CatVod 的 req 支持 timeout 选项 (基于 okhttp call.timeout).
// 防止源挂掉时长时间阻塞搜索; 不支持该选项的引擎会忽略, 无副作用.
var REQ_TIMEOUT = 8000;     // 常规访问超时
var SEARCH_TIMEOUT = 5000;  // 搜索冷启动用更短超时, 保证搜索快速响应, 挂掉的源快速跳过
var LIVE_FILTER_TIMEOUT = 2500;  // 直播源加载时探测 host 可用性的超时 (毫秒)
var liveHostCache = {};          // 本次会话内 host -> 'alive'/'dead', 避免同 host 重复探测

var LIVS_SOURCES = [
    {
      "name": "央卫直播",
      "type": 3,
      "api": "./Py/央卫直播live-ysp.py"
    },
	 {
      "key": "咕噜央视-海豚",
      "name": "📡咕噜央视",
      "type": 3,
      "api": "./Py/咕噜央视.py"
    },
	{
      "name": "裤佬直播",
      "url": "https://gh-proxy.com/https://raw.githubusercontent.com/pyapk/1/refs/heads/main/zby"
    },
    {
      "name": "平台直播",
      "url": "http://47.120.41.246:8025/vip/jar/zb.php",
      "ua": "okhttp/3.12.13",
      "live_filter": true
    },
    {
      "name": "刚哥TV",
      "url": "https://gitee.com/yuan301/tv/raw/master/A/z_v.png"
    },
	{
      "name": "YTV",
      "url": "https://ytv1.ccwu.cc/output/live.m3u"
    },
    {
      "name": "俄罗斯TV",
      "url": "https://ilook.epg.one/5CM5SY98BF24PL/2"
    },
	{
      "name": "咪咕TV",
      "url": "http://zo.gt.tc/o/i/央视卫视js.txt"
    },
    {
      "name": "关注直播（大师）",
      "type": 0,
      "url": "https://cdn09022024.gitlink.org.cn/api/v1/repos/ajeo/k1/raw/my/sczb.txt"
    },
    {
      "name": "私藏音乐（大师）",
      "type": 0,
      "url": "https://cdn09022024.gitlink.org.cn/api/v1/repos/ajeo/k1/raw/my/scMV.txt"
    }
];

function init(inputData) {
    initGlobalHeaders();
    try {
        var configs = LIVS_SOURCES;
        if (configs && configs.length > 0) {
            for (var i = 0; i < configs.length; i++) {
                var config = normalizeConfig(configs[i]);
                if (config.host) continue;
                var typeId = config.name + '$' + config.url;
                var typeName = config.name;
                classes.push({
                    'type_id': typeId,
                    'type_name': typeName
                });
                if (config.headers && Object.keys(config.headers).length > 0) {
                    sourceHeaders[typeId] = config.headers;
                    sourceConfigs[typeId] = {
                        headers: config.headers,
                        play_parse: config.play_parse || false,
                        live_filter: config.live_filter || false
                    };
                    if (config.url) {
                        var hostFromUrl = extractHostFromUrl(config.url);
                        if (hostFromUrl && !processedHosts.has(hostFromUrl)) {
                            addToGlobalHeaders(hostFromUrl, config.headers);
                            processedHosts.add(hostFromUrl);
                        }
                    }
                } else {
                    sourceConfigs[typeId] = {
                        headers: {},
                        play_parse: config.play_parse || false,
                        live_filter: config.live_filter || false
                    };
                }
            }
            return;
        }
    } catch (error) {
        console.error('JSON解析错误:', error);
    }
    var baseUrl = '';
    if (inputData && inputData.indexOf('$$$') > 0) {
        baseUrl = inputData.split('$$$')[0].trim();
        inputData = inputData.split('$$$')[1].trim();
    }
    if (inputData && inputData.indexOf('&&&') > 0) {
        inputData = inputData.split('&&&')[0].trim();
    }
    if (inputData) {
        var parts = inputData.split('#');
        for (var j = 0; j < parts.length; j++) {
            var part = parts[j];
            if (part.indexOf('$') > 0) {
                var typeId = part;
                var typeName = part.split('$')[0];
                if (typeId.indexOf('://') < 0) {
                    typeId = typeId.replace('$', '$' + baseUrl);
                }
                classes.push({
                    'type_id': typeId,
                    'type_name': typeName.replace('!!', '')
                });
            } else {
                var url = part;
                if (url.indexOf('://') < 0) {
                    url = baseUrl + url;
                }
                var requestHeaders = getHeadersForUrl(url);
                try {
                    var response = req(url, {
                        'method': 'GET',
                        'headers': requestHeaders
                    });
                    var data = JSON.parse(response.content);
                    var pathPrefix = url.substring(0, url.lastIndexOf('/') + 1);
                    for (var k = 0; k < data.length; k++) {
                        var item = data[k];
                        var itemName = item.name;
                        var itemUrl = item.url;
                        var itemTypeId = itemName + '$' + (itemUrl.indexOf('://') < 0 ? pathPrefix : '') + itemUrl;
                        classes.push({
                            'type_id': itemTypeId,
                            'type_name': itemName.replace('!!', '')
                        });
                        var normalizedItem = normalizeConfig(item);
                        if (normalizedItem.headers && Object.keys(normalizedItem.headers).length > 0) {
                            sourceHeaders[itemTypeId] = normalizedItem.headers;
                            sourceConfigs[itemTypeId] = normalizedItem;
                        }
                    }
                } catch (error) {
                    console.error('加载二级数据错误:', error);
                }
            }
        }
    }
}

function extractLivesConfig(parsedData) {
    if (Array.isArray(parsedData)) {
        return parsedData;
    }
    if (typeof parsedData === 'object' && parsedData !== null) {
        var livesKey = Object.keys(parsedData).find(key => key.toLowerCase() === 'lives');
        if (livesKey && Array.isArray(parsedData[livesKey])) {
            return parsedData[livesKey];
        }
    }
    return null;
}

function normalizeConfig(config) {
    var normalized = Object.assign({}, config);
    if (config.ua && typeof config.ua === 'string') {
        if (!normalized.headers) {
            normalized.headers = {};
        }
        normalized.headers['User-Agent'] = config.ua;
        delete normalized.ua;
    }
    if (config.header && typeof config.header === 'object') {
        if (!normalized.headers) {
            normalized.headers = {};
        }
        Object.assign(normalized.headers, config.header);
        delete normalized.header;
    }
    return normalized;
}

function extractHostFromUrl(url) {
    try {
        var urlObj = new URL(url);
        return urlObj.host;
    } catch (error) {
        var match = url.match(/:\/\/([^\/]+)/);
        return match ? match[1] : null;
    }
}

// 加载时动态过滤: 探测频道 URL 的 host 是否可用 (结果按 host 缓存, 同 host 只探测一次)
// 探测方式: GET + Range: bytes=0-1 (HEAD 对部分服务器返回 405 会误判, 不用)
// 判定: 2xx/3xx 视为可用 (3xx 为防盗链跳转, 播放器跟随即可), 超时/4xx/5xx 视为失效
// 只在 live_filter=true 的源上启用, 其余源完全不受影响
function checkHostAlive(url) {
    var host;
    try {
        host = new URL(url).host;
    } catch (error) {
        var m = url.match(/:\/\/([^\/]+)/);
        if (!m) return true;  // 无法解析 host, 不剔除
        host = m[1];
    }
    if (liveHostCache[host]) {
        return liveHostCache[host] === 'alive';
    }
    var alive = false;
    try {
        var resp = req(url, {
            'method': 'GET',
            'headers': {
                'Range': 'bytes=0-1',
                'User-Agent': 'okhttp/3.12.13'
            },
            'timeout': LIVE_FILTER_TIMEOUT
        });
        var code = resp && resp.code ? resp.code : 0;
        if (code >= 200 && code < 400) {
            alive = true;
        }
    } catch (error) {
        alive = false;
    }
    liveHostCache[host] = alive ? 'alive' : 'dead';
    return alive;
}

function addToGlobalHeaders(host, headers) {
    if (!host || !headers || Object.keys(headers).length === 0) return;
    var exists = false;
    for (var i = 0; i < globalHeaders.length; i++) {
        if (globalHeaders[i].host === host) {
            exists = true;
            break;
        }
    }
    if (!exists) {
        globalHeaders.push({
            "host": host,
            "header": headers
        });
        globalHostHeaders[host] = headers;
    }
}

function initGlobalHeaders() {
    for (var i = 0; i < globalHeaders.length; i++) {
        var config = globalHeaders[i];
        if (config.host && config.header) {
            globalHostHeaders[config.host] = config.header;
        }
    }
}

function getHeadersForUrl(url) {
    var resultHeaders = {};
    try {
        var urlObj = new URL(url);
        var host = urlObj.host;
        if (globalHostHeaders[host]) {
            resultHeaders = Object.assign({}, globalHostHeaders[host]);
        } else {
            for (var pattern in globalHostHeaders) {
                if (pattern.includes('*') && url.includes(pattern.replace(':*', ''))) {
                    resultHeaders = Object.assign({}, globalHostHeaders[pattern]);
                    break;
                } else if (url.includes(pattern)) {
                    resultHeaders = Object.assign({}, globalHostHeaders[pattern]);
                    break;
                }
            }
        }
    } catch (error) {
        for (var pattern in globalHostHeaders) {
            if (url.includes(pattern.replace(':*', ''))) {
                resultHeaders = Object.assign({}, globalHostHeaders[pattern]);
                break;
            }
        }
    }
    return resultHeaders;
}

function getPlayHeaders(playUrl, sourceConfig) {
    var playHeaders = getHeadersForUrl(playUrl);
    var hasGlobalHeaders = Object.keys(playHeaders).length > 0;
    if (!hasGlobalHeaders && sourceConfig && sourceConfig.headers && Object.keys(sourceConfig.headers).length > 0) {
        playHeaders = Object.assign({}, playHeaders, sourceConfig.headers);
    }
    return playHeaders;
}

// 咪咕直播中转域名: "捡的"(tv.txt) 里的频道地址都是 http://migu.qq163gmail.eu.org/<频道id>
// 该地址不是直链, 而是"动态签名入口": 服务器按请求者 IP + 当前时间生成
// msisdn/timestamp/SecurityKey/encrypt 等签名参数, 302 跳转到带签名的咪咕官方
// m3u8 (index.m3u8 -> 01.m3u8 -> ts 分片, 每层签名自包含在文本内).
// 签名有时效 (分钟级, 绑定请求 IP 与时间), 所以必须"每次点播时"即时请求入口
// 拿新签名, 不能把入口当直链缓存, 也不能把某次 302 得到的旧地址缓存播放.
function isMiguRedirectUrl(url) {
    return url.indexOf('migu.qq163gmail.eu.org') >= 0;
}

// 实时解析 302 签名直链: 请求入口, 取跟随 302 后的最终签名 m3u8 地址
//   resp.url: TVBox/CatVod 引擎 req 默认自动跟随 302, 返回的 url 为最终地址
//   resp.header: 兜底解析 location (个别引擎未自动跟随)
//   失败/拿不到最终地址: 返回原地址, 不改变原播放流程
function resolveSignedUrl(url, headers) {
    try {
        var resp = req(url, {
            'method': 'GET',
            'headers': headers || {},
            'timeout': REQ_TIMEOUT
        });
        if (!resp) return url;
        // 引擎自动跟随 302: resp.url 即带签名的 index.m3u8 地址
        if (resp.url && resp.url.indexOf('://') > 0 && resp.url != url) {
            return resp.url;
        }
        // 兜底: 从响应头手动取 location
        var loc = '';
        if (resp.header) {
            loc = resp.header['location'] || resp.header['Location'] || '';
        }
        if (loc) {
            return loc.indexOf('://') > 0 ? loc : url;
        }
    } catch (error) {
        console.error('解析咪咕签名链接失败:', error);
    }
    return url;
}

function home(param) {
    return JSON.stringify({
        'class': classes,
        'filters': null
    });
}

function homeVod(param) {
    if (classes.length === 0) return JSON.stringify({ 'list': [] });
    var data = getCategoryData(classes[0].type_id);
    return JSON.stringify({
        'list': data
    });
}

function category(categoryId, page, filter, extend) {
    var data = [];
    if (page == 1) {
        data = getCategoryData(categoryId);
    }
    return JSON.stringify({
        'list': data
    });
}

function getCategoryData(categoryId, timeout) {
    var imageUrl = picUrl;
    var urlPart = categoryId.split('$')[1];
    var namePart = categoryId.split('$')[0];

    if (!categories[categoryId]) {
        categories[categoryId] = [];

        var requestHeaders = getHeadersForUrl(urlPart);
        if (sourceHeaders[categoryId] && Object.keys(sourceHeaders[categoryId]).length > 0) {
            requestHeaders = Object.assign({}, requestHeaders, sourceHeaders[categoryId]);
        }

        if (urlPart.indexOf('|') > 0) {
            var paramsStr = decodeURIComponent(urlPart.split('|')[1]);
            urlPart = urlPart.split('|')[0];
            var params = paramsStr.split('&');
            for (var l = 0; l < params.length; l++) {
                var param = params[l];
                if (param.indexOf('=') > 0) {
                    var key = param.split('=')[0];
                    var value = param.split('=')[1];
                    requestHeaders[key] = value;
                }
            }
        }

        try {
            var response = req(urlPart, {
                'method': 'GET',
                'headers': requestHeaders,
                'timeout': timeout || REQ_TIMEOUT
            });
            var responseContent = response.content.trim();
            // trim() 会去掉末尾换行, 导致 parseM3u 正则匹配不到最后一条频道
            // (parseM3u 正则要求每条 URL 后都有 \n), 这里补一个换行兜底
            responseContent += '\n';
            var parsedContent = '';
            
            if (responseContent.indexOf('#EXTM3U') >= 0) {
                parsedContent = parseM3u(responseContent, namePart);
            } else if (responseContent.indexOf('"channel"') > 0 && responseContent.indexOf('"urls"') > 0) {
                parsedContent = parseFm(responseContent);
            } else if (responseContent.indexOf('"datalist"') > 0 && responseContent.indexOf('"urls"') > 0) {
                parsedContent = parseList(responseContent);
            } else {
                parsedContent = responseContent;
            }
            
            parseContent(parsedContent, categoryId, namePart, imageUrl);
            
        } catch (error) {
            console.error('获取分类数据失败:', error, '分类ID:', categoryId);
        }
    }
    
    return categories[categoryId];
}

function parseContent(content, categoryId, typeName, imageUrl) {
    var lines = (typeName + '\n' + content.replace('\r', '')).split('\n');
    var currentCategory = typeName;
    var currentUrls = '';
    
    for (var m = 0; m < lines.length; m++) {
        var line = lines[m].replace(/\s+/g, '');
        
        if (line != '' && line.indexOf('://') < 0 && (line.indexOf(',') < 0 || line.indexOf('#genre#') > 0)) {
            if (currentUrls != '') {
                saveCategoryItem(categoryId, currentCategory, currentUrls, typeName, imageUrl);
            }
            currentCategory = line.split(',')[0].trim();
            currentUrls = '';
        } else if (line.indexOf(',') > 0 && /http|rtmp|rtsp|rsp/.test(line)) {
            var parts = line.split(',');
            var channelName = parts[0].trim();
            var channelUrl = parts[1].trim();
            
            // 加载时动态过滤: 开了 live_filter 的源 (平台直播), 探测频道 host 可用性,
            // 失效 host (超时/4xx/5xx) 的频道在列表加载时直接剔除, 不再显示
            if (channelUrl && sourceConfigs[categoryId] && sourceConfigs[categoryId].live_filter) {
                if (!checkHostAlive(channelUrl)) {
                    continue;
                }
            }
            
            if (channelUrl && sourceHeaders[categoryId] && Object.keys(sourceHeaders[categoryId]).length > 0) {
                var secondaryHost = extractHostFromUrl(channelUrl);
                if (secondaryHost && !processedHosts.has(secondaryHost)) {
                    addToGlobalHeaders(secondaryHost, sourceHeaders[categoryId]);
                    processedHosts.add(secondaryHost);
                }
            }
            
            if (currentUrls != '') {
                currentUrls += '#';
            }
            currentUrls += channelName + '$' + channelUrl;
        }
    }
    
    if (currentUrls != '') {
        saveCategoryItem(categoryId, currentCategory, currentUrls, typeName, imageUrl);
    }
    
    return lines;
}

function saveCategoryItem(categoryId, categoryName, urls, typeName, imageUrl) {
    var processedImageUrl = picUrl;
    var vodId = categoryId + '$$$' + categories[categoryId].length;
    vodSourceConfigs[vodId] = {
        sourceHeaders: sourceHeaders[categoryId] || {},
        sourceConfig: sourceConfigs[categoryId] || {},
        categoryId: categoryId
    };
    
    var item = {
        'vod_id': vodId,
        'vod_name': categoryName,
        'vod_pic': processedImageUrl,
        'vod_remarks': '',
        'type_name': '',
        'vod_year': '',
        'vod_area': '',
        'vod_actor': '',
        'vod_director': '',
        'vod_content': '',
        'vod_play_from': typeName,
        'vod_play_url': urls
    };
    categories[categoryId].push(item);
}

function parseM3u(content, categoryName) {
    var result = {};
    var regex = /(#EXTINF:.+?),([^,]+?)\s*\n(.+?)\s*\n/g;
    var match;
    while ((match = regex.exec(content)) !== null) {
        var infTag = match[1];
        var name = match[2];
        var url = match[3];
        if (!name || !url || name == '' || url == '') continue;
        name = name.trim();
        url = url.trim();
        var group = categoryName;
        var groupRegex = /group-title="(.*?)"/;
        if (groupRegex.test(infTag)) {
            group = infTag.match(groupRegex)[1];
        }
        if (!result[group]) result[group] = [];
        result[group].push(name + ',' + url);
    }
    var output = '';
    for (var group in result) {
        if (result.hasOwnProperty(group)) {
            output += group + '\n';
            result[group].forEach(item => output += item + '\n');
        }
    }
    return output;
}

function parseFm(content) {
    var output = '';
    try {
        var data = JSON.parse(content);
        data.forEach(item => {
            var channelName = item.name;
            var urls = item.urls;
            output += channelName + ',#genre#\n';
            urls.forEach(urlItem => {
                var itemName = urlItem.name;
                urlItem.datalist.forEach(url => {
                    output += itemName + ',' + url + '\n';
                });
            });
        });
    } catch (error) {
        console.error('解析Fm数据错误:', error);
    }
    return output;
}

function parseList(content) {
    var output = '';
    try {
        var data = JSON.parse(content).data;
        data.list.forEach(item => {
            var channelName = item.prov;
            var programs = item.list;
            output += channelName + ',#genre#\n';
            programs.forEach(program => {
                var programName = program.name;
                program.datalist.forEach(urlItem => {
                    output += programName + ' ===>>> ' + urlItem.vod_play_from + ',' + urlItem.vod_play_url + '\n';
                });
            });
        });
    } catch (error) {
        console.error('解析List数据错误:', error);
    }
    return output;
}

function detail(detailId) {
    var parts = detailId.split('$$$');
    var categoryId = parts[0];
    var index = parseInt(parts[1]);

    if (!categories[categoryId] || !categories[categoryId][index]) {
        return JSON.stringify({ 'list': [] });
    }

    var detailData = categories[categoryId][index];
    var itemId = categoryId.split('$')[0];

    // 搜索结果: vod_id 带频道序号 (parts[2]), 只返回该序号的单条频道,
    // 避免播放整个分组的第一条线路. 手动构造新对象, 不修改缓存里的原 vod.
    if (parts.length >= 3 && detailData) {
        var epIndex = parseInt(parts[2]);
        var episodes = detailData.vod_play_url.split('#');
        var ep = episodes[epIndex];
        if (ep) {
            var v = {
                'vod_id':         detailId,
                'vod_name':       ep.split('$')[0],
                'vod_pic':        detailData.vod_pic || picUrl,
                'vod_remarks':    detailData.vod_remarks || '',
                'type_name':      detailData.type_name || '',
                'vod_year':       detailData.vod_year || '',
                'vod_area':       detailData.vod_area || '',
                'vod_actor':      detailData.vod_actor || '',
                'vod_director':   detailData.vod_director || '',
                'vod_content':    detailData.vod_content || '',
                'vod_play_from':  detailData.vod_play_from,
                'vod_play_url':   ep
            };
            return JSON.stringify({ 'list': [v] });
        }
    }

    if (itemId.indexOf('!!') >= 0) {
        itemId = itemId.replace('!!', '');
        var urls = detailData.vod_play_url.split('#');
        var countMap = {};
        var groupMap = {};
        
        urls.forEach(url => {
            var namePart = url.split('$')[0];
            var displayName = itemId;
            
            if (namePart.indexOf(' ===>>> ') > 0) {
                displayName = namePart.split(' ===>>> ')[1];
                namePart = namePart.split(' ===>>> ')[0];
            }
            
            countMap[namePart] = (countMap[namePart] || 0) + 1;
            displayName = itemId + (countMap[namePart] > 1 ? ' ' + countMap[namePart] : '');
            
            if (!groupMap[displayName]) groupMap[displayName] = [];
            groupMap[displayName].push(namePart + '$' + url.split('$')[1]);
        });
        
        var groupNames = Object.keys(groupMap);
        var groupUrls = groupNames.map(name => groupMap[name].join('#'));
        
        detailData.vod_play_from = groupNames.join('$$$');
        detailData.vod_play_url = groupUrls.join('$$$');
    }
    
    return JSON.stringify({
        'list': [detailData]
    });
}

function play(playId, playUrl, param) {
    var parse = 0;
    var sourceConfig = null;
    try {
        if (vodSourceConfigs[playId]) {
            var vodConfig = vodSourceConfigs[playId];
            sourceConfig = vodConfig.sourceConfig;
            if (vodConfig.sourceConfig && vodConfig.sourceConfig.play_parse !== undefined) {
                parse = vodConfig.sourceConfig.play_parse ? 1 : 0;
            }
        }

        var playHeaders = getPlayHeaders(playUrl, sourceConfig);

        // 咪咕 302 签名中转: 每次点播实时请求入口, 拿带签名的最终 m3u8 直链,
        // 避免播放器把入口当直链或缓存旧签名地址导致失效; 解析失败兜底返回原地址
        if (isMiguRedirectUrl(playUrl)) {
            var resolvedUrl = resolveSignedUrl(playUrl, playHeaders);
            if (resolvedUrl && resolvedUrl.indexOf('://') > 0) {
                playUrl = resolvedUrl;
            }
        }
    } catch (e) {
        console.error('play() 异常:', e);
    }

    return JSON.stringify({
        'parse': parse,
        'url': playUrl,
        'header': playHeaders,
        'js': '',
        'extra': {}
    });
}

// 搜索: 对已接入的 M3U/JSON 源做本地关键字搜索
//   实现思路:
//   1. 大小写不敏感: keyword 和被搜文本都 toLowerCase() 后做子串匹配
//   2. 双层匹配: 既匹配 vod_name (分组名), 也匹配 vod_play_url 里的每个频道名
//      (专属直播的点播粒度是"分组", 一个分组=一集影片, 组内多频道=多播放线路,
//       所以只搜 vod_name 会漏掉组内的具体频道名, 比如 "CCTV-1" 在 "央视" 分组里)
//   3. 冷启动兜底: 遍历所有"未缓存"的分类调 getCategoryData() 填充缓存,
//      用 SEARCH_TIMEOUT 短超时 (5s), 某个源挂掉时快速跳过不影响整体搜索;
//      已缓存 (含失败后置空的 []) 不会重试, 避免每次搜索都重试挂掉的源
//   4. 去重: 按"名称+播放地址"组合去重
//      - 名称完全相同 且 链接完全相同 -> 去重 (完全重复的条目)
//      - 名称相同 但 链接不同 -> 保留 (不同线路, 让用户挑选)
//      - 名称不同 但 链接相同 -> 保留 (同链接但命名不同, 搜索命中不同关键词都能搜到)
//   5. 连续关键字匹配: 把用户输入作为一个整体 (含空格) 做大小写不敏感子串匹配,
//      只要频道名/分组名"包含这段连续字符"就算命中, 不再按空格拆分做 AND 导致结果太少
//   6. 命中具体频道时, 把该频道的名称作为 vod_name 返回 (而不是分组名),
//      并把 vod_play_url 裁剪为只含命中的那一条线路, 方便用户直接点播
function search(keyword, param) {
    var kw = (keyword || '').trim();
    if (!kw) {
        return JSON.stringify({ 'list': [] });
    }
    // 连续关键字匹配: 把用户输入作为一个整体 (含空格、中文、数字) 做
    // 大小写不敏感子串匹配. 只要频道名/分组名里"包含这段连续字符"
    // 就算命中; 不再按空格拆分做 AND, 避免"中央 电视台"搜不到
    // "中央电视台" (名称里没空格) 这种实际是连续子串的情况.
    var kwLower = kw.toLowerCase();
    var kwCompact = kwLower.replace(/\s+/g, '');

    function matchContinuous(text) {
        if (!text) return false;
        var t = text.toLowerCase();
        if (t.indexOf(kwLower) >= 0) return true;
        var tCompact = t.replace(/\s+/g, '');
        if (tCompact.indexOf(kwCompact) >= 0) return true;
        return false;
    }

    // 冷启动兜底: 遍历所有"未缓存"的分类填充缓存 (用较短超时).
    // 某个源挂掉/超时会抛异常被 catch 跳过, 该分类本次搜不到, 不影响其它分类.
    // 已缓存 (含失败后置空的 []) 不会重试, 避免每次搜索都重试挂掉的源.
    for (var i = 0; i < classes.length; i++) {
        var typeId = classes[i].type_id;
        if (!categories[typeId]) {
            try {
                getCategoryData(typeId, SEARCH_TIMEOUT);
            } catch (e) {
                // 单个分类失败 (超时/网络错误) 不影响整体搜索
            }
        }
    }

    var results = [];
    // 按"名称||播放地址"组合去重:
    //   - 名称完全相同 且 地址相同 -> 去重 (完全重复的条目)
    //   - 名称相同 但 地址不同 -> 保留 (不同线路, 让用户挑选)
    //   - 名称不同 但 地址相同 -> 保留 (同一链接命名不同, 搜索不同关键词都能搜到)
    var seenPairs = new Set();

    function dedupeKey(name, url) {
        return (name || '') + '\x1f' + (url || '');
    }

    for (var categoryId in categories) {
        var list = categories[categoryId];
        if (!Array.isArray(list)) continue;

        for (var j = 0; j < list.length; j++) {
            var vod = list[j];
            var groupName = vod.vod_name || '';
            var playUrl = vod.vod_play_url || '';

            // 优先匹配 vod_play_url 里的每个频道名 (粒度更精确)
            // vod_play_url 格式: "频道名1$地址1#频道名2$地址2#..."
            var episodes = playUrl.split('#');
            var hitEpisodes = [];
            for (var k = 0; k < episodes.length; k++) {
                var epSeg = episodes[k].split('$');
                var epName = epSeg[0] || '';
                if (matchContinuous(epName)) {
                    hitEpisodes.push(episodes[k]);
                }
            }

            if (hitEpisodes.length > 0) {
                // 命中了具体频道: 每个命中频道作为独立结果返回
                // 去重 key = 频道名 || 播放地址, 保证名称相同+地址相同才去重
                for (var m = 0; m < hitEpisodes.length; m++) {
                    var ep = hitEpisodes[m];
                    var epParts = ep.split('$');
                    var epName = epParts[0];
                    var epUrl = epParts[1] || '';
                    var key = dedupeKey(epName, epUrl);
                    if (!seenPairs.has(key)) {
                        seenPairs.add(key);
                        // vod_id 追加频道序号 ($$$epIndex), 让 detail 能定位到具体频道
                        // 而非整个分组; 同时同分组内不同频道的 vod_id 各不相同,
                        // 避免被盒子按 id 去重导致同名不同地址只显示一个
                        var epIndex = episodes.indexOf(ep);
                        results.push({
                            'vod_id':        vod.vod_id + '$$$' + epIndex,
                            'vod_name':      epName,
                            'vod_pic':       vod.vod_pic || picUrl,
                            'vod_remarks':   '直播',
                            'vod_play_from': vod.vod_play_from,
                            'vod_play_url':  ep
                        });
                    }
                }
            } else if (matchContinuous(groupName)) {
                // 没命中具体频道, 但分组名命中了: 返回整个分组
                // 分组级去重 key = 分组名 || 完整 playUrl 组合
                var gkey = dedupeKey(groupName, playUrl);
                if (!seenPairs.has(gkey)) {
                    seenPairs.add(gkey);
                    results.push({
                        'vod_id':        vod.vod_id,
                        'vod_name':      groupName,
                        'vod_pic':       vod.vod_pic || picUrl,
                        'vod_remarks':   '直播',
                        'vod_play_from': vod.vod_play_from,
                        'vod_play_url':  vod.vod_play_url
                    });
                }
            }
        }
    }

    return JSON.stringify({ 'list': results });
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