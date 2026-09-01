/**
 * 央视频 1080P — 二次开发改造版 v2.4
 * 版本：2.4
 * 流程：
 *   - 点频道 → 自动【横屏全屏播放】（保持原全屏方式，仅方向横屏）
 *   - 全屏内：左滑调音量、右滑调亮度；**双击 → 退出全屏，竖屏显示官网网页**
 *   - 网页模式：**双击视频区 → 回到横屏全屏**；**双击视频区外(页面空白) → 返回 Ok影视 频道页面**
 * 说明：
 *   - UA 用桌面版（官网桌面版含 HTML5，可正常播放；手机版会提示"请使用央视频客户端观看"）
 *   - 方向切换/返回频道通过 WvCtl 桥(Java @JavascriptInterface)实现；Java 记录 mode 持久化，方向翻转重建后可恢复
 *   - 全屏手势层只在全屏时创建、退出时销毁，网页模式下不拦截触摸（可正常滚动/点选），避免"网页滑动变成调音量亮度"
 *   - 电视端 jar isPhone()=false，保持原非交互横屏全屏 + 系统返回键退出
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
 */
const PHONE_CONTROL_SCRIPT = String.raw`
//【开始：WvPlayer 手机端控制层 2.4】
(function(){
    if (!window || !window.matchMedia) { return; }
    var COARSE = false;
    try { COARSE = window.matchMedia('(any-pointer:coarse)').matches; } catch (e) {}
    if (!COARSE) { return; }   // 电视/遥控：不接管

    var fullscreen = false;
    var lastTap = 0, lastX = 0, lastY = 0;
    var v = null;
    var showing = false;

    function $q(s){ try { return document.querySelector(s); } catch(e){ return null; } }
    function getV(){ return $q('video'); }
    function rotLand(){ try { if (window.WvCtl && WvCtl.goLandscape) WvCtl.goLandscape(); } catch(e){} }
    function rotPort(){ try { if (window.WvCtl && WvCtl.goPortrait) WvCtl.goPortrait(); } catch(e){} }
    function getModeVal(){ try { if (window.WvCtl && WvCtl.getMode) return WvCtl.getMode(); } catch(e){} return 1; }
    function doDismiss(){ try { if (window.WvCtl && WvCtl.dismiss) WvCtl.dismiss(); } catch(e){} }

    function mkHint(){
        var h = document.getElementById('__wv_hint');
        if (h) return h;
        h = document.createElement('div');
        h.id = '__wv_hint';
        h.style.cssText = 'position:fixed!important;left:50%!important;top:18%!important;transform:translateX(-50%)!important;'
            + 'z-index:2147483648!important;color:#fff!important;background:rgba(0,0,0,.65)!important;padding:10px 18px!important;'
            + 'border-radius:6px!important;font-size:16px!important;pointer-events:none!important;display:none!important;';
        document.body.appendChild(h);
        return h;
    }
    function showHint(t, ms){
        ms = ms || 1400;
        try {
            var h = mkHint();
            h.textContent = t || '';
            h.style.display = 'block';
            clearTimeout(h._t);
            h._t = setTimeout(function(){ h.style.display = 'none'; }, ms);
        } catch(e){}
    }

    /* 全屏手势层只在全屏时存在；销毁时同时移除亮度遮罩 */
    function destroyUI(){
        ['__wv_gh','__wv_dim'].forEach(function(id){
            var el = document.getElementById(id);
            if (el && el.parentNode) el.parentNode.removeChild(el);
        });
    }
    function buildUI(){
        destroyUI();
        var dim = document.createElement('div'); dim.id = '__wv_dim';
        dim.style.cssText = 'position:fixed!important;top:0!important;left:0!important;width:100%!important;height:100%!important;'
            + 'z-index:2147483646!important;background:#000!important;opacity:0!important;pointer-events:none!important;';
        document.body.appendChild(dim);
        var gl = document.createElement('div'); gl.id = '__wv_gh';
        gl.style.cssText = 'position:fixed!important;top:0!important;left:0!important;width:100%!important;height:100%!important;z-index:2147483647!important;';
        document.body.appendChild(gl);
        var sY = 0;
        gl.addEventListener('touchstart', function(e){ var t = e.touches[0]; sY = t.clientY; e.preventDefault(); }, {passive:false});
        gl.addEventListener('touchmove', function(e){
            var t = e.touches[0]; var dy = sY - t.clientY; sY = t.clientY;
            var half = window.innerWidth / 2;
            var vv = getV();
            if (t.clientX < half) {
                if (vv) { var nv = Math.max(0, Math.min(1, vv.volume + dy / window.innerHeight)); vv.volume = nv; showHint('音量 ' + Math.round(nv*100)); }
            } else {
                var dd = document.getElementById('__wv_dim');
                if (dd) { var nb = Math.max(0.05, Math.min(1, 1 - parseFloat(dd.style.opacity||'0') + dy / window.innerHeight)); dd.style.opacity = (1 - nb).toFixed(3); showHint('亮度 ' + Math.round(nb*100)); }
            }
            e.preventDefault();
        }, {passive:false});
        gl.addEventListener('touchend', function(){}, false);
    }

    /* 进入横屏全屏（CSS 覆盖式，不移动 video 的 DOM 位置） */
    function enterFS(){
        if (fullscreen) return;
        v = getV();
        if (!v) { showHint('未找到视频'); return; }
        v.style.cssText = 'position:fixed!important;top:0!important;left:0!important;width:100vw!important;height:100vh!important;'
            + 'object-fit:contain!important;background:#000!important;z-index:2147483645!important;margin:0!important;';
        fullscreen = true;
        buildUI();
        rotLand();
        if (v.paused) { try { v.play(); } catch(e){ v.muted = true; v.play(); } }
        showHint('全屏：双击返回网页；左滑音量，右滑亮度');
    }

    /* 退出全屏：清 video 行内样式归原位，切竖屏显示网页 */
    function exitFS(){
        if (!fullscreen) return;
        v = getV();
        if (v) { v.style.cssText = ''; if (v.paused) { try { v.play(); } catch(e){} } }
        fullscreen = false;
        destroyUI();
        rotPort();
        showHint('网页：双击视频全屏，双击空白返回频道');
    }

    /* 分区域双击：
       - 全屏：双击 → 退出全屏回网页
       - 网页：双击视频区 → 进全屏；双击空白处 → 返回 Ok影视 频道页 */
    function onTap(e){
        var now = Date.now();
        var x = 0, y = 0;
        if (e.changedTouches && e.changedTouches.length) { x = e.changedTouches[0].clientX; y = e.changedTouches[0].clientY; }
        if (now - lastTap < 300) {
            lastTap = 0;
            var tx = x || lastX, ty = y || lastY;
            if (fullscreen) {
                exitFS();
            } else {
                v = getV();
                var inVideo = false;
                if (v && v.getBoundingClientRect) {
                    var r = v.getBoundingClientRect();
                    inVideo = (tx >= r.left && tx <= r.right && ty >= r.top && ty <= r.bottom);
                }
                if (inVideo) { enterFS(); }
                else { doDismiss(); }
            }
        } else { lastTap = now; lastX = x; lastY = y; }
    }
    document.addEventListener('touchend', onTap, true);

    /* 自动进入横屏全屏（仅当处于全屏模式 mode==1） */
    function tryAuto(){
        v = getV();
        if (v) { clearInterval(_ai); setTimeout(enterFS, 150); }
    }
    var _ai = null;
    if (getModeVal() !== 2) {
        _ai = setInterval(tryAuto, 200);
        setTimeout(function(){ if (!fullscreen && getV()) { clearInterval(_ai); enterFS(); } }, 6000);
    } else {
        rotPort();
    }

    window.__wvPhoneControl = { enterFS: enterFS, exitFS: exitFS, dismiss: doDismiss };
})();
//【结束：WvPlayer 手机端控制层 2.4】
`;

async function action(pid) {
    // 桌面 UA：官网桌面版含 HTML5 播放器，可在 WebView 正常播放
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