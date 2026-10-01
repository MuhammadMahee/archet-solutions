'use strict';

async function syncSalesSources(progress, isCurrent) {
  let continuation = false;
  while (isCurrent()) {
    const result = await api('sales/refresh', 'POST', continuation ? {continue: true} : {});
    if (!isCurrent()) return null;
    if (result.status === 'busy' || !result.remaining || !result.due) return result;
    // Do not loop indefinitely if the server could not make progress.
    if (!(result.workers || []).some(worker => worker.completed > 0)) return result;
    progress(`${result.remaining} account-days remain. Fetching the next batch\u2026`);
    continuation = true;
  }
  return null;
}

function sourceSyncMessage(result) {
  if (result.status === 'busy') return 'Another source sync is already running. Try again after it finishes.';
  if (!result.remaining) return 'Sources are up to date.';
  const errors = [...new Set((result.workers || []).map(worker => worker.error).filter(Boolean))];
  return `${result.remaining} account-days could not be fetched${errors.length ? ' (' + errors.join(', ') + ')' : ''}. Saved data was kept. Click Sync sources to retry now.`;
}
