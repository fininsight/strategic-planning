import { spawn } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome-stable",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
  "/usr/bin/chromium-browser",
].filter(Boolean);

function findChromePath() {
  const found = CHROME_CANDIDATES.find((candidate) => fs.existsSync(candidate));
  if (!found) {
    throw new Error(`Chrome 실행 파일을 찾지 못했습니다. CHROME_PATH를 설정하거나 Chrome/Chromium을 설치하세요.`);
  }
  return found;
}

function parseArgs() {
  const args = new Map();
  for (let i = 2; i < process.argv.length; i += 2) {
    args.set(process.argv[i], process.argv[i + 1]);
  }
  return {
    bidNo: args.get("--bid-no"),
    bidOrd: args.get("--bid-ord") || "000",
    outDir: args.get("--out-dir") || "/private/tmp/g2b-downloads",
  };
}

function getJson(port, route) {
  return new Promise((resolve, reject) => {
    http
      .get({ host: "127.0.0.1", port, path: route }, (res) => {
        let data = "";
        res.on("data", (chunk) => {
          data += chunk;
        });
        res.on("end", () => resolve(JSON.parse(data)));
      })
      .on("error", reject);
  });
}

function newPage(port, targetUrl) {
  return new Promise((resolve, reject) => {
    const req = http.request(
      { host: "127.0.0.1", port, path: `/json/new?${encodeURIComponent(targetUrl)}`, method: "PUT" },
      (res) => {
        let data = "";
        res.on("data", (chunk) => {
          data += chunk;
        });
        res.on("end", () => resolve(JSON.parse(data)));
      },
    );
    req.on("error", reject);
    req.end();
  });
}

async function waitForChrome(port) {
  const started = Date.now();
  while (Date.now() - started < 15000) {
    try {
      await getJson(port, "/json/version");
      return;
    } catch {
      await delay(300);
    }
  }
  throw new Error("Chrome 원격 디버깅 포트가 열리지 않았습니다.");
}

function decodeHtml(value = "") {
  return String(value)
    .replaceAll("&#40;", "(")
    .replaceAll("&#41;", ")")
    .replaceAll("&amp;", "&")
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&quot;", "\"")
    .replaceAll("&#39;", "'");
}

function waitForFile(dir, before, expectedSize, expectedExtension = "") {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const timer = setInterval(() => {
      const files = fs
        .readdirSync(dir)
        .filter((name) => !before.has(name) && !name.endsWith(".crdownload"))
        .map((name) => path.join(dir, name));
      const target = files.find((file) => !expectedExtension || file.toLowerCase().endsWith(expectedExtension));
      if (target) {
        const stat = fs.statSync(target);
        if (!expectedSize || stat.size === expectedSize) {
          clearInterval(timer);
          resolve(target);
        }
      }
      if (Date.now() - started > 45000) {
        clearInterval(timer);
        reject(new Error("첨부파일 다운로드 대기 시간이 초과되었습니다."));
      }
    }, 500);
  });
}

function withoutExtension(fileName = "") {
  return decodeHtml(fileName).replace(/\.[^.]+$/, "").trim().toLowerCase();
}

function selectAttachments(attachments) {
  const pdfBases = new Set(
    attachments
      .filter((item) => String(item.fileExtnNm).toLowerCase() === ".pdf")
      .map((item) => withoutExtension(item.orgnlAtchFileNm)),
  );

  return attachments.filter((item) => {
    const extension = String(item.fileExtnNm || "").toLowerCase();
    if (!extension) return false;
    if (extension === ".pdf") return true;
    return !pdfBases.has(withoutExtension(item.orgnlAtchFileNm));
  });
}

function stableCopy(filePath, selected, index, outDir) {
  const extension = String(selected.fileExtnNm || path.extname(filePath) || "").toLowerCase() || ".bin";
  const stablePath = path.join(outDir, `g2b-doc-${String(index + 1).padStart(2, "0")}${extension}`);
  if (path.resolve(filePath) !== path.resolve(stablePath)) {
    fs.copyFileSync(filePath, stablePath);
  }
  return stablePath;
}

function stablePathFor(selected, index, outDir) {
  const extension = String(selected.fileExtnNm || "").toLowerCase() || ".bin";
  return path.join(outDir, `g2b-doc-${String(index + 1).padStart(2, "0")}${extension}`);
}

function connectToPage(wsUrl) {
  let id = 0;
  const pending = new Map();
  const interestingResponses = new Map();

  async function connect() {
    const ws = new WebSocket(wsUrl);

    function send(method, params = {}) {
      const callId = ++id;
      ws.send(JSON.stringify({ id: callId, method, params }));
      return new Promise((resolve, reject) => {
        pending.set(callId, { resolve, reject });
        setTimeout(() => {
          if (pending.has(callId)) {
            pending.delete(callId);
            reject(new Error(`CDP timeout: ${method}`));
          }
        }, 20000);
      });
    }

    ws.addEventListener("message", async (event) => {
      const message = JSON.parse(event.data);
      if (message.id && pending.has(message.id)) {
        pending.get(message.id).resolve(message.result);
        pending.delete(message.id);
        return;
      }
      if (message.method === "Network.responseReceived") {
        const url = message.params.response.url;
        if (url.includes("/fs/fsc/fscb/UntyAtchFile/selectUntyAtchFileList.do")) {
          interestingResponses.set("attachments", message.params.requestId);
        }
      }
    });

    await new Promise((resolve) => ws.addEventListener("open", resolve, { once: true }));
    return { ws, send, interestingResponses };
  }

  return connect();
}

