(function () {
    var cookieUrl = "https://cdn09022024.gitlink.org.cn/api/v1/repos/ajeo/k1/raw/my/.quark_cookie.txt";
    var saveDir = "/storage/emulated/0/feimao";
    var savePath = saveDir + "/.quark_cookie.txt";

    try {
        // 判断目录，不存在就创建
        if (!LocalFile.exists(saveDir)) {
            var ok = LocalFile.mkdirs(saveDir);
            if(ok){
                toast("已创建feimao文件夹");
            }else{
                toast("文件夹创建失败");
                return;
            }
        }

        fetch(cookieUrl)
        .then(function(resp){
            if (!resp.ok) {
                throw new Error("网络请求失败:" + resp.status);
            }
            return resp.text();
        })
        .then(function(text){
            LocalFile.write(savePath, text);
            toast("✅ Cookie保存成功！路径：" + savePath);
        })
        .catch(function(e){
            toast("❌失败:" + e.message);
        });

    } catch (e) {
        toast("❌脚本异常:" + e.message);
    }
})();
