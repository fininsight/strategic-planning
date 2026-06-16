export type BudgetFilter = "all" | "under100m" | "100mTo300m" | "over300m";
export type SortField = "score" | "closeAt" | "postedAt" | "budget" | "title";
export type SortOrder = "desc" | "asc";

export type Notice = {
  task: "용역" | "물품";
  number: string;
  bidNtceNo?: string;
  bidNtceOrd?: string;
  deepLink?: string;
  category: "일반" | "긴급";
  title: string;
  agency: string;
  closeAt: string;
  postedAt: string;
  method: string;
  region: string;
  industry: string;
  matchedCodes: string[];
  qualificationSource: string;
  budget: number;
  score: number;
  grade: string;
  reasons?: string[];
  keywords: string[];
};

export type DashboardPayload = {
  generatedAt: string;
  summary: {
    qualified: number;
    disqualified: number;
    keywords: string[];
  };
  notices: Notice[];
};
