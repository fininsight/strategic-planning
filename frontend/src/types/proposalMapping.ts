export type ProposalMappingPayload = {
  id: string;
  generatedAt: string;
  sourceAnalysisAt: string;
  projectName: string;
  sourceFile: string;
  requirementSourceFiles?: string[];
  extractionWarnings?: string[];
  documentTypes: ProposalDocumentType[];
  requirementTraceability: RequirementMapping[];
  scoringPagePlan: ScoringPagePlan[];
  scoringSource?: string;
  tableOfContents: ProposalTocGroup[];
  validation: ProposalMappingValidation;
};

export type ProposalDocumentType = {
  type: "quantitative" | "qualitative" | string;
  label: string;
  detected: boolean;
};

export type RequirementMapping = {
  code: string;
  name: string;
  detail: string;
  source: string;
  proposalType: "quantitative" | "qualitative" | string;
  targetSection: string;
  status: "mapped" | "ambiguous" | string;
  note: string;
};

export type ScoringPagePlan = {
  scoreItem: string;
  score: number;
  targetSection: string;
  proposalType: "quantitative" | "qualitative" | string;
  recommendedPages: number;
  mappedRequirementCodes: string[];
  source?: string;
  detail?: string;
};

export type ProposalTocGroup = {
  proposalType: "quantitative" | "qualitative" | string;
  title: string;
  children: ProposalTocSection[];
};

export type ProposalTocSection = {
  title: string;
  section: string;
  requirementCodes: string[];
  recommendedPages: number;
};

export type ProposalMappingValidation = {
  totalRequirements: number;
  mappedRequirements: number;
  unmappedRequirements: string[];
  ambiguousRequirements: string[];
  isComplete: boolean;
  message: string;
};

export type StrategyResearchPayload = {
  id: string;
  generatedAt: string;
  projectName: string;
  sourceMode: "web_ai" | "fallback" | string;
  status: "verified" | "needs_verification" | "failed" | string;
  executiveSummary: string;
  competitors: StrategyCompetitor[];
  precedents: StrategyPrecedent[];
  marketStats: StrategyMarketStat[];
  trends: StrategyTrend[];
  swot: StrategySwotItem[];
  advantages: StrategyAdvantage[];
  factChecks: StrategyFactCheck[];
  companyEvidence?: StrategyCompanyEvidence[];
  researchPrompt: string;
  warnings: string[];
};

export type StrategySource = {
  title: string;
  url: string;
  publisher?: string;
  publishedAt?: string;
};

export type StrategyCompetitor = {
  name: string;
  expectedRole: string;
  rationale: string;
  likelyPartners: string[];
  sources: StrategySource[];
};

export type StrategyPrecedent = {
  projectName: string;
  buyer: string;
  winner: string;
  year: string;
  contractAmount?: string;
  relevance: string;
  sources: StrategySource[];
};

export type StrategyMarketStat = {
  metric: string;
  value: string;
  period: string;
  interpretation: string;
  verification: "verified" | "unverified" | string;
  sources: StrategySource[];
};

export type StrategyTrend = {
  title: string;
  detail: string;
  implication: string;
  sources: StrategySource[];
};

export type StrategySwotItem = {
  type: "S" | "W" | "O" | "T";
  title: string;
  detail: string;
};

export type StrategyAdvantage = {
  evaluationItem: string;
  finInsightEdge: string;
  evidenceNeeded: string;
  competitorComparison: string;
  priority: "high" | "medium" | "low" | string;
};

export type StrategyFactCheck = {
  claim: string;
  status: "verified" | "unverified" | "conflict" | string;
  note: string;
  sources: StrategySource[];
};

export type StrategyCompanyEvidence = {
  fileName: string;
  docType: string;
  chunkId: string;
  score: number;
  text: string;
};
