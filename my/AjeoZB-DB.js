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
      "name": "橘汁直播",
      "url": "juzi_live",
      "juzi_live": true
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
    // 加载 tv.txt 建频道映射 (橘汁直播兜底用: 换链失败时用咪咕中转地址)
    try {
        var tvResp = req('http://tv.qq163gmail.eu.org/tv.txt', { 'timeout': 5000 });
        if (tvResp && tvResp.content) {
            var tvLines = tvResp.content.split('\n');
            for (var ti = 0; ti < tvLines.length; ti++) {
                var tl = tvLines[ti].trim();
                if (!tl || tl.indexOf('#') === 0) continue;
                var ci = tl.indexOf(',');
                if (ci < 0) continue;
                var cname = tl.substring(0, ci).trim();
                var curl = tl.substring(ci + 1).trim();
                if (cname && curl) TV_MAP[cname] = curl;
            }
        }
    } catch (e) {}
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
                // 橘汁直播: 内置频道表, 不进网络加载, 不套 host/UA 过滤
                if (config.juzi_live) {
                    initJuziLive(typeId, typeName);
                    continue;
                }
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

        // 橘汁直播: 每次点播实时签名换链 (登录 token -> 签名头/签名体 -> 服务器返回
        // 中转地址 -> 302 央视官方签名 m3u8), 播放时带 UA okhttp/3.12.1
        if (playUrl && playUrl.indexOf('juzi://') === 0) {
            var jzUrl = jzResolveLive(playUrl);
            if (jzUrl && jzUrl.indexOf('://') > 0) {
                playUrl = jzUrl;
                playHeaders = { 'User-Agent': JUZI_UA };
            }
        }

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

// ============ 橘汁直播集成模块 (追加到 AjeoZB-DB.js 末尾使用) ============
// 协议: 登录(register/login) 拿 token -> 每次播放实时签名换链
// 换链: POST /api/proto/v5/videoUsableUrl, body=protobuf(AES-ECB(SAFECODE)(mapkv+ts) 分段包装)
// 头: publicParams=AES-CBC(NATIVE_K, 设备JSON) hex, 设备JSON 内含 sig(RSA2 加密 ts+rnd+VC) + sig2/sig3(AES(SAFE) 加密 ts+rnd 切片)
// 响应: protobuf 里 fn1/wt0=code(200), fn3/wt2=data, data 内含 https URL (全文正则提取, ASCII 无损)
// 播放链: 换链返回 token 中转地址 -> 302 -> 央视官方签名 m3u8 (带 UA okhttp/3.12.1)

// ---------- 常量 ----------
var JUZI_HOST = 'https://juziapp.hzhcbkj.cn';
var JUZI_UA = 'okhttp/3.12.1';
var JUZI_VC = '3024';
var JUZI_PKG = 'com.mxj.wylcjbxyx';
var JUZI_NATIVE_K = 'ed5fdsgucxumegqa';
var JUZI_SAFE = 'OC1A06E197EF10CF3F6058CA7A803B5E';
var JUZI_SAFECODE = 'OW1WBLFZCLJ0WTNJQMRSZ2DYSGNBPT0=';
var JUZI_RSA2_N = 'a9f44938c0895002dc059ee05196c162a30dadafee1439c88678d29b63b9cbef87ad52a51be9fbe939238784511f69695fc14a4e075ef1dc910bdcda35f677e309e558ad83e3949720a2a5161ffb5f21f140416bedc4120194a6b3921c3c7770a1cac5a679646290aaa406c551638a2a34fba3e2c8e6e99ba5b74538238a6b45';
var JUZI_RSA2_E = 65537;
var JUZI_UDID = 'ABEB9828C0CBCBB9';
var JUZI_USER = 'tv_abeb9828c0';
var JUZI_PASS = 'da06655827ef97e37c38f330833d2ab1';
var jzToken = '4bbbca33e1ac443009d2f1422d4edc9e';
var jzLoginTried = true;
// tv.txt 频道映射 (频道名 -> 咪咕中转地址), init() 里填充, 橘汁换链失败时兜底
var TV_MAP = {};

// ---------- base64 ----------
var JUZI_B64C = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
function jzB64Encode(bytes) {
    var out = '';
    for (var i = 0; i < bytes.length; i += 3) {
        var b0 = bytes[i], b1 = i + 1 < bytes.length ? bytes[i + 1] : -1,
            b2 = i + 2 < bytes.length ? bytes[i + 2] : -1;
        out += JUZI_B64C.charAt(b0 >> 2);
        out += JUZI_B64C.charAt(((b0 & 3) << 4) | (b1 >= 0 ? b1 >> 4 : 0));
        out += b1 >= 0 ? JUZI_B64C.charAt(((b1 & 15) << 2) | (b2 >= 0 ? b2 >> 6 : 0)) : '=';
        out += b2 >= 0 ? JUZI_B64C.charAt(b2 & 63) : '=';
    }
    return out;
}
function jzB64Decode(s) {
    var out = [];
    var buf = 0, bits = 0;
    for (var i = 0; i < s.length; i++) {
        var c = s.charAt(i);
        if (c === '=') break;
        var idx = JUZI_B64C.indexOf(c);
        if (idx < 0) continue;
        buf = (buf << 6) | idx;
        bits += 6;
        if (bits >= 8) {
            bits -= 8;
            out.push((buf >> bits) & 0xFF);
        }
    }
    return out;
}
function jzStrToBytes(s) {
    var out = [];
    for (var i = 0; i < s.length; i++) out.push(s.charCodeAt(i) & 255);
    return out;
}
function jzBytesToStr(bytes) {
    var out = '';
    for (var i = 0; i < bytes.length; i++) out += String.fromCharCode(bytes[i]);
    return out;
}
function jzHexToBytes(h) {
    var out = [];
    for (var i = 0; i < h.length; i += 2) out.push(parseInt(h.substr(i, 2), 16));
    return out;
}
function jzBytesToHex(bytes) {
    var out = '';
    for (var i = 0; i < bytes.length; i++) {
        var t = bytes[i].toString(16);
        out += t.length < 2 ? '0' + t : t;
    }
    return out;
}

