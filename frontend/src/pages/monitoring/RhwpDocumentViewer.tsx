import { useEffect, useMemo, useState } from "react";
import init, { HwpDocument } from "@rhwp/core";
import rhwpWasmUrl from "@rhwp/core/rhwp_bg.wasm?url";

type RhwpDocumentViewerProps = {
  fileName: string;
  fileUrl: string;
  pdfUrl?: string;
};

const INITIAL_PAGE_COUNT = 8;
const PAGE_BATCH_SIZE = 8;
const CANVAS_SCALE = 1.35;
const FONT_FALLBACKS: Array<[RegExp, string]> = [
  [/한컴바탕|함초롬바탕|HY명조|HCR Batang|Batang|바탕|궁서/gi, '"Noto Serif KR", "Nanum Myeongjo", serif'],
  [
    /한컴돋움|함초롬돋움|HY고딕|HCR Dotum|Dotum|돋움|굴림|Malgun Gothic|맑은 고딕/gi,
    '"Noto Sans KR", "Nanum Gothic", sans-serif',
  ],
  [/Arial|Calibri|Helvetica/gi, '"Noto Sans KR", sans-serif'],
  [/Times New Roman/gi, '"Noto Serif KR", serif'],
];

let initPromise: Promise<unknown> | null = null;
let measureContext: CanvasRenderingContext2D | null = null;
let measureFont = "";

declare global {
  // rhwp calls this from WASM while calculating text layout.
  // eslint-disable-next-line no-var
  var measureTextWidth: ((font: string, text: string) => number) | undefined;
}

type RenderState =
  | { status: "loading"; pages: RenderedPage[]; pageCount: number; error: "" }
  | { status: "ready"; pages: RenderedPage[]; pageCount: number; error: "" }
  | { status: "failed"; pages: RenderedPage[]; pageCount: number; error: string };

type RenderMode = "svg" | "canvas";

type RenderedPage =
  | { kind: "svg"; content: string }
  | { kind: "canvas"; content: string; width: number; height: number };

export default function RhwpDocumentViewer({ fileName, fileUrl, pdfUrl = "" }: RhwpDocumentViewerProps) {
  const [visibleCount, setVisibleCount] = useState(INITIAL_PAGE_COUNT);
  const [renderMode, setRenderMode] = useState<RenderMode>("canvas");
  const [renderState, setRenderState] = useState<RenderState>({
    status: "loading",
    pages: [],
    pageCount: 0,
    error: "",
  });
  const wasmUrl = useMemo(() => new URL(rhwpWasmUrl, window.location.href).toString(), []);

  useEffect(() => {
    setVisibleCount(INITIAL_PAGE_COUNT);
  }, [fileUrl]);

  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;

    async function renderDocument() {
      setRenderState((current) => ({
        status: "loading",
        pages: current.pages,
        pageCount: current.pageCount,
        error: "",
      }));

      try {
        await ensureRhwpReady(wasmUrl);
        const response = await fetch(fileUrl, { signal: controller.signal });
        if (!response.ok) {
          throw new Error(`원본 파일을 불러오지 못했습니다. (${response.status})`);
        }

        const data = new Uint8Array(await response.arrayBuffer());
        const document = new HwpDocument(data);
        try {
          prepareDocumentLayout(document);
          const pageCount = document.pageCount();
          const pagesToRender = Math.max(0, Math.min(pageCount, visibleCount));
          const pages = Array.from({ length: pagesToRender }, (_, pageIndex) =>
            renderPage(document, pageIndex, renderMode),
          );

          if (!disposed) {
            setRenderState({ status: "ready", pages, pageCount, error: "" });
          }
        } finally {
          document.free();
        }
      } catch (error) {
        if (disposed || controller.signal.aborted) return;
        setRenderState({
          status: "failed",
          pages: [],
          pageCount: 0,
          error: error instanceof Error ? error.message : "HWP/HWPX 뷰어 렌더링에 실패했습니다.",
        });
      }
    }

    renderDocument();

    return () => {
      disposed = true;
      controller.abort();
    };
  }, [fileUrl, renderMode, visibleCount, wasmUrl]);

  const hasMorePages = renderState.status === "ready" && renderState.pages.length < renderState.pageCount;

  if (renderState.status === "failed") {
    return (
      <div className="documentEmpty">
        <strong>{fileName}</strong>
        <p>{renderState.error}</p>
        <a className="fileDownloadButton" href={fileUrl}>
          원본 다운로드
        </a>
      </div>
    );
  }

  return (
    <div className="rhwpViewer">
      <div className="rhwpViewerToolbar">
        <strong>{fileName}</strong>
        <div className="rhwpViewerActions">
          <div className="rhwpModeControl" aria-label="HWP 렌더링 방식">
            <button className={renderMode === "svg" ? "active" : ""} type="button" onClick={() => setRenderMode("svg")}>
              SVG
            </button>
            <button
              className={renderMode === "canvas" ? "active" : ""}
              type="button"
              onClick={() => setRenderMode("canvas")}
            >
              Canvas
            </button>
          </div>
          {pdfUrl ? (
            <a href={pdfUrl} target="_blank" rel="noreferrer">
              PDF
            </a>
          ) : null}
          <a href={fileUrl}>원본</a>
          <span>
            {renderState.pageCount
              ? `${renderState.pages.length.toLocaleString("ko-KR")} / ${renderState.pageCount.toLocaleString("ko-KR")}페이지`
              : "렌더링 중"}
          </span>
        </div>
      </div>
      <div className="rhwpPages" aria-busy={renderState.status === "loading"}>
        {renderState.pages.map((page, index) => (
          <section className="rhwpPage" aria-label={`${index + 1}페이지`} key={`${fileUrl}-${index}`}>
            {page.kind === "svg" ? (
              <div dangerouslySetInnerHTML={{ __html: page.content }} />
            ) : (
              <img src={page.content} width={page.width} height={page.height} alt={`${index + 1}페이지`} />
            )}
          </section>
        ))}
        {renderState.status === "loading" && !renderState.pages.length ? (
          <div className="rhwpLoading">
            <strong>HWP/HWPX 뷰어 준비 중</strong>
            <p>원본 문서를 렌더링하고 있습니다.</p>
          </div>
        ) : null}
      </div>
      {hasMorePages ? (
        <button className="rhwpMoreButton" type="button" onClick={() => setVisibleCount((count) => count + PAGE_BATCH_SIZE)}>
          {PAGE_BATCH_SIZE}페이지 더 보기
        </button>
      ) : null}
    </div>
  );
}

