import React from 'react';
import { AlertTriangle, Trash2, X } from 'lucide-react';
import './SOWDeleteDialog.css';

interface Props {
  name: string;
  deleting?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

const SOWDeleteDialog: React.FC<Props> = ({ name, deleting, onCancel, onConfirm }) => (
  <div className="sow-delete-overlay" role="presentation" onMouseDown={() => !deleting && onCancel()}>
    <div className="sow-delete-dialog" role="dialog" aria-modal="true" aria-labelledby="sow-delete-title" onMouseDown={event => event.stopPropagation()}>
      <button type="button" className="sow-delete-close" aria-label="Close" disabled={deleting} onClick={onCancel}><X size={19} /></button>
      <div className="sow-delete-warning"><AlertTriangle size={25} /></div>
      <h2 id="sow-delete-title">Permanently delete SOW?</h2>
      <p><strong>{name}</strong> will be removed from all records, trackers and project views.</p>
      <p className="sow-delete-irreversible">This action is irreversible and the generated file cannot be recovered.</p>
      <div className="sow-delete-actions">
        <button type="button" className="sow-delete-cancel" disabled={deleting} onClick={onCancel}>Cancel</button>
        <button type="button" className="sow-delete-confirm" disabled={deleting} onClick={onConfirm}>
          <Trash2 size={16} /> {deleting ? 'Deleting…' : 'Delete permanently'}
        </button>
      </div>
    </div>
  </div>
);

export default SOWDeleteDialog;
