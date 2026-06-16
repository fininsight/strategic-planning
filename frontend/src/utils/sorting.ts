import { Notice, SortField, SortOrder } from "../types/notice";

export function compareNotices(a: Notice, b: Notice, field: SortField, order: SortOrder): number {
  const direction = order === "desc" ? -1 : 1;

  if (field === "title") {
    return a.title.localeCompare(b.title, "ko") * direction;
  }

  if (field === "closeAt" || field === "postedAt") {
    const aTime = new Date(a[field]).getTime();
    const bTime = new Date(b[field]).getTime();
    return ((Number.isNaN(aTime) ? 0 : aTime) - (Number.isNaN(bTime) ? 0 : bTime)) * direction;
  }

  return (a[field] - b[field]) * direction;
}