// ---------- AES ----------
// sbox 硬编码 (启动时不再暴力计算, 避免 TVBox Rhino 引擎慢导致超时)
var JZ_SBOX = [99,124,119,123,242,107,111,197,48,1,103,43,254,215,171,118,202,130,201,125,250,89,71,240,173,212,162,175,156,164,114,192,183,253,147,38,54,63,247,204,52,165,229,241,113,216,49,21,4,199,35,195,24,150,5,154,7,18,128,226,235,39,178,117,9,131,44,26,27,110,90,160,82,59,214,179,41,227,47,132,83,209,0,237,32,252,177,91,106,203,190,57,74,76,88,207,208,239,170,251,67,77,51,133,69,249,2,127,80,60,159,168,81,163,64,143,146,157,56,245,188,182,218,33,16,255,243,210,205,12,19,236,95,151,68,23,196,167,126,61,100,93,25,115,96,129,79,220,34,42,144,136,70,238,184,20,222,94,11,219,224,50,58,10,73,6,36,92,194,211,172,98,145,149,228,121,231,200,55,109,141,213,78,169,108,86,244,234,101,122,174,8,186,120,37,46,28,166,180,198,232,221,116,31,75,189,139,138,112,62,181,102,72,3,246,14,97,53,87,185,134,193,29,158,225,248,152,17,105,217,142,148,155,30,135,233,206,85,40,223,140,161,137,13,191,230,66,104,65,153,45,15,176,84,187,22];
function jzAesSbox() {
    return JZ_SBOX;
}
function jzGmul(a, b) {
    var r = 0;
    while (b) {
        if (b & 1) r ^= a;
        a = (a << 1) ^ (a & 0x80 ? 0x11B : 0);
        a &= 0xFF;
        b >>= 1;
    }
    return r;
}
function jzKeyExpansion(key) {
    var Nk = key.length / 4, Nr = Nk + 6, sbox = jzAesSbox();
    var w = [];
    var i;
    for (i = 0; i < Nk; i++) {
        w[i] = [key[4 * i], key[4 * i + 1], key[4 * i + 2], key[4 * i + 3]];
    }
    var rcon = 1;
    for (i = Nk; i < 4 * (Nr + 1); i++) {
        var t = w[i - 1].slice(0);
        if (i % Nk === 0) {
            t = [sbox[t[1]], sbox[t[2]], sbox[t[3]], sbox[t[0]]];
            t[0] ^= rcon;
            rcon = jzGmul(rcon, 2);
        } else if (Nk > 6 && i % Nk === 4) {
            t = [sbox[t[0]], sbox[t[1]], sbox[t[2]], sbox[t[3]]];
        }
        var wm = w[i - Nk];
        w[i] = [t[0] ^ wm[0], t[1] ^ wm[1], t[2] ^ wm[2], t[3] ^ wm[3]];
    }
    return w;
}
function jzAesEncryptBlock(block, w, Nr) {
    var sbox = jzAesSbox();
    var state = block.slice(0);
    function addRoundKey(round) {
        for (var c = 0; c < 4; c++)
            for (var r = 0; r < 4; r++)
                state[r + 4 * c] ^= w[round * 4 + c][r];
    }
    function subBytes() {
        for (var i = 0; i < 16; i++) state[i] = sbox[state[i]];
    }
    function shiftRows() {
        var t = state.slice(0);
        for (var r = 0; r < 4; r++)
            for (var c = 0; c < 4; c++)
                state[r + 4 * c] = t[r + 4 * ((c + r) % 4)];
    }
    function mixColumns() {
        for (var c = 0; c < 4; c++) {
            var a = state.slice(4 * c, 4 * c + 4);
            state[4 * c + 0] = jzGmul(a[0], 2) ^ jzGmul(a[1], 3) ^ a[2] ^ a[3];
            state[4 * c + 1] = a[0] ^ jzGmul(a[1], 2) ^ jzGmul(a[2], 3) ^ a[3];
            state[4 * c + 2] = a[0] ^ a[1] ^ jzGmul(a[2], 2) ^ jzGmul(a[3], 3);
            state[4 * c + 3] = jzGmul(a[0], 3) ^ a[1] ^ a[2] ^ jzGmul(a[3], 2);
        }
    }
    addRoundKey(0);
    for (var round = 1; round < Nr; round++) {
        subBytes(); shiftRows(); mixColumns(); addRoundKey(round);
    }
    subBytes(); shiftRows(); addRoundKey(Nr);
    return state;
}
function jzAes(keyBytes, dataBytes, mode, ivBytes) {
    var Nk = keyBytes.length / 4, Nr = Nk + 6;
    var w = jzKeyExpansion(keyBytes);
    var out = [];
    var prev = null;
    if (mode === 'CBC') prev = ivBytes.slice(0);
    for (var off = 0; off < dataBytes.length; off += 16) {
        var block = dataBytes.slice(off, off + 16);
        while (block.length < 16) block.push(0);
        if (mode === 'CBC') {
            for (var i = 0; i < 16; i++) block[i] ^= prev[i];
        }
        var enc = jzAesEncryptBlock(block, w, Nr);
        if (mode === 'CBC') prev = enc;
        for (var j = 0; j < 16; j++) out.push(enc[j]);
    }
    return out;
}
function jzPkcs7(dataBytes, blockSize) {
    var pad = blockSize - (dataBytes.length % blockSize);
    var out = dataBytes.slice(0);
    for (var i = 0; i < pad; i++) out.push(pad);
    return out;
}

