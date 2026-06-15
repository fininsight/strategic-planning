export type ProposalAnalysisPayload = {
  id: string;
  sourceFile: string;
  generatedAt: string;
  match: ProposalAnalysisMatch;
  noticeInfo: {
    details: NoticeInfoDetail[];
    requirements: NoticeRequirement[];
    summary: NoticeInfoSummary;
  };
  checklist: ProposalChecklist;
  scoring: ProposalScoring;
};

export type ProposalAnalysisMatch = {
  noticeId: string;
  bidNtceNo: string;
  bidNtceOrd: string;
  noticeNumber: string;
  projectName: string;
  keywords: string[];
};

export type NoticeInfoDetail = {
  label: string;
  value: string;
  note: string;
};

export type NoticeRequirement = {
  requirement: string;
  detail: string;
  type: string;
};

export type NoticeInfoSummary = {
  projectName: string;
  agency: string;
  noticeNumber: string;
  budget: string;
  period: string;
  deadline: string;
  method: string;
  contractMethod: string;
};

export type ProposalChecklist = {
  title: string;
  subtitle: string;
  method: string;
  headers: string[];
  organizationHeaders: string[];
  items: ProposalChecklistItem[];
  notes: string[];
};

export type ProposalChecklistItem = {
  no: number;
  document: string;
  form: string;
  owner: string;
  organizations: {
    name: string;
    required: boolean;
    checked: boolean;
  }[];
  deadline: string;
  note: string;
  extra: string;
};

export type ProposalScoring = {
  title: string;
  totalSummary: string;
  items: ProposalScoreItem[];
  totals: {
    score: number;
    weight: number;
    gradeA: number;
    gradeB: number;
    gradeC: number;
  };
};

export type ProposalScoreItem = {
  major: string;
  middle: string;
  minor: string;
  score: number;
  weight: number;
  grade: string;
  strategy: string;
  detail: string;
};
