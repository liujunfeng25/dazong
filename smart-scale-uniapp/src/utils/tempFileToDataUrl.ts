/**
 * 将 canvasToTempFilePath 返回的本地路径读成 data URL。
 * 部分 HBuilder 标准基座未注入 uni.getFileSystemManager，需用 5+ Runtime 的 plus.io.FileReader 兜底。
 */
export function tempFilePathToDataUrl(tempFilePath: string, mimeType = "image/png"): Promise<string> {
  const getFs = (uni as unknown as { getFileSystemManager?: () => UniApp.FileSystemManager }).getFileSystemManager;
  if (typeof getFs === "function") {
    const fs = getFs();
    if (fs && typeof fs.readFile === "function") {
      return new Promise((resolve, reject) => {
        fs.readFile({
          filePath: tempFilePath,
          encoding: "base64",
          success: (r) => {
            const b64 = String((r as { data?: string }).data || "");
            resolve(`${mimeType};base64,${b64}`);
          },
          fail: reject,
        });
      });
    }
  }

  const plusApi = (typeof globalThis !== "undefined" ? (globalThis as unknown as { plus?: PlusIo }) : {}).plus;
  if (plusApi?.io?.resolveLocalFileSystemURL && plusApi.io.FileReader) {
    return readViaPlusIo(tempFilePath, plusApi);
  }

  return Promise.reject(
    new Error("无法读取签字临时文件：当前运行环境无 getFileSystemManager 且无 plus.io")
  );
}

type PlusIo = {
  io: {
    resolveLocalFileSystemURL: (
      path: string,
      win: (entry: PlusFileEntry) => void,
      fail: (err: unknown) => void
    ) => void;
    FileReader: new () => PlusFileReader;
  };
};

type PlusFileEntry = {
  file: (win: (file: unknown) => void, fail: (err: unknown) => void) => void;
};

type PlusFileReader = {
  onloadend: ((e: { target?: { result?: string } }) => void) | null;
  onerror: ((err: unknown) => void) | null;
  readAsDataURL: (file: unknown) => void;
};

function readViaPlusIo(tempFilePath: string, plusApi: PlusIo): Promise<string> {
  return new Promise((resolve, reject) => {
    plusApi.io.resolveLocalFileSystemURL(
      tempFilePath,
      (entry) => {
        entry.file(
          (file) => {
            try {
              const reader = new plusApi.io.FileReader();
              reader.onloadend = (e) => {
                const result = e.target?.result;
                if (typeof result === "string" && result.length > 0) resolve(result);
                else reject(new Error("plus.io.FileReader 结果为空"));
              };
              reader.onerror = reject;
              reader.readAsDataURL(file);
            } catch (e) {
              reject(e);
            }
          },
          reject
        );
      },
      reject
    );
  });
}
