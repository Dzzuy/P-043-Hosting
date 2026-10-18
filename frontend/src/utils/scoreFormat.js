export const CRITERIA = [
  { key: 'need_discovery', label: 'Khám phá nhu cầu', short: 'Khám phá nhu cầu' },
  { key: 'product_knowledge', label: 'Kiến thức sản phẩm', short: 'Kiến thức sản phẩm' },
  { key: 'objection_handling', label: 'Xử lý phản đối', short: 'Xử lý phản đối' },
  { key: 'policy_accuracy', label: 'Chính xác chính sách', short: 'Chính xác chính sách' },
  { key: 'closing_next_step', label: 'Chốt bước tiếp theo', short: 'Chốt bước tiếp theo' },
];

export const CRITERION_LABEL = Object.fromEntries(CRITERIA.map((item) => [item.key, item.label]));

/** 2.5 -> "2,5". Null or non-finite -> "—". */
export function fmtScore(value, digits = 1) {
  if (value == null || !Number.isFinite(Number(value))) return '—';
  return Number(value).toFixed(digits).replace('.', ',');
}

/** Signed change: +0,4 / −0,1 / 0,0. Null -> "—". */
export function fmtDelta(value) {
  if (value == null || !Number.isFinite(Number(value))) return '—';
  const rounded = Math.round(Number(value) * 10) / 10;
  if (rounded === 0) return '0,0';
  return `${rounded > 0 ? '+' : '−'}${Math.abs(rounded).toFixed(1).replace('.', ',')}`;
}

/** ISO datetime/date -> dd/mm */
export function fmtDayMonth(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return `${String(date.getDate()).padStart(2, '0')}/${String(date.getMonth() + 1).padStart(2, '0')}`;
}

/** Whole calendar days between a past ISO time and now. */
export function daysSince(value, now = new Date()) {
  if (!value) return null;
  const then = new Date(value);
  if (Number.isNaN(then.getTime())) return null;
  const startOf = (date) => new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  return Math.max(0, Math.round((startOf(now) - startOf(then)) / 86400000));
}

/** Initials for an avatar, e.g. "Phạm Đình Duy" -> "PD". */
export function initialsOf(name) {
  const parts = String(name || '').trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

export function sparkPoints(values, width, height, pad = 4) {
  // values: array of number|null on a 1..3 scale; returns runs of "x,y" strings (split on nulls)
  const count = values.length;
  const runs = [];
  let run = [];
  values.forEach((value, index) => {
    if (value == null) {
      if (run.length) runs.push(run);
      run = [];
      return;
    }
    const x = count === 1 ? width / 2 : pad + (index * (width - pad * 2)) / (count - 1);
    const y = pad + ((3 - Math.min(3, Math.max(1, value))) / 2) * (height - pad * 2);
    run.push({ x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10 });
  });
  if (run.length) runs.push(run);
  return runs;
}
