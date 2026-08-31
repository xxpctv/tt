/**
 * 央视频 1080P — 二次开发改造版
 * 版本：2.0
 * 针对手机(TV)双端优化：
 *   1) 手机端：进入官网页面【不强制全屏】，可操作页面频道/标签；双击视频全屏；全屏内左滑调音量、右滑调亮度；再双击返回官网页面。
 *   2) 电视端：保持原逻辑（非交互全屏 + 系统手势/返回键退出），互不影响。
 * 说明：注入给 WvPlayer 页面的手势层由 script 参数携带，WvPlayer 加载完官网页面后自动执行。
 */

/**
 * 初始化配置
 * 注意：这里去掉了 blockList 对图片(.png/.webp/.ico…)的拦截，
 * 避免电视端官网页面图标(通常是图片)显示异常的缺陷。
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
 * - 通过 (any-pointer: coarse) 判断是否为触屏设备；电视(不满足)直接跳过，保持原逻辑。
 * - 手机：先还原 WvPlayer 默认全屏 → 展示可交互页面；
 *   双击视频=全屏/返回页面；全屏内左滑=音量，右滑=亮度（用半透明遮罩模拟）。
 */
const PHONE_CONTROL_SCRIPT = String.raw`
//【开始：WvPlayer 手机端控制层 2.0】
(function(){
    if (!window || !window.matchMedia) { return; }
    var COARSE = false;
    try { COARSE = window.matchMedia('(any-pointer:coarse)').matches; } catch (e) {}
    if (!COARSE) {
        // 电视/遥控设备：不接管，交由 WvPlayer 原Java手势与返回键逻辑
        try { window.wvSetScale = window.wvSetScale || function(){}; } catch (e) {}
        return;
    }
    var fullscreen = false;
    var lastTap = 0;
    var v = null;
    var dim = null;
    var hint = null;

    function $(s){ var r=null; try{ r=document.querySelector(s); }catch(e){} return r; }
    function getVideo(){ return $('#wv-player-container video') || $('video'); }
    function showHint(text, ms){
        ms = ms || 1200;
        if (!hint) return;
        hint.textContent = text || '';
        hint.style.display = 'block';
        clearTimeout(hint._t);
        hint._t = setTimeout(function(){ hint.style.display = 'none'; }, ms);
    }

    /* 还原 WvPlayer 的 setupFullScreen，露出官网页面，让用户可操作标签/频道 */
    function undoInitialFullscreen(){
        var c = $('#wv-player-container');
        var vv = getVideo();
        if (c && c.parentNode) { c.parentNode.removeChild(c); }
        if (vv && vv.parentNode && vv.parentNode !== document.body) {
            try { document.body.appendChild(vv); } catch(e){}
        }
        var kids = document.body ? document.body.childNodes : [];
        for (var i=0;i<kids.length;i++){
            var n = kids[i];
            if (n && n.style && n.id !== 'wv-player-container') { n.style.display = ''; }
        }
        try {
            if (document.body) document.body.style.cssText = '';
            if (document.documentElement) document.documentElement.style.cssText = '';
        } catch(e) {}
    }

    /* 进入全屏：把视频收进独立容器，隐藏页面其余元素 */
    function enterFS(){
        v = getVideo();
        if (!v) { showHint('未找到视频'); return; }
        var c = $('#wv-player-container') || document.getElementById('wv-player-container');
        if (!c) {
            c = document.createElement('div');
            c.id = 'wv-player-container';
            document.body.appendChild(c);
        }
        try { if (v.parentNode && v.parentNode !== c) v.parentNode.removeChild(v); } catch(e){}
        c.appendChild(v);
        c.style.cssText = 'position:fixed!important;top:0!important;left:0!important;width:100%!important;height:100%!important;'
            + 'z-index:2147483647!important;background:#000!important;overflow:hidden!important;margin:0!important;padding:0!important;';
        v.style.cssText = 'width:100%!important;height:100%!important;object-fit:contain!important;';
        var kids = document.body ? document.body.childNodes : [];
        for (var i=0;i<kids.length;i++){
            var n = kids[i];
            var own = n && n.id && (n.id==='wv-player-container'||n.id==='__wv_dim'||n.id==='__wv_gesture'||n.id==='__wv_hint');
            if (n && n.style && !own) { n.style.display = 'none'; }
        }
        try { if (document.body) document.body.style.cssText = 'margin:0!important;padding:0!important;overflow:hidden!important;background:#000!important;'; } catch(e){}
        try { gl.style.display = 'block'; } catch(e){}
        fullscreen = true;
        if (v.paused) { try{ v.play(); }catch(e){ v.muted=true; v.play(); } }
        showHint('双击返回官网，左滑音量，右滑亮度');
    }

    /* 退出全屏：返回官网可交互页面 */
    function exitFS(){
        v = getVideo();
        var c = document.getElementById('wv-player-container');
        if (c) {
            var kids = document.body ? document.body.childNodes : [];
            for (var i=0;i<kids.length;i++){
                var n = kids[i];
                var own = n && n.id && (n.id==='__wv_dim'||n.id==='__wv_gesture'||n.id==='__wv_hint');
                if (n && n.style && !own) { n.style.display = ''; }
            }
            if (v && c.contains && c.contains(v)) { try{ c.removeChild(v); }catch(e){} }
            if (c.parentNode) c.parentNode.removeChild(c);
        }
        try { gl.style.display = 'none'; } catch(e){}
        if (v && v.parentNode !== document.body) { try{ document.body.appendChild(v); }catch(e){} }
        try { if (document.body) document.body.style.cssText = ''; } catch(e){}
        try { if (document.documentElement) document.documentElement.style.cssText = ''; } catch(e){}
        fullscreen = false;
        showHint('已返回官网，可继续操作；双击视频全屏');
    }

    /* 亮度遮罩（用黑色半透明层模拟亮度调节：opacity 越大越暗） */
    function ensureDim(){
        dim = document.getElementById('__wv_dim');
        if (!dim){
            dim = document.createElement('div');
            dim.id = '__wv_dim';
            dim.style.cssText = 'position:fixed!important;top:0!important;left:0!important;width:100%!important;height:100%!important;'
                + 'z-index:2147483646!important;background:#000!important;opacity:0!important;pointer-events:none!important;';
            document.body.appendChild(dim);
        }
        return dim;
    }
    function setBright(ratio){  // ratio 0-1
        var d = ensureDim();
        d.style.opacity = (1 - Math.max(0.05, Math.min(1, ratio))).toFixed(3);
        showHint('亮度 ' + Math.round(ratio*100));
    }
    function setVol(ratio){ if (v) { v.volume = Math.max(0, Math.min(1, ratio)); showHint('音量 ' + Math.round(v.volume*100)); } }

    /* 全屏内的手势拦截层：左半=音量，右半=亮度，双击=返回页面 */
    var gl = document.createElement('div');
    gl.id = '__wv_gesture';
    gl.style.cssText = 'position:fixed!important;top:0!important;left:0!important;width:100%!important;height:100%!important;'
        + 'z-index:2147483645!important;display:none!important;';
    var gStartY = 0, gMoved = 0, gVol = 1, gBri = 1;
    gl.addEventListener('touchstart', function(e){ if(!fullscreen) return; var t=e.touches[0]; gStartY=t.clientY; gMoved=0; if(v) gVol=v.volume; try{gBri=1-parseFloat(ensureDim().style.opacity||'0');}catch(_){gBri=1;} e.preventDefault(); }, {passive:false});
    gl.addEventListener('touchmove', function(e){ if(!fullscreen) return; var t=e.touches[0]; var dy=gStartY-t.clientY; gStartY=t.clientY; if(Math.abs(dy)>2) gMoved=1; var half=window.innerWidth/2; if(t.clientX<half){ gVol+=dy/window.innerHeight; setVol(gVol); } else { gBri+=dy/window.innerHeight; setBright(gBri); } e.preventDefault(); }, {passive:false});
    gl.addEventListener('touchend', function(e){ if(!fullscreen) return; if(!gMoved){ var vv=getVideo(); if(vv){ if(vv.paused){ vv.play(); } else { vv.pause(); } } gl.style.display='none'; setTimeout(function(){ gl.style.display='block'; }, 60); } }, {passive:false});
    document.body.appendChild(gl);

    /* 提示 HUD */
    hint = document.createElement('div');
    hint.id = '__wv_hint';
    hint.style.cssText = 'position:fixed!important;left:50%!important;top:20%!important;transform:translateX(-50%)!important;'
        + 'z-index:2147483648!important;color:#fff!important;background:rgba(0,0,0,.65)!important;padding:10px 18px!important;'
        + 'border-radius:6px!important;font-size:16px!important;pointer-events:none!important;display:none!important;';
    document.body.appendChild(hint);

    /* 双击开关（页面非全屏时监听双击进入全屏；全屏时由手势层上方的双击返回） */
    document.addEventListener('dblclick', function(e){
        if (!fullscreen) { enterFS(); } else { exitFS(); }
    }, true);
    document.addEventListener('touchend', function(e){
        var now = Date.now();
        if (now - lastTap < 300) {
            lastTap = 0;
            if (fullscreen) { gl.style.display='none'; exitFS(); } else { enterFS(); }
        } else { lastTap = now; }
    }, true);

    /* 进入页面即还原全屏 → 展示官网可交互页面 */
    setTimeout(undoInitialFullscreen, 300);
    setTimeout(function(){ showHint('点击/双击视频可全屏；官网标签可直接操作'); }, 600);

    window.__wvPhoneControl = { enterFS:enterFS, exitFS:exitFS };
})();
//【结束：WvPlayer 手机端控制层 2.0】
`;

/**
 * 分类播放动作
 * 设备类型由注入页面内的脚本自行判断：
 *   - 手机/触屏：进入官网页面为可交互状态（不强制全屏）
 *   - 电视/遥控：维持原横屏全屏逻辑
 */
async function action(pid) {
    // 设备交互模式(手机=交互页面 / 电视=非交互全屏)由 Java 侧 isPhone() 自动决定，此处不再强制覆盖
    Java.wvPlayerSetScale(0); //画面比例: 0=默认, 1=16:9, 2=4:3, 3=填充, 4=原始, 5=裁剪

    Java.wvPlayer({
        url: 'https://yangshipin.cn/tv/home?pid=' + pid,
        headers: {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'
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