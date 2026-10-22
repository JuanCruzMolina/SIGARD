// Only the dev:demo coordinator sets this non-VITE define. A production build
// always folds DEV to false, including builds made with a misleading env flag.
export const demoMode = import.meta.env.DEV && import.meta.env.SIGARD_DEMO === true
