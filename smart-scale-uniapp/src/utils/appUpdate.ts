import { request } from "./request";

export type RemoteVersion = {
  version_code: number;
  version_name: string;
  apk_url: string;
  wgt_url: string;
  force: boolean;
  notes: string;
};

function getLocalVersionCode(): number {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const rt = typeof plus !== "undefined" ? (plus as any)?.runtime : null;
    const raw = rt?.versionCode;
    if (raw != null && raw !== "") {
      const n = parseInt(String(raw), 10);
      return Number.isFinite(n) ? n : 0;
    }
  } catch {
    /* H5 / 非 App */
  }
  return 0;
}

function installLocalPath(path: string): void {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const rt = typeof plus !== "undefined" ? (plus as any)?.runtime : null;
  if (!rt?.install) {
    uni.showToast({ title: "当前环境不支持安装", icon: "none" });
    return;
  }
  uni.showLoading({ title: "安装中…", mask: true });
  rt.install(
    path,
    { force: true },
    () => {
      uni.hideLoading();
      uni.showToast({ title: "安装完成，请重启应用", icon: "none" });
    },
    (e: { message?: string }) => {
      uni.hideLoading();
      uni.showModal({
        title: "安装失败",
        content: e?.message || "请检查存储权限或到设置中允许安装未知应用",
        showCancel: false,
      });
    }
  );
}

function downloadAndInstall(url: string): void {
  if (!url) return;
  uni.showLoading({ title: "下载中…", mask: true });
  uni.downloadFile({
    url,
    success: (res) => {
      uni.hideLoading();
      if (res.statusCode !== 200 || !res.tempFilePath) {
        uni.showToast({ title: "下载失败", icon: "none" });
        return;
      }
      installLocalPath(res.tempFilePath);
    },
    fail: () => {
      uni.hideLoading();
      uni.showToast({ title: "下载失败，请检查网络与地址", icon: "none" });
    },
  });
}

/** App 启动时调用：对比后端 version_code，提示下载 wgt 或 apk */
export async function checkSmartScaleAppUpdate(): Promise<void> {
  // #ifndef APP-PLUS
  return;
  // #endif

  const local = getLocalVersionCode();
  if (!local) return;

  let remote: RemoteVersion;
  try {
    remote = await request<RemoteVersion>("/system/smart-scale-app/version", {
      method: "GET",
    });
  } catch {
    return;
  }

  if (!remote?.version_code || remote.version_code <= local) return;
  if (!remote.apk_url && !remote.wgt_url) return;

  const title = `发现新版本 ${remote.version_name || ""}（${remote.version_code}）`;
  const content =
    (remote.notes && remote.notes.trim()) ||
    "是否下载并安装？安装过程可能需要您确认系统权限。";

  await new Promise<void>((resolve) => {
    uni.showModal({
      title,
      content,
      showCancel: !remote.force,
      confirmText: "立即更新",
      cancelText: "稍后",
      success: (r) => {
        if (r.confirm) {
          if (remote.wgt_url) {
            downloadAndInstall(remote.wgt_url);
          } else if (remote.apk_url) {
            downloadAndInstall(remote.apk_url);
          }
        }
        resolve();
      },
      fail: () => resolve(),
    });
  });
}