// ---------- RSA (base 2^16 LE 大数) ----------
function jzShiftLeft(a, s) {
    if (s === 0) return a.slice(0);
    var out = [], carry = 0;
    for (var i = 0; i < a.length; i++) {
        var v = (a[i] << s) | carry;
        carry = a[i] >>> (16 - s);
        out.push(v & 0xFFFF);
    }
    if (carry) out.push(carry & 0xFFFF);
    return out;
}
function jzShiftRight(a, s) {
    if (s === 0) return a.slice(0);
    var out = [], carry = 0;
    for (var i = a.length - 1; i >= 0; i--) {
        var v = (a[i] >>> s) | (carry << (16 - s));
        carry = a[i] & ((1 << s) - 1);
        out[i] = v & 0xFFFF;
    }
    return out;
}
function jzMul(a, b) {
    var c = new Array(a.length + b.length);
    for (var i = 0; i < c.length; i++) c[i] = 0;
    for (var i = 0; i < a.length; i++) {
        var carry = 0;
        for (var j = 0; j < b.length; j++) {
            var t = c[i + j] + a[i] * b[j] + carry;
            carry = Math.floor(t / 65536);
            c[i + j] = t - carry * 65536;
        }
        var j2 = i + b.length;
        while (carry) {
            var t2 = c[j2] + carry;
            carry = Math.floor(t2 / 65536);
            c[j2] = t2 - carry * 65536;
            j2++;
        }
    }
    while (c.length > 1 && c[c.length - 1] === 0) c.pop();
    return c;
}
function jzCmpBig(a, b) {
    var la = a.length, lb = b.length;
    for (var i = Math.max(la, lb) - 1; i >= 0; i--) {
        var va = i < la ? a[i] : 0, vb = i < lb ? b[i] : 0;
        if (va !== vb) return va > vb ? 1 : -1;
    }
    return 0;
}
function jzMulWord(vn, qhat) {
    var out = new Array(vn.length + 1);
    var carry = 0;
    for (var i = 0; i < vn.length; i++) {
        var t = qhat * vn[i] + carry;
        out[i] = t & 0xFFFF;
        carry = Math.floor(t / 65536);
    }
    out[vn.length] = carry & 0xFFFF;
    return out;
}
function jzDivmod(num, den) {
    var n = den.length, m = num.length - n;
    if (m < 0) return { q: [0], r: num.slice(0) };
    var s = 0, top = den[n - 1];
    while (top < 0x8000) { top <<= 1; s++; }
    var vn = jzShiftLeft(den, s);
    var un = jzShiftLeft(num, s);
    while (un.length < m + n + 1) un.push(0);
    var q = new Array(m + 1);
    for (var j = m; j >= 0; j--) {
        var hi = un[j + n] * 65536 + un[j + n - 1];
        var qhat = Math.floor(hi / vn[n - 1]);
        if (qhat > 65535) qhat = 65535;
        var P = jzMulWord(vn, qhat);
        while (jzCmpBig(P, un.slice(j, j + n + 1)) > 0) {
            qhat--;
            P = jzMulWord(vn, qhat);
        }
        var borrow = 0;
        for (var is = 0; is <= n; is++) {
            var tt = un[j + is] - P[is] - borrow;
            if (tt < 0) { tt += 65536; borrow = 1; } else { borrow = 0; }
            un[j + is] = tt & 0xFFFF;
        }
        q[j] = qhat;
    }
    var r = jzShiftRight(un.slice(0, n), s);
    while (r.length > 1 && r[r.length - 1] === 0) r.pop();
    return { q: q, r: r };
}
function jzModPow(base, exp, mod) {
    var result = [1];
    var b = base.slice(0);
    while (exp > 0) {
        if (exp & 1) result = jzDivmod(jzMul(result, b), mod).r;
        exp >>= 1;
        if (exp > 0) b = jzDivmod(jzMul(b, b), mod).r;
    }
    return result;
}
function jzRsaEncrypt(nHex, msgBytes) {
    var nBytes = jzHexToBytes(nHex);
    var k = nBytes.length;
    var msgLen = msgBytes.length;
    var psLen = k - 3 - msgLen;
    var block = new Array(k);
    block[0] = 0; block[1] = 2;
    for (var i = 0; i < psLen; i++) block[2 + i] = 1 + Math.floor(Math.random() * 254);
    block[2 + psLen] = 0;
    for (var j = 0; j < msgLen; j++) block[k - msgLen + j] = msgBytes[j];
    var words = [];
    for (var w = k - 2; w >= 0; w -= 2) {
        words.push((block[w] << 8) | block[w + 1]);
    }
    var nWords = [];
    for (var w2 = nBytes.length - 2; w2 >= 0; w2 -= 2) {
        nWords.push((nBytes[w2] << 8) | nBytes[w2 + 1]);
    }
    var c = jzModPow(words, JUZI_RSA2_E, nWords);
    var out = new Array(k);
    for (var oi = 0; oi < k; oi++) out[oi] = 0;
    for (var wi = 0; wi < c.length; wi++) {
        out[k - 2 - wi * 2] = (c[wi] >> 8) & 0xFF;
        out[k - 1 - wi * 2] = c[wi] & 0xFF;
    }
    return out;
}

// ---------- protobuf ----------
function jzVarint(n) {
    var b = [];
    while (n >= 0x80) {
        b.push((n % 128) | 0x80);
        n = Math.floor(n / 128);
    }
    b.push(n | 0);
    return b;
}
function jzPbField(num, wire, payload) {
    var t = jzVarint((num << 3) | wire);
    if (wire === 2) {
        var len = jzVarint(payload.length);
        return t.concat(len).concat(payload);
    }
    return t.concat(payload);
}
function jzPbParse(buf) {
    var out = [];
    var i = 0, n = buf.length;
    while (i < n) {
        var b = buf[i]; var fn = b >> 3, wt = b & 7; i++;
        if (wt === 0) {
            var v = 0, sh = 0;
            while (i < n) {
                var x = buf[i]; i++;
                v |= (x & 0x7f) << sh; sh += 7;
                if (!(x & 0x80)) break;
            }
            out.push({ fn: fn, wt: wt, v: v });
        } else if (wt === 2) {
            var ln = 0; sh = 0;
            while (i < n) {
                var x = buf[i]; i++;
                ln |= (x & 0x7f) << sh; sh += 7;
                if (!(x & 0x80)) break;
            }
            out.push({ fn: fn, wt: wt, v: buf.slice(i, i + ln) }); i += ln;
        } else if (wt === 5) {
            out.push({ fn: fn, wt: wt, v: buf.slice(i, i + 4) }); i += 4;
        } else if (wt === 1) {
            out.push({ fn: fn, wt: wt, v: buf.slice(i, i + 8) }); i += 8;
        } else { i++; }
    }
    return out;
}

// ---------- 协议逻辑 ----------
function jzRnd(k) {
    var CH = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    var pool = CH.split('');
    var out = '';
    for (var i = 0; i < k - 1; i++) {
        var idx = Math.floor(Math.random() * pool.length);
        out += pool[idx];
        pool.splice(idx, 1);
    }
    return out + '=';
}

