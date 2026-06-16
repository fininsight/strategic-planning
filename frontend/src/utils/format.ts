export function buildDeepLink(number: string): string {
  const [bidPbancNo, bidPbancOrd = "000"] = number.split("-");
  return `https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=${bidPbancNo}&bidPbancOrd=${bidPbancOrd}`;
}

export function formatDateTime(value: string): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  const datePart = date.toISOString().slice(0, 10);
  const timePart = date.toTimeString().slice(0, 5);
  return `${datePart} ${timePart}`;
}

export function formatBudget(value: number): string {
  if (!value) return "공고서 확인";
  if (value >= 100000000) {
    const eok = value / 100000000;
    return `${Number.isInteger(eok) ? eok : eok.toFixed(1)} 억원`;
  }
  return `${Math.round(value / 10000).toLocaleString("ko-KR")} 만원`;
}
