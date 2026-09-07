'use client';
import type { CSSProperties, RefObject } from 'react';
import {
  RefreshCw,
  ExternalLink,
  X,
  LoaderCircle,
  MoreHorizontal,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuCheckboxItem, DropdownMenuRadioGroup, DropdownMenuRadioItem } from '@/components/ui/dropdown-menu';
import { ResizeHandle } from '@/components/panel-resize';
import type { Preview, Workspace } from '@/lib/lab-types';

type Props = {
  preview: Preview;
  visible: boolean;
  previewFull: boolean;
  previewWidth: number;
  fitPreview: boolean;
  setPreviewFull: (value: boolean) => void;
  setPreviewWidth: (value: number) => void;
  setFitPreview: (value: boolean) => void;
  workArea: RefObject<HTMLDivElement | null>;
  previewElement: RefObject<HTMLIFrameElement | null>;
  syncPreviewFit: () => void;
  collapsePreview: () => void;
  openPreview: (
    title: string,
    endpoint: string,
    workspace?: Workspace,
    ide?: boolean,
  ) => Promise<void>;
};
export function PreviewPanel({
  preview,
  visible,
  previewFull,
  previewWidth,
  fitPreview,
  setPreviewFull,
  setPreviewWidth,
  setFitPreview,
  workArea,
  previewElement,
  syncPreviewFit,
  collapsePreview,
  openPreview,
}: Props) {
  return (
    <aside
      aria-hidden={!visible}
      className={`preview-panel ${previewFull ? 'expanded' : ''}`}
      style={
        {
          '--preview-width': previewWidth + '%',
          display: visible ? undefined : 'none',
        } as CSSProperties
      }
    >
      {!previewFull && (
        <ResizeHandle
          side="right"
          value={previewWidth}
          onChange={setPreviewWidth}
          onReset={() => setPreviewWidth(55)}
          min={30}
          max={75}
          container={() => workArea.current}
        />
      )}
      <div className="preview-toolbar">
        <div>
          <strong>{preview.title}</strong>
        </div>
        <div>
          {preview.workspace && (
            <div className="workspace-tabs">
              <Button
                size="sm"
                variant={preview.ide ? 'secondary' : 'ghost'}
                onClick={() =>
                  openPreview(
                    preview.workspace!.project_name || preview.workspace!.name,
                    `/api/developer/workspaces/${preview.workspace!.id}/open`,
                    preview.workspace,
                    true,
                  )
                }
              >
                VS Code
              </Button>
              <Button
                size="sm"
                variant={preview.ide ? 'ghost' : 'secondary'}
                onClick={() =>
                  openPreview(
                    preview.workspace!.project_name || preview.workspace!.name,
                    `/api/developer/workspaces/${preview.workspace!.id}/preview`,
                    preview.workspace,
                  )
                }
              >
                App preview
              </Button>
            </div>
          )}
          <DropdownMenu>
            <DropdownMenuTrigger className="preview-menu-trigger" aria-label="Preview options" title="Preview options"><MoreHorizontal size={18} /></DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-48">
              <DropdownMenuRadioGroup value={previewFull ? 'full' : String(previewWidth)} onValueChange={(value) => {
                setPreviewFull(value === 'full'); if (value !== 'full') setPreviewWidth(Number(value));
              }}>
                <DropdownMenuRadioItem value="40">Narrow · 40%</DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="55">Balanced · 55%</DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="70">Wide · 70%</DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="full">Full width</DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
              {!preview.ide && <DropdownMenuCheckboxItem checked={fitPreview} onCheckedChange={setFitPreview}>Fit content to width</DropdownMenuCheckboxItem>}
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => void openPreview(preview.title, preview.endpoint, preview.workspace, preview.ide)}><RefreshCw size={15} />Reload preview</DropdownMenuItem>
              {preview.url && <DropdownMenuItem render={<a href={preview.url} target="_blank" rel="noreferrer" />}><ExternalLink size={15} />Open in new tab</DropdownMenuItem>}
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Collapse preview"
            onClick={collapsePreview}
          >
            <X size={17} />
          </Button>
        </div>
      </div>
      {preview.error ? (
        <div className="preview-message" role="alert">
          {preview.error}
          <p>
            Use Reload preview to retry. Sleeping workspaces wake automatically
            when needed.
          </p>
        </div>
      ) : preview.url ? (
        <iframe
          onLoad={syncPreviewFit}
          ref={previewElement}
          key={preview.url}
          title={preview.title}
          src={preview.url}
          sandbox={
            preview.ide
              ? 'allow-scripts allow-same-origin allow-forms allow-downloads allow-modals allow-pointer-lock'
              : 'allow-scripts allow-forms allow-downloads'
          }
          allow={
            preview.ide
              ? 'clipboard-read; clipboard-write; microphone'
              : undefined
          }
          referrerPolicy="no-referrer"
        />
      ) : (
        <div className="preview-message">
          <LoaderCircle className="spin" /> Opening preview…
        </div>
      )}

    </aside>
  );
}
