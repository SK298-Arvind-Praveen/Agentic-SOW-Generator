export const hasProjectScopeSource = (
  projectObjective: string,
  uploadedFiles: File[] | undefined,
): boolean => (
  projectObjective.trim().length > 0
  || Boolean(uploadedFiles?.length)
);