// 登录/注册, 拿 token; 固定账号服务器自动注册, 可复用
function jzLogin() {
    try {
        var body = '{"username":"' + JUZI_USER + '","password":"' + JUZI_PASS + '","udid":"' + JUZI_UDID + '"}';
        var h = { 'User-Agent': JUZI_UA, 'Content-Type': 'application/json' };
        try {
            req(JUZI_HOST + '/api/ex/v3/user/register', { 'method': 'POST', 'headers': h, 'body': body, 'timeout': REQ_TIMEOUT });
        } catch (e) {}
        var r = req(JUZI_HOST + '/api/ex/v3/user/login', { 'method': 'POST', 'headers': h, 'body': body, 'timeout': REQ_TIMEOUT });
        if (r && r.content) {
            var d = JSON.parse(r.content);
            var data = d.data || {};
            jzToken = data.token || (data.user && data.user.token) || '';
        }
    } catch (e) {
        jzToken = '';
    }
    jzLoginTried = true;
    return jzToken;
}

// 设备参数 JSON (与 py _hdr 的 J 逐字段一致) -> AES-CBC hex
function jzDeviceJson(ts, rnd16, sig, ao) {
    return '{"country":"CN","vName":"3.0.2.4","cpuId":"","young":0,"facturer":"OnePlus","pkg":"' + JUZI_PKG + '","uuid":"' + JUZI_UDID + '","resolution":"1080x2256","mac":"02%3A00%3A00%3A00%3A00%3A00","sig":"' + sig + '","abid":"7470","model":"PJX110","plat":"android","udid":"' + JUZI_UDID + '","dpi":"480","net":"1","lang":"zh","random_str":"' + rnd16 + '","brand":"OnePlus","timestamp":' + ts + ',"density":"3.0","appName":"%E6%A9%98%E6%B1%81","cpu":"arm64-v8a","chid":"10000","carrier":"%E8%81%94%E9%80%9A","sig2":"' + ao.substring(0, 8) + '","v":1,"sig3":"' + ao.substring(8) + '","tenantId":"*","_vOsCode":"36","vOs":"16","vApp":"' + JUZI_VC + '","device":0,"androidID":"' + JUZI_UDID + '"}';
}

// 全签名请求头
function jzHeaders() {
    var ts = String(Date.now());
    var rnd16 = jzRnd(16);
    var sig = jzB64Encode(jzRsaEncrypt(JUZI_RSA2_N, jzStrToBytes(ts + rnd16 + JUZI_VC)));
    // 注意: ao 必须 PKCS7 pad (ts+rnd 29 字节 -> 32), 漏 pad 会被服务器拒绝
    var ao = jzB64Encode(jzAes(jzStrToBytes(JUZI_SAFE), jzPkcs7(jzStrToBytes(ts + rnd16), 16), 'ECB'));
    var J = jzDeviceJson(ts, rnd16, sig, ao);
    var pdHex = jzBytesToHex(jzAes(jzStrToBytes(JUZI_NATIVE_K), jzPkcs7(jzStrToBytes(J), 16), 'CBC', jzStrToBytes(JUZI_NATIVE_K)));
    var h = { 'User-Agent': JUZI_UA, 'Accept': 'application/json', 'Cache-Control': 'no-cache', 'publicParams': '{"paramsData":"' + pdHex + '"}' };
    if (jzToken) h['token'] = jzToken;
    return h;
}

// 签名请求体 protobuf (返回字节数组)
function jzSecure(mapkv) {
    var ts = String(Date.now());
    var rnd8 = jzRnd(8);
    var plain = jzStrToBytes(mapkv + ts);
    var ct = jzAes(jzStrToBytes(JUZI_SAFECODE), jzPkcs7(plain, 16), 'ECB');
    var b64 = jzB64Encode(ct);
    var out = [];
    out = out.concat(jzPbField(1, 2, jzStrToBytes(rnd8 + b64.substring(0, 12))));
    out = out.concat(jzPbField(2, 2, jzStrToBytes(b64.substring(12))));
    out = out.concat(jzPbField(3, 2, jzStrToBytes(jzRnd(20))));
    out = out.concat(jzPbField(4, 0, jzVarint(parseInt(ts, 10))));
    out = out.concat(jzPbField(5, 2, jzStrToBytes(rnd8)));
    return out;
}

// 换链: 播放参数 -> 真实播放地址
function jzResolvePlay(pf, pu) {
    try {
        var headers = jzHeaders();
        headers['Content-Type'] = 'application/x-protobuf; charset=ISO-8859-1';
        headers['Accept'] = 'application/x-protobuf';
        var qs = 'vodPlayFrom=' + encodeURIComponent(pf) + '&playUrl=' + encodeURIComponent(pu);
        var bodyBytes = jzSecure(qs);
        var resp = req(JUZI_HOST + '/api/proto/v5/videoUsableUrl', {
            'method': 'POST',
            'headers': headers,
            'body': jzBytesToStr(bodyBytes),
            'timeout': REQ_TIMEOUT
        });
        if (!resp || !resp.content) return '';
        // 换链响应是 protobuf, 引擎按 UTF-8 解码 content 会损坏非 ASCII 字节,
        // 但 URL 是纯 ASCII, 直接全文正则提取即可 (不解析 protobuf 结构, 更稳)
        var m = resp.content.match(/https?:\/\/[\x21-\x7e]+/);
        return m ? m[0] : '';
    } catch (e) {
        console.error('橘汁换链失败:', e);
        return '';
    }
}

// 播放入口: juzi://<base64(JSON{vodPlayFrom, playUrl})>
function jzResolveLive(playUrl) {
    var b64 = playUrl.indexOf('juzi://') === 0 ? playUrl.substring(7) : playUrl;
    try {
        var jm = JSON.parse(jzBytesToStr(jzB64Decode(b64)));
        var pf = jm.vodPlayFrom || '';
        var pu = jm.playUrl || '';
        if (!pf || !pu) return '';
        if (!jzToken && !jzLoginTried) jzLogin();
        var url = jzResolvePlay(pf, pu);
        if (url) return url;
        // token 可能过期: 重新登录再换链一次
        if (jzLoginTried) {
            jzToken = '';
            jzLoginTried = false;
            jzLogin();
            url = jzResolvePlay(pf, pu);
            if (url) return url;
        }
    } catch (e) {
        console.error('橘汁解析播放参数失败:', e);
    }
    return '';
}

