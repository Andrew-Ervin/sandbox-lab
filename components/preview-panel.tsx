'use client';
import type { CSSProperties, RefObject } from 'react';
import {
  AppWindow,
  Monitor,
  RefreshCw,
  ExternalLink,
  X,
  LoaderCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
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
          {preview.ide ? <Monitor size={17} /> : <AppWindow size={17} />}
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
                    preview.workspace!.name,
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
                    preview.workspace!.name,
                    `/api/developer/workspaces/${preview.workspace!.id}/preview`,
                    preview.workspace,
                  )
                }
              >
                App preview
              </Button>
            </div>
          )}
          <label className="preview-width-control" title="Preview width">
            <span className="sr-only">Preview width</span>
            <select
              aria-label="Preview width"
              value={previewFull ? 'full' : String(previewWidth)}
              onChange={(e) => {
                setPreviewFull(e.target.value === 'full');
                if (e.target.value !== 'full')
                  setPreviewWidth(Number(e.target.value));
              }}
            >
              {![40, 55, 70].includes(previewWidth) && (
                <option value={previewWidth}>
                  {Math.round(previewWidth)}%
                </option>
              )}
              <option value="40">40%</option>
              <option value="55">55%</option>
              <option value="70">70%</option>
              <option value="full">Full</option>
            </select>
          </label>
          {!preview.ide &&
            !/\.(png|jpe?g|webp|gif|svg)$/i.test(preview.title) && (
              <Button
                variant={fitPreview ? 'secondary' : 'ghost'}
                size="sm"
                aria-pressed={fitPreview}
                title="Fit content to preview width"
                onClick={() => setFitPreview(!fitPreview)}
              >
                {fitPreview ? 'Fit width' : 'Actual size'}
              </Button>
            )}
          <Button
            variant="ghost"
            size="icon"
            aria-label="Reload preview"
            onClick={() =>
              openPreview(
                preview.title,
                preview.endpoint,
                preview.workspace,
                preview.ide,
              )
            }
          >
            <RefreshCw size={16} />
          </Button>
          {preview.url && (
            <a
              href={preview.url}
              target="_blank"
              rel="noreferrer"
              aria-label="Open preview in new tab"
            >
              <ExternalLink size={16} />
            </a>
          )}
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
      <div className="preview-caption">
        {preview.ide
          ? 'Your developer workspace · terminal and files inside VS Code'
          : preview.workspace
            ? 'Workspace app on port 3000 · isolated preview'
            : 'Isolated preview · application credentials are not forwarded'}
      </div>
    </aside>
  );
}
