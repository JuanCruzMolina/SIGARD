// The exact-values ("private research") mode of the predictive viewer is hidden unless the
// local dev command is started with SIGARD_PRIVATE_VIEW=1. Only that coordinator sets this
// non-VITE define; a production build always folds DEV to false. The API keeps applying its
// own protection regardless of what the interface shows.
export const privateViewEnabled = import.meta.env.DEV && import.meta.env.SIGARD_PRIVATE_VIEW === true
