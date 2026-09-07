'use client';
import { useCallback, useState } from 'react';

// Preview contents remain mounted when collapsed; briefly reopening preserves the IDE.
export function usePaneLayout() {
  const [historyOpen, setHistoryOpen] = useState(true);
  const [mobileHistoryOpen, setMobileHistoryOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const openPreview = useCallback(() => {
    setHistoryOpen(false);
    setMobileHistoryOpen(false);
    setPreviewOpen(true);
  }, []);
  const changeHistory = useCallback((open: boolean) => {
    setHistoryOpen(open);
    if (open) setPreviewOpen(false);
  }, []);
  const changeMobileHistory = useCallback((open: boolean) => {
    setMobileHistoryOpen(open);
    if (open) setPreviewOpen(false);
  }, []);
  return {
    historyOpen,
    mobileHistoryOpen,
    previewOpen,
    openPreview,
    changeHistory,
    changeMobileHistory,
    collapsePreview: () => setPreviewOpen(false),
  };
}
