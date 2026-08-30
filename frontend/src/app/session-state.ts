/**
 * In-memory session state — resets to default on every fresh page load / new tab.
 * This is intentional: we never want the dashboard to show stale data from a
 * previous session without the user explicitly uploading a dataset again.
 */

/** True only after the user successfully uploads a dataset in this session. */
export let datasetUploadedThisSession = false;

/** Call this once a dataset commit succeeds. */
export function markDatasetUploaded() {
  datasetUploadedThisSession = true;
}
