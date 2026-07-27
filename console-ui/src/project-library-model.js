export function projectLibraryVersionCandidates(items, selected) {
  if (!selected) return [];
  return items
    .filter((item) => (
      item.asset_id !== selected.asset_id
      && item.file_type === selected.file_type
    ))
    .sort((left, right) => (
      Number(right.work_id === selected.work_id) - Number(left.work_id === selected.work_id)
      || right.revision_number - left.revision_number
      || right.created_at.localeCompare(left.created_at)
    ));
}

export function projectLibrarySourceLabel(item) {
  if (item.source_kind === 'planning_input') return '输入材料';
  if (item.source_kind === 'registered_output') return '已登记产物';
  return '运行目录产物 · 未登记';
}

export function splitProjectLibraryTags(value) {
  const seen = new Set();
  const tags = [];
  value.split(/[,，]/).forEach((raw) => {
    const tag = raw.trim().replace(/\s+/g, ' ');
    const identity = tag.toLocaleLowerCase();
    if (!tag || seen.has(identity)) return;
    seen.add(identity);
    tags.push(tag);
  });
  return tags.slice(0, 20);
}