async function main() {
  const { bidNo, bidOrd, outDir } = parseArgs();
  if (!bidNo) throw new Error("--bid-no 값이 필요합니다.");

  fs.mkdirSync(outDir, { recursive: true });
  const before = new Set(fs.readdirSync(outDir));
  const port = 9222 + Math.floor(Math.random() * 1000);
  const profileDir = path.join(os.tmpdir(), `g2b-cdp-${Date.now()}`);
  const url = `https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=${encodeURIComponent(bidNo)}&bidPbancOrd=${encodeURIComponent(bidOrd)}`;

  const chrome = spawn(findChromePath(), [
    "--headless=new",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--no-first-run",
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`,
    "about:blank",
  ], { stdio: "ignore" });

  try {
    await waitForChrome(port);
    const page = await newPage(port, url);
    const { ws, send, interestingResponses } = await connectToPage(page.webSocketDebuggerUrl);
    await send("Network.enable");
    await send("Page.enable");
    await send("Runtime.enable");
    await send("Page.setDownloadBehavior", { behavior: "allow", downloadPath: outDir }).catch(() => undefined);

    let attachments = [];
    for (let i = 0; i < 60; i += 1) {
      await delay(1000);
      const requestId = interestingResponses.get("attachments");
      if (requestId) {
        const body = await send("Network.getResponseBody", { requestId }).catch(() => null);
        if (body?.body) {
          const payload = JSON.parse(body.body);
          attachments = payload.dlUntyAtchFileL || [];
          if (attachments.length) break;
        }
      }
    }

    if (!attachments.length) {
      const state = await send("Runtime.evaluate", {
        expression: `JSON.stringify({ title: document.title, text: (document.body?.innerText || "").slice(-2000) })`,
        returnByValue: true,
      }).catch(() => null);
      throw new Error(`첨부파일 목록을 찾지 못했습니다. page=${state?.result?.value || "unknown"}`);
    }
    const selectedAttachments = selectAttachments(attachments);
    if (!selectedAttachments.length) throw new Error("분석 대상 첨부파일을 찾지 못했습니다.");

    const downloads = [];
    const seen = new Set(before);
    for (const [index, selected] of selectedAttachments.entries()) {
      const cachedStablePath = stablePathFor(selected, index, outDir);
      if (fs.existsSync(cachedStablePath)) {
        const stat = fs.statSync(cachedStablePath);
        if (!selected.fileSz || stat.size === selected.fileSz) {
          downloads.push({ filePath: cachedStablePath, pdfPath: cachedStablePath, selected });
          seen.add(path.basename(cachedStablePath));
          continue;
        }
      }

      const expectedName = decodeHtml(selected.orgnlAtchFileNm);
      const existingPath = path.join(outDir, expectedName);
      if (fs.existsSync(existingPath)) {
        const stat = fs.statSync(existingPath);
        if (!selected.fileSz || stat.size === selected.fileSz) {
          const stablePath = stableCopy(existingPath, selected, index, outDir);
          downloads.push({ filePath: stablePath, pdfPath: stablePath, selected });
          seen.add(path.basename(stablePath));
          continue;
        }
      }

      const downloadOptions = {
        untyAtchFileNo: selected.untyAtchFileNo,
        bsnePath: "PNPE",
        prcmBsneSeCd: selected.bsneClsfCd,
        tblNm: "PBANC_BID_PBANC",
        colNm: "ITEM_PBANC_UNTY_ATCH_FILE_NO",
        atchFileSqno: String(selected.atchFileSqno),
        atchFileNm: selected.atchFileNm,
        orgnlAtchFileNm: selected.orgnlAtchFileNm,
      };

      await send("Runtime.evaluate", {
        expression: `comUtil.gfnFileDownLoad(${JSON.stringify(downloadOptions)})`,
        returnByValue: true,
      });
      const filePath = await waitForFile(outDir, seen, selected.fileSz, String(selected.fileExtnNm || "").toLowerCase());
      const stablePath = stableCopy(filePath, selected, index, outDir);
      seen.add(path.basename(filePath));
      seen.add(path.basename(stablePath));
      downloads.push({ filePath: stablePath, pdfPath: stablePath, selected });
    }

    ws.close();
    process.stdout.write(JSON.stringify({
      pdfPath: downloads[0].filePath,
      selected: downloads[0].selected,
      downloads,
      attachments,
    }, null, 2));
  } finally {
    chrome.kill("SIGTERM");
  }
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