function ensureRhwpReady(wasmUrl: string) {
  if (!globalThis.measureTextWidth) {
    globalThis.measureTextWidth = (font, text) => {
      if (!measureContext) {
        measureContext = document.createElement("canvas").getContext("2d");
      }
      if (!measureContext) return text.length * 10;
      const normalizedFont = normalizeFont(font);
      if (normalizedFont !== measureFont) {
        measureContext.font = normalizedFont;
        measureFont = normalizedFont;
      }
      return measureContext.measureText(text).width;
    };
  }

  if (!initPromise) {
    initPromise = Promise.all([waitForDocumentFonts(), init({ module_or_path: wasmUrl })]);
  }
  return initPromise;
}

async function waitForDocumentFonts() {
  if (!("fonts" in document)) return;
  try {
    await Promise.race([
      document.fonts.ready,
      new Promise((resolve) => {
        window.setTimeout(resolve, 1400);
      }),
    ]);
  } catch {
    // Font loading is an enhancement; rendering can continue with system fonts.
  }
}

function prepareDocumentLayout(document: HwpDocument) {
  try {
    document.setDpi(window.devicePixelRatio > 1 ? 120 : 96);
  } catch {
    // Older rhwp builds may ignore DPI changes.
  }
  try {
    document.reflowLinesegs();
  } catch {
    // Reflow is best effort; some documents render fine without it.
  }
}

function renderPage(document: HwpDocument, pageIndex: number, mode: RenderMode): RenderedPage {
  if (mode === "canvas") {
    return renderCanvasPage(document, pageIndex);
  }

  const svg = sanitizeSvg(document.renderPageSvg(pageIndex));
  if (!hasVisibleSvgContent(svg)) {
    return renderCanvasPage(document, pageIndex);
  }
  return { kind: "svg", content: svg };
}

function renderCanvasPage(document: HwpDocument, pageIndex: number): RenderedPage {
  const canvas = window.document.createElement("canvas");
  document.renderPageToCanvas(pageIndex, canvas, CANVAS_SCALE);
  return {
    kind: "canvas",
    content: canvas.toDataURL("image/png"),
    width: canvas.width,
    height: canvas.height,
  };
}

function sanitizeSvg(svg: string) {
  const parsed = new DOMParser().parseFromString(svg, "image/svg+xml");
  const root = parsed.documentElement;
  if (!root || root.nodeName.toLowerCase() === "parsererror") {
    return "";
  }

  root.querySelectorAll("script, foreignObject, iframe, object, embed").forEach((element) => element.remove());
  root.querySelectorAll("*").forEach((element) => {
    for (const attribute of Array.from(element.attributes)) {
      const name = attribute.name.toLowerCase();
      const value = attribute.value.trim().toLowerCase();
      if (name.startsWith("on") || value.startsWith("javascript:")) {
        element.removeAttribute(attribute.name);
      }
    }
  });

  return new XMLSerializer().serializeToString(root);
}

function hasVisibleSvgContent(svg: string) {
  return /<(text|path|rect|line|polyline|polygon|circle|ellipse|image)\b/i.test(svg);
}

function normalizeFont(font: string) {
  return FONT_FALLBACKS.reduce((normalized, [pattern, fallback]) => normalized.replace(pattern, fallback), font);
}
