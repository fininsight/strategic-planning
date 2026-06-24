import { spawn } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import net from "node:net";
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

class MinimalWebSocket {
  constructor(wsUrl) {
    this.listeners = new Map();
    this.buffer = Buffer.alloc(0);
    this.socket = null;
    this.connect(wsUrl);
  }

  addEventListener(type, listener, options = {}) {
    const wrapped = options.once
      ? (event) => {
          this.removeEventListener(type, wrapped);
          listener(event);
        }
      : listener;
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(wrapped);
  }

  removeEventListener(type, listener) {
    this.listeners.get(type)?.delete(listener);
  }

  emit(type, event = {}) {
    for (const listener of this.listeners.get(type) || []) listener(event);
  }

  connect(wsUrl) {
    const parsed = new URL(wsUrl);
    const key = crypto.randomBytes(16).toString("base64");
    const port = Number(parsed.port || 80);
    this.socket = net.createConnection({ host: parsed.hostname, port }, () => {
      this.socket.write(
        [
          `GET ${parsed.pathname}${parsed.search} HTTP/1.1`,
          `Host: ${parsed.host}`,
          "Upgrade: websocket",
          "Connection: Upgrade",
          `Sec-WebSocket-Key: ${key}`,
          "Sec-WebSocket-Version: 13",
          "\r\n",
        ].join("\r\n"),
      );
    });
    this.socket.on("data", (chunk) => this.handleData(chunk));
    this.socket.on("error", (error) => this.emit("error", { error }));
    this.socket.on("close", () => this.emit("close", {}));
  }

  handleData(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    const headerEnd = this.buffer.indexOf("\r\n\r\n");
    if (headerEnd >= 0 && this.buffer.slice(0, headerEnd).includes("HTTP/1.1 101")) {
      this.buffer = this.buffer.slice(headerEnd + 4);
      this.emit("open", {});
    }

    while (this.buffer.length >= 2) {
      const first = this.buffer[0];
      const opcode = first & 0x0f;
      let length = this.buffer[1] & 0x7f;
      let offset = 2;
      if (length === 126) {
        if (this.buffer.length < offset + 2) return;
        length = this.buffer.readUInt16BE(offset);
        offset += 2;
      } else if (length === 127) {
        if (this.buffer.length < offset + 8) return;
        const high = this.buffer.readUInt32BE(offset);
        const low = this.buffer.readUInt32BE(offset + 4);
        length = high * 2 ** 32 + low;
        offset += 8;
      }
      if (this.buffer.length < offset + length) return;
      const payload = this.buffer.slice(offset, offset + length);
      this.buffer = this.buffer.slice(offset + length);

      if (opcode === 1) this.emit("message", { data: payload.toString("utf8") });
      if (opcode === 8) this.close();
    }
  }

  send(text) {
    const payload = Buffer.from(text);
    const mask = crypto.randomBytes(4);
    const headerLength = payload.length < 126 ? 2 : payload.length < 65536 ? 4 : 10;
    const frame = Buffer.alloc(headerLength + 4 + payload.length);
    frame[0] = 0x81;
    if (payload.length < 126) {
      frame[1] = 0x80 | payload.length;
      mask.copy(frame, 2);
      for (let i = 0; i < payload.length; i += 1) frame[6 + i] = payload[i] ^ mask[i % 4];
    } else if (payload.length < 65536) {
      frame[1] = 0x80 | 126;
      frame.writeUInt16BE(payload.length, 2);
      mask.copy(frame, 4);
      for (let i = 0; i < payload.length; i += 1) frame[8 + i] = payload[i] ^ mask[i % 4];
    } else {
      frame[1] = 0x80 | 127;
      frame.writeUInt32BE(0, 2);
      frame.writeUInt32BE(payload.length, 6);
      mask.copy(frame, 10);
      for (let i = 0; i < payload.length; i += 1) frame[14 + i] = payload[i] ^ mask[i % 4];
    }
    this.socket.write(frame);
  }

  close() {
    this.socket?.end();
  }
}

const WebSocketClient = globalThis.WebSocket || MinimalWebSocket;

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

