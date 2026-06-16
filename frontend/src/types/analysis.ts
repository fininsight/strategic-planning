export type NoticeAnalysis = {
  bidNtceNo?: string;
  bidNtceOrd?: string;
  analyzedAt: string;
  status: "completed";
  source: {
    fileName: string;
    pageCount: number;
    textLength: number;
    extractionMethod: string;
  };
  attachments: {
    fileName: string;
    extension: string;
    size: number;
    kindCode: string;
  }[];
  documents?: AnalysisDocument[];
  documentText: string;
  summary: {
    title: string;
    budget: string;
    deadline: string;
    method: string;
    requirements: { label: string; text: string }[];
    strength: string;
    risk: string;
    opportunity?: string;
    insightSource?: "llm" | "rule";
    insightError?: string;
    timeline: { label: string; date: string }[];
  };
};

export type AnalysisDocument = {
  id: string;
  fileName: string;
  extension: string;
  docType: string;
  viewerType: "pdf" | "text" | "unsupported";
  fileUrl: string;
  originalFileUrl: string;
  pdfUrl: string;
  pageCount: number;
  textLength: number;
  extractionError?: string;
  viewerError?: string;
  documentText?: string;
  analysis: {
    docType: string;
    summary: string;
    checklist: string[];
    scoreTable: { item: string; detail: string }[];
    analysisSource: "llm" | "rule";
  };
};
