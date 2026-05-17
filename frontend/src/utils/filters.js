export function cleanFilters(filters) {
  return Object.fromEntries(
    Object.entries(filters).filter(([, value]) => value !== undefined && value !== null && value !== '')
  );
}

export function localSearch(items, search, fields) {
  const term = String(search || '').toLowerCase().trim();
  if (!term) return items;
  return items.filter((item) =>
    fields.some((field) => String(item[field] || '').toLowerCase().includes(term))
  );
}

export function sourceFilter(source) {
  return source ? { source } : {};
}