async function waitForChrome(port, getDebugOutput = () => "") {
  const started = Date.now();
  while (Date.now() - started < 30000) {
    try {
      await getJson(port, "/json/version");
      return;
    } catch {
      await delay(300);
    }
  }
  throw new Error(`Chrome 원격 디버깅 포트가 열리지 않았습니다.${getDebugOutput() ? `\n${getDebugOutput()}` : ""}`);
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

function waitForFile(dir, before, expectedExtension = "") {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const timer = setInterval(() => {
      const files = fs
        .readdirSync(dir)
        .filter((name) => !before.has(name) && !name.endsWith(".crdownload"))
        .map((name) => path.join(dir, name));
      const target = files.find((file) => !expectedExtension || file.toLowerCase().endsWith(expectedExtension));
      if (target) {
        clearInterval(timer);
        resolve(target);
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

const ALLOWED_ATTACHMENT_EXTENSIONS = new Set([".pdf", ".hwp", ".hwpx", ".zip"]);

function attachmentLabel(item) {
  return decodeHtml(
    [
      item.atchFileKndNm,
      item.atchFileKndCdNm,
      item.atchFileKndCd,
      item.fileKindName,
      item.fileSeNm,
      item.orgnlAtchFileNm,
      item.atchFileNm,
    ]
      .filter(Boolean)
      .join(" "),
  ).toLowerCase();
}

function isNoticeDocument(item) {
  const label = attachmentLabel(item);
  return label.includes("공고서") || label.includes("공고문") || label.includes("입찰공고");
}

function isConvertedNoticePdf(item) {
  const label = attachmentLabel(item);
  return (
    String(item.fileExtnNm || "").toLowerCase() === ".pdf" &&
    isNoticeDocument(item) &&
    (label.includes("변환본") || label.includes("pdf"))
  );
}

function selectAttachments(attachments) {
  const pdfBases = new Set(
    attachments
      .filter((item) => String(item.fileExtnNm).toLowerCase() === ".pdf")
      .map((item) => withoutExtension(item.orgnlAtchFileNm)),
  );
  const hasConvertedNoticePdf = attachments.some(isConvertedNoticePdf);

  return attachments.filter((item) => {
    const extension = String(item.fileExtnNm || "").toLowerCase();
    if (!ALLOWED_ATTACHMENT_EXTENSIONS.has(extension)) return false;
    if (extension === ".pdf") return true;
    if (hasConvertedNoticePdf && isNoticeDocument(item)) return false;
    return !pdfBases.has(withoutExtension(item.orgnlAtchFileNm));
  });
}

function normalizeAttachment(item) {
  const orgnlAtchFileNm = decodeHtml(
    item.orgnlAtchFileNm ||
      item.orgFileNm ||
      item.fileNm ||
      item.atchFileNm ||
      item.name ||
      "",
  );
  const fileExtnNm = String(
    item.fileExtnNm ||
      item.fileExt ||
      item.fileExtsn ||
      path.extname(orgnlAtchFileNm) ||
      "",
  ).toLowerCase();

  const normalizedExtension = fileExtnNm
    ? fileExtnNm.startsWith(".")
      ? fileExtnNm
      : `.${fileExtnNm}`
    : "";

  return {
    ...item,
    orgnlAtchFileNm,
    fileExtnNm: normalizedExtension,
    fileSz: Number(item.fileSz || item.fileSize || item.atchFileSz || 0),
    atchFileKndCd: item.atchFileKndCd || item.fileKindCode || "",
    atchFileKndNm: item.atchFileKndNm || item.atchFileKndCdNm || item.fileKindName || item.fileSeNm || "",
    untyAtchFileNo: item.untyAtchFileNo || item.atchFileId || item.fileId,
    atchFileSqno: item.atchFileSqno || item.fileSn || item.fileSeq || item.seq || "1",
    atchFileNm: item.atchFileNm || item.fileNm || orgnlAtchFileNm,
    bsneClsfCd: item.bsneClsfCd || item.prcmBsneSeCd || item.bsnePath || "PNPE",
  };
}

function looksLikeAttachment(item) {
  if (!item || typeof item !== "object") return false;
  const fileName = item.orgnlAtchFileNm || item.orgFileNm || item.fileNm || item.atchFileNm || item.name || "";
  const extension = String(
    item.fileExtnNm ||
      item.fileExt ||
      item.fileExtsn ||
      path.extname(fileName) ||
      "",
  ).toLowerCase();
  const hasIdOrSize = item.fileSz || item.fileSize || item.atchFileSz || item.untyAtchFileNo || item.atchFileId || item.fileId;
  return Boolean(fileName && hasIdOrSize && ALLOWED_ATTACHMENT_EXTENSIONS.has(extension.startsWith(".") ? extension : `.${extension}`));
}

function findAttachments(payload) {
  if (payload?.dlUntyAtchFileL && Array.isArray(payload.dlUntyAtchFileL)) {
    return payload.dlUntyAtchFileL.map(normalizeAttachment);
  }

  const found = [];
  const seen = new Set();

  function visit(value) {
    if (!value) return;
    if (Array.isArray(value)) {
      if (value.some(looksLikeAttachment)) {
        for (const item of value.filter(looksLikeAttachment).map(normalizeAttachment)) {
          const key = `${item.orgnlAtchFileNm}|${item.untyAtchFileNo || ""}|${item.atchFileSqno || ""}`;
          if (!seen.has(key)) {
            seen.add(key);
            found.push(item);
          }
        }
      }
      value.forEach(visit);
      return;
    }
    if (typeof value === "object") {
      if (looksLikeAttachment(value)) {
        const item = normalizeAttachment(value);
        const key = `${item.orgnlAtchFileNm}|${item.untyAtchFileNo || ""}|${item.atchFileSqno || ""}`;
        if (!seen.has(key)) {
          seen.add(key);
          found.push(item);
        }
      }
      Object.values(value).forEach(visit);
    }
  }

  visit(payload?.dlUntyAtchFileL || payload?.resultList || payload?.list || payload);
  return found;
}

function connectToPage(wsUrl) {
  let id = 0;
  const pending = new Map();
  const interestingResponses = [];

  async function connect() {
    const ws = new WebSocketClient(wsUrl);

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
        const contentType = String(message.params.response.mimeType || "");
        // 첨부파일 관련 URL이거나 JSON 응답이면 모두 캡처한다.
        // 나라장터 API URL 패턴이 다양하므로 JSON 응답 전체를 대상으로 한다.
        if (/json|text/i.test(contentType) || /atch|file|fsc|pbanc|bid|dlvy|ntce|g2b/i.test(url)) {
          interestingResponses.push({
            requestId: message.params.requestId,
            url,
          });
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
  const profileDir = path.join(process.cwd(), ".cache", "chrome_profiles", crypto.randomUUID());
  const url = `https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=${encodeURIComponent(bidNo)}&bidPbancOrd=${encodeURIComponent(bidOrd)}`;

  const chrome = spawn(findChromePath(), [
    "--headless=new",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--no-first-run",
    "--disable-background-networking",
    "--remote-debugging-address=127.0.0.1",
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`,
    "about:blank",
  ], { stdio: ["ignore", "ignore", "pipe"] });
  let chromeError = "";
  chrome.stderr?.on("data", (chunk) => {
    chromeError += chunk.toString();
    if (chromeError.length > 4000) chromeError = chromeError.slice(-4000);
  });

  try {
    await waitForChrome(port, () => chromeError.trim());
    const page = await newPage(port, "about:blank");
    const { ws, send, interestingResponses } = await connectToPage(page.webSocketDebuggerUrl);
    await send("Network.enable");
    await send("Page.enable");
    await send("Runtime.enable");
    await send("Page.setDownloadBehavior", { behavior: "allow", downloadPath: outDir }).catch(() => undefined);
    await send("Page.navigate", { url });

    let attachments = [];
    for (let i = 0; i < 60; i += 1) {
      await delay(1000);
      const candidates = interestingResponses.splice(0, interestingResponses.length);
      for (const candidate of candidates) {
        const body = await send("Network.getResponseBody", { requestId: candidate.requestId }).catch(() => null);
        if (body?.body) {
          try {
            const payload = JSON.parse(body.body);
            attachments = findAttachments(payload);
            if (attachments.length) break;
          } catch {
            // Ignore non-JSON responses captured by the broad network filter.
          }
        }
      }
      if (attachments.length) break;
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
    for (const selected of selectedAttachments) {
      const expectedName = decodeHtml(selected.orgnlAtchFileNm);
      const existingPath = path.join(outDir, expectedName);
      if (fs.existsSync(existingPath)) {
        const stat = fs.statSync(existingPath);
        if (!selected.fileSz || stat.size === selected.fileSz) {
          downloads.push({ filePath: existingPath, pdfPath: existingPath, selected });
          seen.add(path.basename(existingPath));
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
      const filePath = await waitForFile(outDir, seen, String(selected.fileExtnNm || "").toLowerCase());
      seen.add(path.basename(filePath));
      downloads.push({ filePath, pdfPath: filePath, selected });
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
    try {
      fs.rmSync(profileDir, { recursive: true, force: true, maxRetries: 3, retryDelay: 200 });
    } catch {
      // Chrome may still be flushing cache files; the temp profile is disposable.
    }
  }
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
