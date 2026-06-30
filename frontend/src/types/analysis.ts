export type NoticeAnalysis = {
  bidNtceNo: string;
  bidNtceOrd: string;
  analyzedAt: string;
  status: "documents_ready" | "completed" | "download_failed" | string;
  downloadError?: string;
  source: {
    fileName: string;
    pdfPath: string;
    pageCount: number;
    textLength: number;
    extractionMethod: string;
  };
  attachments: NoticeAttachment[];
  documents: NoticeDocument[];
  documentText: string;
  summary: NoticeSummary;
};

export type NoticeAttachment = {
  fileName: string;
  extension: string;
  size: number;
  kindCode: string;
};

export type NoticeDocument = {
  id: string;
  fileName: string;
  extension: string;
  docType: string;
  viewerType: "pdf" | "html" | "rhwp" | "text" | "unsupported" | string;
  fileUrl: string;
  originalFileUrl: string;
  pdfUrl: string;
  filePath: string;
  viewerPath: string;
  pdfPath: string;
  pageCount: number;
  textLength: number;
  extractionMethod: string;
  extractionError: string;
  viewerError: string;
  documentText: string;
  analysis: NoticeDocumentAnalysis;
};

export type NoticeDocumentAnalysis = {
  docType: string;
  summary: string;
  checklist: string[];
  requirements: string[];
  risks: string[];
  scoringHints: string[];
  scoreTable: NoticeDocumentScoreTableItem[];
  analysisSource: "llm" | "rule" | string;
};

export type NoticeDocumentScoreTableItem = {
  item: string;
  detail: string;
};

export type NoticeSummary = {
  title: string;
  budget: string;
  deadline: string;
  method: string;
  requirements: NoticeSummaryRequirement[];
  strength: string;
  risk: string;
  opportunity: string;
  timeline: NoticeTimelineItem[];
  analysisVersion: number;
  insightSource: "llm" | "rule" | string;
  documentCount: number;
};

export type NoticeSummaryRequirement = {
  label: string;
  text: string;
};

export type NoticeTimelineItem = {
  label: string;
  date: string;
};
