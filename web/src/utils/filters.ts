import { BudgetFilter, Notice } from "../types/notice";

export function isSameDate(value: string, base = new Date()): boolean {
  if (!value) return false;
  const target = new Date(value);
  if (Number.isNaN(target.getTime())) return false;
  return (
    target.getFullYear() === base.getFullYear() &&
    target.getMonth() === base.getMonth() &&
    target.getDate() === base.getDate()
  );
}

export function scanBaseDate(generatedAt: string): Date {
  const generated = new Date(generatedAt);
  return Number.isNaN(generated.getTime()) ? new Date() : generated;
}

export function isBudgetMatched(notice: Notice, filter: BudgetFilter): boolean {
  if (filter === "all") return true;
  if (filter === "under100m") return notice.budget < 100000000;
  if (filter === "100mTo300m") return notice.budget >= 100000000 && notice.budget < 300000000;
  return notice.budget >= 300000000;
}

export function uniqueValues<T>(values: T[]): T[] {
  return [...new Set(values)];
}

export function normalizeNotice(notice: Partial<Notice>): Notice {
  return {
    task: notice.task === "물품" ? "물품" : "용역",
    number: notice.number ?? "",
    bidNtceNo: notice.bidNtceNo ?? notice.number?.split("-")[0] ?? "",
    bidNtceOrd: notice.bidNtceOrd ?? notice.number?.split("-")[1] ?? "000",
    deepLink: notice.deepLink ?? "",
    category: notice.category === "긴급" ? "긴급" : "일반",
    title: notice.title ?? "",
    agency: notice.agency ?? "",
    closeAt: notice.closeAt ?? "",
    postedAt: notice.postedAt ?? "",
    method: notice.method ?? "미분류",
    region: notice.region || "전국",
    industry: notice.industry || "미분류",
    matchedCodes: Array.isArray(notice.matchedCodes) ? notice.matchedCodes : [],
    qualificationSource: notice.qualificationSource ?? "",
    budget: Number(notice.budget ?? 0),
    score: Number(notice.score ?? 0),
    grade: notice.grade ?? "",
    reasons: Array.isArray(notice.reasons) ? notice.reasons : [],
    keywords: Array.isArray(notice.keywords) ? notice.keywords : [],
  };
}