// 频道表 -> 分类 (LIVS_SOURCES 里的 juzi_live 源专用)
function initJuziLive(typeId, typeName) {
    sourceConfigs[typeId] = {
        headers: {},
        play_parse: false,
        live_filter: false,
        juzi_live: true
    };
    if (!categories[typeId]) categories[typeId] = [];
    for (var i = 0; i < JUZI_LIVE.length; i++) {
        var group = JUZI_LIVE[i][0];
        var chs = JUZI_LIVE[i][1];
        var urls = [];
        for (var j = 0; j < chs.length; j++) {
            var chName = chs[j][0];
            var playId = chs[j][1];
            var jm = '{"vodPlayFrom":"cctv","playUrl":"' + playId + '"}';
            urls.push(chName + '$juzi://' + jzB64Encode(jzStrToBytes(jm)));
        }
        var vodId = typeId + '$$$' + categories[typeId].length;
        vodSourceConfigs[vodId] = {
            sourceHeaders: {},
            sourceConfig: sourceConfigs[typeId],
            categoryId: typeId
        };
        categories[typeId].push({
            'vod_id': vodId,
            'vod_name': group,
            'vod_pic': picUrl,
            'vod_remarks': '',
            'type_name': '',
            'vod_year': '',
            'vod_area': '',
            'vod_actor': '',
            'vod_director': '',
            'vod_content': '',
            'vod_play_from': typeName,
            'vod_play_url': urls.join('#')
        });
    }
}

