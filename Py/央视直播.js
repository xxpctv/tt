/**
 * 央视频 1080P — 二次开发改造版 v2.2
 * 版本：2.2
 * 流程（按用户实测要求）：
 *   - 点节目单频道 → 进入【横屏全屏播放】视频（保持原来的全屏播放方式，仅方向改为横屏）
 *   - 全屏内：左滑调音量、右滑调亮度、轻点播放/暂停
 *   - 双击 → 退出全屏，切换为【竖屏显示官网网页】
 *   - 在网页上双击 → 回到【横屏全屏播放】
 * 说明：
 *   - UA 用桌面版（官网桌面版含 HTML5 播放器，可在 WebView 正常播放；手机版会提示"请使用央视频客户端观看"）
 *   - 全屏采用 CSS 覆盖式，不移动 video 的 DOM 位置；方向切换通过 WvCtl 桥(Java @JavascriptInterface)实现
 *   - 电视端由 jar isPhone() 判定，保持原非交互横屏全屏 + 系统返回键退出
 */

async function init(cfg) {
    return {};
}

async function homeContent(filter) {
    return {
        class: [
            { type_id: "1", type_name: "央视" },
            { type_id: "2", type_name: "卫视" }
        ]
    };
}

async function homeVideoContent() {
    return { list: [] };
}

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
            return {
                vod_id: item.pid,
                vod_name: item.channelName,
                vod_pic: item.audioPosterUrl,
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

async function detailContent(ids) {
    return { list: [] };
}

/**
 * 手机端控制层：注入到 WvPlayer 打开的官网页面内执行
 * - 触屏设备(手机/平板)才接管；电视/遥控跳过，交给 WvPlayer 原逻辑
 * - 进入后自动横屏全屏播放；双击退出到竖屏网页；网页双击回到横屏全屏
 */
const PHONE_CONTROL_SCRIPT = String.raw`
//【开始：WvPlayer 手机端控制层 2.2】
(function(){
    if (!window || !window.matchMedia) { return; }
    var COARSE = false;
    try { COARSE = window.matchMedia('(any-pointer:coarse)').matches; } catch (e) {}
    if (!COARSE) { return; }   // 电视/遥控：不接管

    var fullscreen = false;
    var lastTap = 0;
    var autoEntered = false;
    var v = null, dim = null, hint = null, gl = null;

    function $q(s){ try { return document.querySelector(s); } catch(e){ return null; } }
    function getV(){ return $q('video'); }
    function rotLand(){ try { if (window.WvCtl && WvCtl.goLandscape) WvCtl.goLandscape(); } catch(e){} }
    function rotPort(){ try { if (window.WvCtl && WvCtl.goPortrait) WvCtl.goPortrait(); } catch(e){} }

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
    function setVol(r){
        if (!v) return;
        v.volume = Math.max(0, Math.min(1, r));
        showHint('音量 ' + Math.round(v.volume * 100));
    }

    /* 进入横屏全屏：CSS 覆盖式，不移动 video 的 DOM 位置 */
    function enterFS(){
        ensureUI();
        v = getV();
        if (!v) { showHint('未找到视频'); return; }
        v.style.cssText = 'position:fixed!important;top:0!important;left:0!important;width:100vw!important;height:100vh!important;'
            + 'object-fit:contain!important;background:#000!important;z-index:2147483645!important;margin:0!important;';
        fullscreen = true;
        if (gl) gl.style.display = 'block';
        rotLand();
        if (v.paused) { try { v.play(); } catch(e){ v.muted = true; v.play(); } }
        showHint('双击退出全屏；左滑音量，右滑亮度');
    }

    /* 退出全屏：清 video 行内样式归原位，并切为竖屏显示网页 */
    function exitFS(){
        ensureUI();
        v = getV();
        if (v) { v.style.cssText = ''; }
        fullscreen = false;
        if (gl) gl.style.display = 'none';
        if (dim) dim.style.display = 'none';
        rotPort();
        showHint('已退出全屏，双击回到全屏');
    }

    function toggleFS(){
        if (fullscreen) { exitFS(); } else { enterFS(); }
    }

    /* 双击切换 */
    document.addEventListener('dblclick', function(e){ ensureUI(); toggleFS(); }, true);
    document.addEventListener('touchend', function(e){
        var now = Date.now();
        if (now - lastTap < 300) { lastTap = 0; toggleFS(); }
        else { lastTap = now; }
    }, true);

    /* 自动进入横屏全屏播放 */
    function tryAutoEnter(){
        v = getV();
        if (v) {
            clearInterval(_ai);
            autoEntered = true;
            setTimeout(enterFS, 150);
        }
    }
    var _ai = setInterval(tryAutoEnter, 200);
    setTimeout(function(){ if (!autoEntered) { clearInterval(_ai); enterFS(); } }, 6000);

    window.__wvPhoneControl = { enterFS: enterFS, exitFS: exitFS, toggle: toggleFS };
})();
//【结束：WvPlayer 手机端控制层 2.2】
`;

async function action(pid) {
    // 桌面 UA：官网桌面版含 HTML5 播放器，可在 WebView 正常播放（手机版会提示"请使用央视频客户端观看"）
    Java.wvPlayerSetScale(0); //画面比例: 0=默认, 1=16:9, 2=4:3, 3=填充, 4=原始, 5=裁剪

    Java.wvPlayer({
        url: 'https://yangshipin.cn/tv/home?pid=' + pid,
        headers: {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'
        },
        script: PHONE_CONTROL_SCRIPT
    });
}

async function searchContent(key, quick, pg) {
    return { list: [] };
}

async function playerContent(flag, id, vipFlags) {
    return;
}