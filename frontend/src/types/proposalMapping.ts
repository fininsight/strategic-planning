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
