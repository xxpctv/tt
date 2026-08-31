/**
 * 央视频 1080P — 二次开发改造版 v2.1
 * 版本：2.1
 * 针对手机/TV 双端优化：
 *   1) 手机（非电视，jar 内 isPhone 判断）：官网页面以【横屏 + 内联视频】展示，可操作页面频道/标签；
 *      双击视频进入全屏（横屏）；全屏内左滑调音量、右滑调亮度；再双击返回官网并保持原位播放。
 *   2) 电视：保持原逻辑（全屏播放 + 系统手势/返回键退出）。
 * 说明：注入给 WvPlayer 页面的手势层由 script 参数携带；全屏采用 CSS 覆盖式，不移动 video 的 DOM 位置，
 *       退出全屏时视频自然回到网页原位置。
 */

/**
 * 初始化配置（去掉了对图片 .png/.webp 的 blockList，修复电视图标不显示问题）
 */
async function init(cfg) {
    return {};
}

/**
 * 首页分类
 */
async function homeContent(filter) {
    return {
        class: [
            { type_id: "1", type_name: "央视" },
            { type_id: "2", type_name: "卫视" }
        ]
    };
}

/**
 * 首页推荐视频
 */
async function homeVideoContent() {
    return {
        list: []
    };
}

/**
 * 分类内容
 */
async function categoryContent(tid, pg, filter, extend) {
    const res = await Java.req('https://h5access.yangshipin.cn/web/tv_web_share?raw=1&pid=600002485');
    const jsonData = JSON.parse(res.body);
    const pidInfo = jsonData?.data?.pidInfo || [];

    const isCentralTV = (name) => name.startsWith('CCTV') || name.startsWith('CGTN');

    const vods = pidInfo
        .filter(item => {
            if (item.vipInfo?.isVip !== false) return false;
            if (!item.pid || !item.channelName) return false;
            const isCentral = isCentralTV(item.channelName);
            return tid === '1' ? isCentral : !isCentral;
        })
        .map(item => {
            const isCentral = isCentralTV(item.channelName);
            const vodPic = item.audioPosterUrl;
            return {
                vod_id: item.pid,
                vod_name: item.channelName,
                vod_pic: vodPic,
                action: item.pid,
                style: { type: "rect", ratio: isCentral ? 1.66 : 1 }
            };
        })
        .filter(item => item.vod_pic);

    return {
        code: 1,
        msg: "数据列表",
        list: vods,
        page: 1,
        pagecount: 1,
        limit: vods.length,
        total: vods.length
    };
}

/**
 * 详情页
 */
async function detailContent(ids) {
    return {
        list: []
    };
}

/**
 * 手机端手势层脚本（注入到 WvPlayer 打开的官网页面内执行）
 * - 触屏设备(手机/平板)才接管；电视/遥控直接跳过，交由 WvPlayer 原逻辑。
 * - WvPlayer 已注入 __wvPhoneMode：手机端不自动全屏，保留 video 内联并加响应式 viewport。
 * - 本层负责：双击进出全屏(CSS覆盖式)；全屏左滑=音量、右滑=亮度；轻点=播放/暂停。
 */