// 频道表: 21 组 508 频道 (橘汁 APP typeId=25 直播, 全部 vodPlayFrom=cctv)
var JUZI_LIVE = [
["CCTV直播", [["CCTV1综合","zb-cctv1"],["CCTV2财经","zb-cctv2"],["CCTV3综艺","zb-cctv3"],["CCTV4中文国际","zb-cctv4"],["CCTV5体育","zb-cctv5"],["CCTV5+体育赛事","zb-cctv5p"],["CCTV6电影","zb-cctv6"],["CCTV7国防军事","zb-cctv7"],["CCTV8电视剧","zb-cctv8"],["CCTV9纪录","zb-cctv9"],["CCTV10科教","zb-cctv10"],["CCTV11戏曲","zb-cctv11"],["CCTV12社会与法","zb-cctv12"],["CCTV13新闻","zb-cctv13"],["CCTV14少儿","zb-cctv14"],["CCTV15音乐","zb-cctv15"],["CCTV16奥林匹克","zb-cctv16"],["CCTV17农业农村","zb-cctv17"],["CCTV4欧洲","zb-cctv4oz"],["CCTV4美洲","zb-cctv4mz"],["CGTN外语记录","zb-cgtnwyjl"],["CGTN阿拉伯语","zb-cgtnalby"],["CGTN西班牙语","zb-cgtnxbyy"],["CGTN法语","zb-cgtnfy"],["CGTN俄语","zb-cgtney"],["CGTN","zb-cgtn"]]],
["卫视频道", [["浙江卫视","zb-zjws"],["北京卫视","zb-bjws"],["东方卫视","zb-dfws"],["江苏卫视","zb-jsws"],["广东卫视","zb-gdws"],["江西卫视","zb-jxws"],["河南卫视","zb-henws"],["陕西卫视","zb-shanxws"],["大湾区卫视","zb-dwqws"],["湖北卫视","zb-hubws"],["吉林卫视","zb-jlws"],["青海卫视","zb-qhws"],["海南卫视","zb-hainws"],["嘉佳卡通","zb-jjkt"],["优漫卡通","zb-ymkt"],["兵团卫视","zb-btws"],["河北卫视","zb-hebws"],["黑龙江卫视","zb-hljws"],["山东教育卫视","zb-sdjyws"],["三沙卫视","zb-ssws"],["延边卫视","zb-ybws"],["云南卫视","zb-ynws"],["西藏卫视","zb-xzws"],["西藏藏语卫视","zb-xzzy"],["康巴卫视","zb-kbws"],["山东卫视","zb-sdws"],["新疆卫视","zb-xjws"],["山西卫视","zb-sxws"],["农林卫视","zb-nlws"],["内蒙古卫视","zb-nmgws"],["内蒙古蒙语卫视","zb-nmmyws"],["海峡卫视","zb-hxws"],["天津卫视","zb-tjws"],["辽宁卫视","zb-lnws"],["安徽卫视","zb-ahws"],["广西卫视","zb-gxws"],["四川卫视","zb-scws"],["贵州卫视","zb-gzws"],["宁夏卫视","zb-nxws"],["深圳卫视","zb-szws"],["重庆卫视","zb-cqws"],["甘肃卫视","zb-gsws"],["东南卫视","zb-dnws"],["青海安多卫视","zb-qhadws"],["湖南卫视","zb-hunws"],["湖南经视","zb-hunjs"],["金鹰卡通","zb-jykt"],["金鹰纪实","zb-jyjs"],["快乐垂钓","zb-klcd"],["先锋乒羽","zb-xfpy"],["湖南都市","zb-hunds"],["湖南电视剧","zb-hndsj"],["湖南公共","zb-hungg"],["湖南国际","zb-hungj"],["湖南娱乐","zb-hunyl"],["湖南快乐购","zb-klg"],["湖南茶频道","zb-cpd"],["湖南电影","zb-hndy"],["长沙新闻","zb-csxw"],["长沙政法","zb-cszf"],["长沙女性","zb-csnx"]]],
["橘汁带你看世界杯", [["直播","zb-cctv5"]]],
["体育频道", [["CCTV5体育","zb-cctv5"],["CCTV5+体育赛事","zb-cctv5p"],["体育休闲频道","zb-tyxxpd"],["北京体育休闲","zb-bjty"],["五星体育","zb-wxty"],["新疆体育健康","zb-xjty"]]],
["电影频道", [["CCTV6电影","zb-cctv6"],["湖南电影","zb-hndy"],["1905电影轮播","zb-1905lb"],["浙江教科影视","zb-zjjkys"],["24小时轮播","zb-24hlb"],["往昔影院","zb-wxyy"],["怀旧经典","zb-hjjd"],["放映厅","zb-fyt"],["红色经典","zb-hsjd"]]],
["少儿频道", [["CCTV14少儿","zb-cctv14"],["浙江少儿","zb-zjse"],["经典动画大集合","zb-jddhdjh"],["金鹰卡通","zb-jykt"],["卡酷少儿","zb-kkse"],["嘉佳卡通","zb-jjkt"],["优漫卡通","zb-ymkt"],["内蒙古少儿频道","zb-nmse"],["新疆少儿频道","zb-xjse"],["江苏教育","zb-jsjy"]]],
["大综合频道", [["CCTV1综合","zb-cctv1"],["CCTV2财经","zb-cctv2"],["CCTV3综艺","zb-cctv3"],["CCTV4中文国际","zb-cctv4"],["CCTV5体育","zb-cctv5"],["CCTV5+体育赛事","zb-cctv5p"],["CCTV6电影","zb-cctv6"],["CCTV7国防军事","zb-cctv7"],["CCTV8电视剧","zb-cctv8"],["CCTV9纪录","zb-cctv9"],["CCTV10科教","zb-cctv10"],["CCTV11戏曲","zb-cctv11"],["CCTV12社会与法","zb-cctv12"],["CCTV13新闻","zb-cctv13"],["CCTV14少儿","zb-cctv14"],["CCTV15音乐","zb-cctv15"],["CCTV16奥林匹克","zb-cctv16"],["CCTV17农业农村","zb-cctv17"],["CCTV4欧洲","zb-cctv4oz"],["CCTV4美洲","zb-cctv4mz"],["CGTN外语记录","zb-cgtnwyjl"],["CGTN阿拉伯语","zb-cgtnalby"],["CGTN西班牙语","zb-cgtnxbyy"],["CGTN法语","zb-cgtnfy"],["CGTN俄语","zb-cgtney"],["CGTN","zb-cgtn"],["浙江卫视","zb-zjws"],["北京卫视","zb-bjws"],["江苏卫视","zb-jsws"],["河南卫视","zb-henws"],["大湾区卫视","zb-dwqws"],["湖北卫视","zb-hubws"],["吉林卫视","zb-jlws"],["海南卫视","zb-hainws"],["嘉佳卡通","zb-jjkt"],["优漫卡通","zb-ymkt"],["兵团卫视","zb-btws"],["河北卫视","zb-hebws"],["黑龙江卫视","zb-hljws"],["山东教育卫视","zb-sdjyws"],["延边卫视","zb-ybws"],["云南卫视","zb-ynws"],["西藏卫视","zb-xzws"],["西藏藏语卫视","zb-xzzy"],["康巴卫视","zb-kbws"],["山东卫视","zb-sdws"],["新疆卫视","zb-xjws"],["山西卫视","zb-sxws"],["农林卫视","zb-nlws"],["内蒙古卫视","zb-nmgws"],["内蒙古蒙语卫视","zb-nmmyws"],["天津卫视","zb-tjws"],["辽宁卫视","zb-lnws"],["安徽卫视","zb-ahws"],["广西卫视","zb-gxws"],["四川卫视","zb-scws"],["贵州卫视","zb-gzws"],["宁夏卫视","zb-nxws"],["深圳卫视","zb-szws"],["重庆卫视","zb-cqws"],["甘肃卫视","zb-gsws"],["东南卫视","zb-dnws"],["青海安多卫视","zb-qhadws"],["湖南卫视","zb-hunws"],["湖南经视","zb-hunjs"],["金鹰纪实","zb-jyjs"],["快乐垂钓","zb-klcd"],["先锋乒羽","zb-xfpy"],["湖南都市","zb-hunds"],["湖南电视剧","zb-hndsj"],["湖南公共","zb-hungg"],["湖南国际","zb-hungj"],["湖南娱乐","zb-hunyl"],["湖南快乐购","zb-klg"],["湖南茶频道","zb-cpd"],["湖南电影","zb-hndy"],["长沙新闻","zb-csxw"],["长沙政法","zb-cszf"],["长沙女性","zb-csnx"],["CETV1","zb-cetv1"],["CETV2","zb-cetv2"],["CETV4","zb-cetv4"],["1905电影轮播","zb-1905lb"],["西藏影视文化","zb-xzys"],["老故事","zb-lgs"],["发现之旅","zb-fxzl"],["中学生","zb-zxs"],["经典动画大集合","zb-jddhdjh"],["青春怀旧剧场","zb-qchjjt"],["最强综艺趴","zb-zqzyp"],["江苏综艺频道","zb-jszypd"],["南京新闻综合频道","zb-njxwzhpd"],["南京教科频道","zb-njjkpd"],["江苏城市频道","zb-jscspd"],["江苏国际","zb-jsgj"],["江苏教育","zb-jsjy"],["江苏影视频道","zb-jsyspd"],["公共新闻频道","zb-ggxwpd"],["淮安新闻综合","zb-haxwzh"],["连云港新闻综合","zb-lygxwzh"],["徐州新闻综合","zb-xzxwzh"],["熊猫频道1","zb-xm1"],["熊猫频道2","zb-xm2"],["熊猫频道3","zb-xm3"],["熊猫频道4","zb-xm4"],["熊猫频道5","zb-xm5"],["熊猫频道6","zb-xm6"],["熊猫频道7","zb-xm7"],["熊猫频道8","zb-xm8"],["熊猫频道9","zb-xm9"],["熊猫频道10","zb-xm10"],["浙江钱江","zb-zjqj"],["浙江经济生活","zb-zjjjsh"],["浙江教科影视","zb-zjjkys"],["浙江民生休闲","zb-zjmsxx"],["浙江新闻","zb-zjxw"],["浙江少儿","zb-zjse"],["浙江国际","zb-zjgj"],["浙江好易购","zb-zjhyg"],["浙江之江纪录","zb-zjzjjl"],["北京文艺","zb-bjwy"],["纪实科教","zb-jskj"],["北京影视","zb-bjys"],["北京财经","zb-bjcj"],["北京生活","zb-bjsh"],["北京新闻","zb-bjxw"],["卡酷少儿","zb-kkse"],["上海新闻综合","zb-shxwzh"],["新纪实","zb-xjs"],["魔都眼","zb-mdy"],["乐游","zb-ly"],["第一财经","zb-dycj"],["上号都市","zb-ds"],["五星体育","zb-wxty"],["山西经济","zb-sxjj"],["山西影视","zb-sxys"],["山西社会与法治","zb-sxfz"],["山西文体生活","zb-sxwt"],["山西黄河","zb-sxhh"],["陕西新闻资讯","zb-xwzx"],["陕西都市青春","zb-dsqc"],["银龄频道","zb-ylpd"],["秦腔频道","zb-qqpd"],["乐家购物","zb-ljgw"],["移动电视","zb-ydds"],["耿马综合","zb-gmzh"],["龙陵综合","zb-llzh"],["隆阳综合","zb-lyzh"],["玉溪新闻综合","zb-yxzh"],["河南都市","zb-hnds"],["河南民生","zb-hnms"],["河南法治","zb-hmfz"],["河南电视剧","zb-hndsj"],["河南新闻","zb-hnxw"],["欢腾购物","zb-htgw"],["河南公共","zb-hngg"],["河南乡村","zb-hnxc"],["河南梨园","zb-hnly"],["文物宝库","zb-wwbk"],["武术世界","zb-wspd"],["晴彩中原","zb-jczy"],["移动戏曲","zb-ydxj"],["象视界","zb-xsj"],["内蒙古新闻综合","zb-nmxwzh"],["内蒙古经济生活","zb-nmjjsh"],["内蒙古少儿频道","zb-nmse"],["内蒙古文体娱乐","zb-nmwtyl"],["内蒙古农牧频道","zb-nmnm"],["内蒙古蒙古语文化","zb-nmwh"],["呼和浩特新闻综合","zb-hhht1"],["锡林郭勒","zb-xlgl1"],["阿拉善新闻综合","zb-als1"],["巴彦淖尔","zb-byle1"],["鄂尔多斯","zb-erds1"],["赤峰新闻综合","zb-cf1"],["通辽新闻综合","zb-tl1"],["乌兰察布","zb-wlcb1"],["乌海新闻","zb-wh1"],["呼伦贝尔新闻综合","zb-hlbe1"],["兴安新闻综合","zb-xa1"],["包头新闻","zb-bt1"],["新疆维语新闻综合","zb-xjwyzh"],["新疆哈语新闻综合","zb-xjhyzh"],["新疆综艺","zb-xjzy"],["新疆维语影视","zb-xjwyys"],["新疆体育健康","zb-xjty"],["新疆少儿频道","zb-xjse"],["亳州综合频道","zb-bzzhpd"],["广州综合","zb-gzzh"],["河源综合","zb-hyzh"],["中山综合","zb-zszh"],["湛江新闻综合","zb-zjxwzh"],["揭阳综合","zb-jyzh"],["吉林都市频道","zb-jldspd"],["吉林生活频道","zb-jlshpd"],["吉林影视频道","zb-jlyspd"],["吉林乡村频道","zb-jlxcpd"],["吉林综艺文化频道","zb-jlzywhpd"],["长春综合频道","zb-cczhpd"],["吉林新闻综合频道","zb-jlxwzhpd"],["四平新闻综合频道","zb-spxwzhpd"],["辽源新闻综合频道","zb-lyxwzhpd"],["白城新闻综合频道","zb-bcxwzhpd"],["通化新闻综合频道","zb-thxwzhpd"],["白山新闻综合频道","zb-bsxwzhpd"],["攀枝花新闻综合频道","zb-pzhxwzhpd"],["攀枝花文旅生活频道","zb-pzhwlshpd"],["巴中综合频道","zb-bzzhpd"],["黑龙江新闻法治频道","zb-hljxwfzpd"],["黑龙江都市频道","zb-hljdspd"],["黑龙江农业・科教频道","zb-hljnykjpd"],["哈尔滨新闻综合频道","zb-hebxwzhpd"],["齐齐哈尔新闻综合频道","zb-qqhexwzhpd"],["牡丹江新闻综合频道","zb-mdjxwzhpd"],["双鸭山新闻综合频道","zb-sysxwzhpd"],["伊春新闻综合频道","zb-ycxwzhpd"],["七台河新闻综合频道","zb-qthxwzhpd"],["鹤岗新闻综合频道","zb-hgxwzhpd"],["黑河新闻综合频道","zb-hhxwzhpd"],["绥化新闻综合频道","zb-shxwzhpd"],["大兴安岭新闻综合频道","zb-dxalxwzhpd"],["杭州生活","zb-hzsh"],["24小时轮播","zb-24hlb"],["传奇剧场","zb-cqjc"],["热血剧场","zb-rxjc"],["往昔影院","zb-wxyy"],["生活剧场","zb-shjc"],["怀旧经典","zb-hjjd"],["放映厅","zb-fyt"],["红色经典","zb-hsjd"],["大咖面对面","zb-dkmdm"]]],
["熊猫频道", [["熊猫频道1","zb-xm1"],["熊猫频道2","zb-xm2"],["熊猫频道3","zb-xm3"],["熊猫频道4","zb-xm4"],["熊猫频道5","zb-xm5"],["熊猫频道6","zb-xm6"],["熊猫频道7","zb-xm7"],["熊猫频道8","zb-xm8"],["熊猫频道9","zb-xm9"],["熊猫频道10","zb-xm10"]]],
["湖南频道", [["湖南都市","zb-hunds"],["湖南电视剧","zb-hndsj"],["湖南公共","zb-hungg"],["湖南国际","zb-hungj"],["湖南娱乐","zb-hunyl"],["湖南快乐购","zb-klg"],["湖南茶频道","zb-cpd"],["湖南电影","zb-hndy"],["长沙新闻","zb-csxw"],["长沙政法","zb-cszf"],["长沙女性","zb-csnx"]]],
["广东频道", [["亳州综合频道","zb-bzzhpd"],["韶关新闻综合","zb-sgxwzh"],["河源综合","zb-hyzh"],["中山综合","zb-zszh"],["湛江新闻综合","zb-zjxwzh"],["揭阳综合","zb-jyzh"]]],
["东北频道", [["吉林都市频道","zb-jldspd"],["吉林生活频道","zb-jlshpd"],["吉林影视频道","zb-jlyspd"],["吉林乡村频道","zb-jlxcpd"],["吉林综艺文化频道","zb-jlzywhpd"],["长春综合频道","zb-cczhpd"],["吉林新闻综合频道","zb-jlxwzhpd"],["四平新闻综合频道","zb-spxwzhpd"],["辽源新闻综合频道","zb-lyxwzhpd"],["白城新闻综合频道","zb-bcxwzhpd"],["通化新闻综合频道","zb-thxwzhpd"],["白山新闻综合频道","zb-bsxwzhpd"],["黑龙江文体频道","zb-hljwtpd"],["黑龙江影视频道","zb-hljyspd"],["黑龙江新闻法治频道","zb-hljxwfzpd"],["黑龙江都市频道","zb-hljdspd"],["黑龙江农业・科教频道","zb-hljnykjpd"],["哈尔滨新闻综合频道","zb-hebxwzhpd"],["齐齐哈尔新闻综合频道","zb-qqhexwzhpd"],["牡丹江新闻综合频道","zb-mdjxwzhpd"],["双鸭山新闻综合频道","zb-sysxwzhpd"],["伊春新闻综合频道","zb-ycxwzhpd"],["七台河新闻综合频道","zb-qthxwzhpd"],["鹤岗新闻综合频道","zb-hgxwzhpd"],["黑河新闻综合频道","zb-hhxwzhpd"],["绥化新闻综合频道","zb-shxwzhpd"],["大兴安岭新闻综合频道","zb-dxalxwzhpd"]]],
["浙江频道", [["浙江钱江","zb-zjqj"],["浙江经济生活","zb-zjjjsh"],["浙江教科影视","zb-zjjkys"],["浙江民生休闲","zb-zjmsxx"],["浙江新闻","zb-zjxw"],["浙江少儿","zb-zjse"],["浙江国际","zb-zjgj"],["浙江好易购","zb-zjhyg"],["浙江之江纪录","zb-zjzjjl"]]],
["河南频道", [["河南都市","zb-hnds"],["河南电视剧","zb-hndsj"],["河南新闻","zb-hnxw"],["河南公共","zb-hngg"],["河南梨园","zb-hnly"]]],
["江苏频道", [["江苏综艺频道","zb-jszypd"],["南京新闻综合频道","zb-njxwzhpd"],["南京教科频道","zb-njjkpd"],["江苏城市频道","zb-jscspd"],["江苏国际","zb-jsgj"],["江苏教育","zb-jsjy"],["江苏影视频道","zb-jsyspd"],["淮安新闻综合","zb-haxwzh"],["连云港新闻综合","zb-lygxwzh"],["宿迁新闻综合","zb-sqxwzh"],["徐州新闻综合","zb-xzxwzh"]]],
["新闻频道", [["CCTV13新闻","zb-cctv13"],["公共新闻频道","zb-ggxwpd"],["北京新闻","zb-bjxw"],["陕西新闻资讯","zb-xwzx"],["南京新闻综合频道","zb-njxwzhpd"],["淮安新闻综合","zb-haxwzh"],["连云港新闻综合","zb-lygxwzh"],["宿迁新闻综合","zb-sqxwzh"],["徐州新闻综合","zb-xzxwzh"],["上海新闻综合","zb-shxwzh"],["内蒙古新闻综合","zb-nmxwzh"],["呼和浩特新闻综合","zb-hhht1"],["阿拉善新闻综合","zb-als1"],["赤峰新闻综合","zb-cf1"],["通辽新闻综合","zb-tl1"],["乌海新闻","zb-wh1"],["呼伦贝尔新闻综合","zb-hlbe1"],["兴安新闻综合","zb-xa1"],["包头新闻","zb-bt1"],["新疆维语新闻综合","zb-xjwyzh"],["新疆哈语新闻综合","zb-xjhyzh"],["韶关新闻综合","zb-sgxwzh"],["湛江新闻综合","zb-zjxwzh"],["吉林新闻综合频道","zb-jlxwzhpd"],["四平新闻综合频道","zb-spxwzhpd"],["辽源新闻综合频道","zb-lyxwzhpd"],["白城新闻综合频道","zb-bcxwzhpd"],["通化新闻综合频道","zb-thxwzhpd"],["白山新闻综合频道","zb-bsxwzhpd"],["攀枝花新闻综合频道","zb-pzhxwzhpd"],["黑龙江新闻法治频道","zb-hljxwfzpd"],["哈尔滨新闻综合频道","zb-hebxwzhpd"],["齐齐哈尔新闻综合频道","zb-qqhexwzhpd"],["牡丹江新闻综合频道","zb-mdjxwzhpd"],["双鸭山新闻综合频道","zb-sysxwzhpd"],["伊春新闻综合频道","zb-ycxwzhpd"],["七台河新闻综合频道","zb-qthxwzhpd"],["鹤岗新闻综合频道","zb-hgxwzhpd"],["黑河新闻综合频道","zb-hhxwzhpd"],["绥化新闻综合频道","zb-shxwzhpd"],["大兴安岭新闻综合频道","zb-dxalxwzhpd"]]],
["北京频道", [["北京文艺","zb-bjwy"],["纪实科教","zb-jskj"],["北京影视","zb-bjys"],["北京财经","zb-bjcj"],["北京生活","zb-bjsh"],["北京新闻","zb-bjxw"]]],
["戏曲频道", [["CCTV11戏曲","zb-cctv11"],["秦腔频道","zb-qqpd"]]],
["山西频道", [["山西经济","zb-sxjj"],["山西影视","zb-sxys"],["山西社会与法治","zb-sxfz"],["山西文体生活","zb-sxwt"],["山西黄河","zb-sxhh"]]],
["陕西频道", [["陕西新闻资讯","zb-xwzx"],["陕西都市青春","zb-dsqc"],["银龄频道","zb-ylpd"],["秦腔频道","zb-qqpd"]]],
["新疆频道", [["新疆维语新闻综合","zb-xjwyzh"],["新疆哈语新闻综合","zb-xjhyzh"],["新疆综艺","zb-xjzy"],["新疆维语影视","zb-xjwyys"],["新疆体育健康","zb-xjty"],["新疆少儿频道","zb-xjse"]]],
["内蒙古频道", [["内蒙古新闻综合","zb-nmxwzh"],["内蒙古经济生活","zb-nmjjsh"],["内蒙古少儿频道","zb-nmse"],["内蒙古文体娱乐","zb-nmwtyl"],["内蒙古农牧频道","zb-nmnm"],["内蒙古蒙古语文化","zb-nmwh"],["呼和浩特新闻综合","zb-hhht1"],["锡林郭勒","zb-xlgl1"],["阿拉善新闻综合","zb-als1"],["巴彦淖尔","zb-byle1"],["鄂尔多斯","zb-erds1"],["赤峰新闻综合","zb-cf1"],["通辽新闻综合","zb-tl1"],["乌兰察布","zb-wlcb1"],["乌海新闻","zb-wh1"],["呼伦贝尔新闻综合","zb-hlbe1"],["兴安新闻综合","zb-xa1"],["包头新闻","zb-bt1"]]]
];


__JS_SPIDER__ = {
    'init': init,
    'home': home,
    'homeVod': homeVod,
    'category': category,
    'detail': detail,
    'play': play,
    'search': search
};