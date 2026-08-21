import React, { useEffect, useRef, useState } from 'react';
import ReactDOM from 'react-dom';
import { ExternalLink, X } from 'lucide-react';
import apiService from '../services/apiService';

export interface ArchitectureDiagramAsset {
  type: 'drawio_architecture';
  title: string;
  alt_text?: string;
  caption?: string;
  drawio_xml: string;
  image_base64: string;
  edit_url: string;
  [key: string]: unknown;
}

interface DiagramEditorModalProps {
  previewId: string;
  asset: ArchitectureDiagramAsset;
  diagramIndex?: number;
  onClose: () => void;
  onSaved: (asset: ArchitectureDiagramAsset) => void;
}

const DRAWIO_BASE = (process.env.REACT_APP_DRAWIO_EMBED_URL || 'https://embed.diagrams.net').replace(/\/$/, '');
const DRAWIO_ORIGIN = new URL(DRAWIO_BASE).origin;
const DRAWIO_URL = `${DRAWIO_BASE}/?embed=1&proto=json&spin=1&libraries=1&saveAndExit=1`;

const DiagramEditorModal: React.FC<DiagramEditorModalProps> = ({ previewId, asset, diagramIndex = 0, onClose, onSaved }) => {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const pendingXml = useRef(asset.drawio_xml);
  const closeAfterSave = useRef(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const receive = async (event: MessageEvent) => {
      if (event.origin !== DRAWIO_ORIGIN || event.source !== iframeRef.current?.contentWindow) return;
      let message: any;
      try {
        message = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
      } catch {
        return;
      }

      if (message?.event === 'init') {
        iframeRef.current?.contentWindow?.postMessage(JSON.stringify({
          action: 'load',
          xml: asset.drawio_xml,
          title: asset.title || 'Architecture Diagram',
          fit: 1,
          autosave: 0,
          exportProtocol: true,
          saveAndExit: 1,
        }), DRAWIO_ORIGIN);
        return;
      }

      if (message?.event === 'save' && message.xml) {
        pendingXml.current = message.xml;
        closeAfterSave.current = Boolean(message.exit);
        setSaving(true);
        setError('');
        iframeRef.current?.contentWindow?.postMessage(JSON.stringify({
          action: 'export',
          format: 'png',
          xml: message.xml,
          scale: 2,
          border: 20,
          background: '#ffffff',
          spin: 'Rendering diagram…',
        }), DRAWIO_ORIGIN);
        return;
      }

      if (message?.event === 'export' && message.data) {
        try {
          const response = await apiService.updateArchitectureDiagram(
            previewId,
            pendingXml.current,
            message.data,
            diagramIndex,
          );
          if (!response.success || !response.asset) {
            throw new Error(response.error || 'Unable to save diagram');
          }
          onSaved(response.asset as ArchitectureDiagramAsset);
          iframeRef.current?.contentWindow?.postMessage(JSON.stringify({
            action: 'status',
            message: 'Diagram saved to the SOW preview',
            modified: false,
          }), DRAWIO_ORIGIN);
          if (closeAfterSave.current) onClose();
        } catch (saveError) {
          setError(saveError instanceof Error ? saveError.message : 'Unable to save diagram');
        } finally {
          setSaving(false);
        }
        return;
      }

      if (message?.event === 'exit') onClose();
    };

    window.addEventListener('message', receive);
    return () => window.removeEventListener('message', receive);
  }, [asset.drawio_xml, asset.title, diagramIndex, onClose, onSaved, previewId]);

  return ReactDOM.createPortal(
    <div className="modal-overlay diagram-editor-overlay">
      <div className="diagram-editor-modal" onClick={(event) => event.stopPropagation()}>
        <div className="modal-header diagram-editor-header">
          <div>
            <h2>Edit Architecture Diagram</h2>
            <p>Use Save in draw.io to update this SOW preview.</p>
          </div>
          <div className="diagram-editor-actions">
            <a href={asset.edit_url} target="_blank" rel="noreferrer" className="modal-btn modal-btn-secondary">
              <ExternalLink size={15} /> Open Full Editor
            </a>
            <button className="modal-close" onClick={onClose} aria-label="Close diagram editor">
              <X size={20} />
            </button>
          </div>
        </div>
        {error && <div className="diagram-editor-error">{error}</div>}
        {saving && <div className="diagram-editor-saving">Rendering and saving diagram…</div>}
        <iframe
          ref={iframeRef}
          className="diagram-editor-frame"
          src={DRAWIO_URL}
          title="draw.io architecture diagram editor"
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-downloads"
        />
      </div>
    </div>,
    document.body,
  );
};

export default DiagramEditorModal;
