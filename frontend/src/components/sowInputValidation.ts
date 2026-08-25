export const MIN_PROJECT_SCOPE_LENGTH = 20;

export const hasProjectScopeSource = (
  projectObjective: string,
  uploadedFiles: File[] | undefined,
): boolean => (
  projectObjective.trim().length >= MIN_PROJECT_SCOPE_LENGTH
  || Boolean(uploadedFiles?.length)
);