const PHONE_CONTROL_SCRIPT = String.raw`
//【开始：WvPlayer 手机端控制层 2.1】
(function(){
    if (!window || !window.matchMedia) { return; }
    var COARSE = false;
    try { COARSE = window.matchMedia('(any-pointer:coarse)').matches; } catch (e) {}
    if (!COARSE) { return; }   // 电视/遥控：不接管

    var fullscreen = false;
    var lastTap = 0;
    var v = null, dim = null, hint = null, gl = null;

    function $q(s){ try { return document.querySelector(s); } catch(e){ return null; } }
    function getV(){ return $q('#wv-player-container video') || $q('video'); }

    function showHint(t, ms){
        ms = ms || 1200;
        if (!hint) return;
        hint.textContent = t || '';
        hint.style.display = 'block';
        clearTimeout(hint._t);
        hint._t = setTimeout(function(){ hint.style.display = 'none'; }, ms);
    }

    function ensureUI(){
        if (document.getElementById('__wv_gesture')) return;
        dim = document.createElement('div');
        dim.id = '__wv_dim';
        dim.style.cssText = 'position:fixed!important;top:0!important;left:0!important;width:100%!important;height:100%!important;'
            + 'z-index:2147483646!important;background:#000!important;opacity:0!important;pointer-events:none!important;display:none!important;';
        document.body.appendChild(dim);

        gl = document.createElement('div');
        gl.id = '__wv_gesture';
        gl.style.cssText = 'position:fixed!important;top:0!important;left:0!important;width:100%!important;height:100%!important;'
            + 'z-index:2147483647!important;display:none!important;';
        var gStartY = 0, gMoved = 0, gVol = 1, gBri = 1;
        gl.addEventListener('touchstart', function(e){
            if (!fullscreen) return;
            var t = e.touches[0]; gStartY = t.clientY; gMoved = 0;
            if (v) gVol = v.volume;
            try { gBri = 1 - parseFloat(dim.style.opacity || '0'); } catch(_) { gBri = 1; }
            e.preventDefault();
        }, {passive:false});
        gl.addEventListener('touchmove', function(e){
            if (!fullscreen) return;
            var t = e.touches[0]; var dy = gStartY - t.clientY; gStartY = t.clientY;
            if (Math.abs(dy) > 2) gMoved = 1;
            var half = window.innerWidth / 2;
            if (t.clientX < half) { gVol += dy / window.innerHeight; setVol(gVol); }
            else { gBri += dy / window.innerHeight; setBright(gBri); }
            e.preventDefault();
        }, {passive:false});
        gl.addEventListener('touchend', function(){
            if (!fullscreen) return;
            if (!gMoved) { var vv = getV(); if (vv) { if (vv.paused) vv.play(); else vv.pause(); } }
        }, false);
        document.body.appendChild(gl);

        hint = document.createElement('div');
        hint.id = '__wv_hint';
        hint.style.cssText = 'position:fixed!important;left:50%!important;top:20%!important;transform:translateX(-50%)!important;'
            + 'z-index:2147483648!important;color:#fff!important;background:rgba(0,0,0,.65)!important;padding:10px 18px!important;'
            + 'border-radius:6px!important;font-size:16px!important;pointer-events:none!important;display:none!important;';
        document.body.appendChild(hint);
    }

    function setBright(r){
        ensureUI();
        if (!dim) return;
        dim.style.display = 'block';
        dim.style.opacity = (1 - Math.max(0.05, Math.min(1, r))).toFixed(3);
        showHint('亮度 ' + Math.round(r * 100));
    }
    function setVol(r){ if (v) { v.volume = Math.max(0, Math.min(1, r)); showHint('音量 ' + Math.round(v.volume * 100)); } }

    /* 进入全屏：CSS 覆盖式，不移动 video 的 DOM 位置 */
    function enterFS(){
        ensureUI();
        v = getV();
        if (!v) { showHint('未找到视频'); return; }
        v.style.cssText = 'position:fixed!important;top:0!important;left:0!important;width:100vw!important;height:100vh!important;'
            + 'object-fit:contain!important;background:#000!important;z-index:2147483645!important;margin:0!important;';
        fullscreen = true;
        if (gl) gl.style.display = 'block';
        if (v.paused) { try { v.play(); } catch(e){ v.muted = true; v.play(); } }
        showHint('双击返回网页；左滑音量，右滑亮度');
    }

    /* 退出全屏：清除 video 行内样式 → 视频自然回到网页原位内联播放 */
    function exitFS(){
        ensureUI();
        v = getV();
        if (v) { v.style.cssText = ''; }
        fullscreen = false;
        if (gl) gl.style.display = 'none';
        if (dim) dim.style.display = 'none';
        showHint('已返回网页，双击视频全屏');
    }

    /* 双击：页面/全屏 切换 */
    document.addEventListener('dblclick', function(e){
        ensureUI();
        if (!fullscreen) { enterFS(); } else { exitFS(); }
    }, true);
    document.addEventListener('touchend', function(e){
        var now = Date.now();
        if (now - lastTap < 300) {
            lastTap = 0;
            if (fullscreen) { exitFS(); } else { enterFS(); }
        } else { lastTap = now; }
    }, true);

    setTimeout(function(){ showHint('双击视频全屏；左滑音量，右滑亮度'); }, 600);

    window.__wvPhoneControl = { enterFS: enterFS, exitFS: exitFS };
})();
//【结束：WvPlayer 手机端控制层 2.1】
`;

/**
 * 分类播放动作
 * 设备类型由 Java 侧 isPhone() 决定；注入脚本在页面内再按触屏区分，双重保障。
 */
async function action(pid) {
    Java.wvPlayerSetScale(0); //画面比例: 0=默认, 1=16:9, 2=4:3, 3=填充, 4=原始, 5=裁剪

    Java.wvPlayer({
        url: 'https://yangshipin.cn/tv/home?pid=' + pid,
        headers: {
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
        },
        script: PHONE_CONTROL_SCRIPT
    });
}

/**
 * 搜索
 */
async function searchContent(key, quick, pg) {
    return {
        list: []
    };
}

/**
 * 播放器
 */
async function playerContent(flag, id, vipFlags) {
    return;
}