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
  webEvidence?: StrategyWebEvidenceGroup[];
  researchQueries?: StrategyResearchQueries;
  researchMemory?: StrategyResearchMemory;
  researchQuality?: StrategyResearchQuality;
  researchPrompt: string;
  warnings: string[];
};

export type StrategySource = {
  title: string;
  url: string;
  publisher?: string;
  publishedAt?: string;
  authorityTier?: "tier1" | "tier2" | "tier3" | "tier4" | string;
};

export type StrategyCompetitor = {
  name: string;
  expectedRole: string;
  rationale: string;
  likelyPartners: string[];
  winRecords?: string[];
  strengths?: string[];
  weaknesses?: string[];
  threatLevel?: "high" | "medium" | "low" | string;
  responseStrategy?: string;
  sources: StrategySource[];
};

export type StrategyPrecedent = {
  projectName: string;
  buyer: string;
  winner: string;
  year: string;
  contractAmount?: string;
  relevance: string;
  outcome?: string;
  proposalImplication?: string;
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
  evidenceSources?: StrategyAdvantageEvidence[];
};

export type StrategyAdvantageEvidence = {
  fileName: string;
  docType?: string;
  text: string;
};

export type StrategyFactCheck = {
  claim: string;
  status: "verified" | "unverified" | "conflict" | string;
  verdict?: "VERIFIED" | "PARTIAL" | "OUTDATED" | "WEAK_SOURCE" | "CONTRADICTED" | "NOT_FOUND" | string;
  category?: "numeric" | "competitor" | "legal" | "tech" | "company" | "other" | string;
  confidence?: number;
  note: string;
  issue?: string;
  suggestedFix?: string;
  citationText?: string;
  sources: StrategySource[];
};

export type StrategyCompanyEvidence = {
  fileName: string;
  docType: string;
  chunkId: string;
  score: number;
  text: string;
};

export type StrategyWebEvidenceGroup = {
  category: string;
  label: string;
  queries: string[];
  findings: StrategyWebFinding[];
  warnings?: string[];
};

export type StrategyWebFinding = {
  category: string;
  claim: string;
  summary: string;
  relevance?: string;
  sources: StrategySource[];
};

export type StrategyResearchQueries = {
  coreContext?: Record<string, unknown>;
  competitors?: string[];
  precedents?: string[];
  marketTrends?: string[];
  companyPositioning?: string[];
  factCheck?: string[];
  authorityTiers?: Record<string, string[]>;
};

export type StrategyResearchMemory = {
  verifiedNumbers: string[];
  verifiedWins: string[];
  usableCitations: string[];
  finInsightEdges: string[];
  gaps: string[];
};

export type StrategyResearchQuality = {
  sourcedFacts: number;
  verifiedClaims: number;
  verifiedMarketStats: number;
  sourcedCompetitors: number;
  sourcedPrecedents: number;
  sourcedTrends?: number;
};
