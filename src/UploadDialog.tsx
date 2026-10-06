import { Button } from '@/components/ui/button';
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Download,
  FileText,
  LoaderCircle,
  ShieldCheck,
  UploadCloud,
  X,
} from 'lucide-react';
import { useRef, useState } from 'react';
import { upload as uploadBlob } from '@vercel/blob/client';
import { api, apiUrl, jsonRequest, kindLabel } from './api';
import type { Kind } from './types';
import { Modal } from './ui';

const kinds: Kind[] = ['invoice', 'purchase_order', 'delivery'];
function FileSlot({
  kind,
  file,
  choose,
  error,
}: {
  kind: Kind;
  file?: File;
  choose: (file?: File) => void;
  error?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const select = (file?: File) => {
    choose(file);
    if (input.current) input.current.value = '';
  };
  return (
    <div
      className={`upload-slot ${drag ? 'dragging' : ''} ${file ? 'has-file' : ''}`}
      onDragOver={(event) => {
        event.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDrag(false);
        select(event.dataTransfer.files[0]);
      }}
    >
      <div className="slot-label">
        <span className={`slot-number file-${kind}`}>{kinds.indexOf(kind) + 1}</span>
        <strong>{kindLabel[kind]}</strong>
        {file && <CheckCircle2 size={16} className="green-text" />}
      </div>
      <input
        ref={input}
        type="file"
        tabIndex={-1}
        accept=".pdf,.png,.jpg,.jpeg,.txt"
        aria-label={`Upload ${kindLabel[kind].toLowerCase()}`}
        onChange={(event) => select(event.target.files?.[0])}
      />
      {file ? (
        <div className="selected-file">
          <FileText size={22} />
          <div>
            <strong>{file.name}</strong>
            <span>{(file.size / 1024).toFixed(0)} KB · Ready to process</span>
          </div>
          <Button
            variant="ghost"
            size="icon"
            type="button"
            className="icon-button"
            aria-label={`Remove ${kindLabel[kind]}`}
            onClick={() => select()}
          >
            <X size={16} />
          </Button>
        </div>
      ) : (
        <button type="button" className="drop-target" onClick={() => input.current?.click()}>
          <UploadCloud size={25} strokeWidth={1.5} />
          <span>
            <strong>Click to upload</strong> or drag and drop
          </span>
          <small>PDF, PNG, JPG or TXT · up to 20 MB</small>
        </button>
      )}
      {error && <p className="field-error">{error}</p>}
    </div>
  );
}

export default function UploadDialog({
  close,
  done,
}: {
  close: () => void;
  done: (id: string, created: boolean) => void;
}) {
  const [files, setFiles] = useState<Partial<Record<Kind, File>>>({});
  const [errors, setErrors] = useState<Partial<Record<Kind, string>>>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  function choose(kind: Kind, file?: File) {
    if (
      file &&
      (!/\.(pdf|png|jpe?g|txt)$/i.test(file.name) ||
        file.size > 20 * 1024 * 1024 ||
        file.size === 0)
    ) {
      setErrors((old) => ({
        ...old,
        [kind]: 'Choose a nonempty PDF, image, or TXT file under 20 MB.',
      }));
      return;
    }
    setErrors((old) => ({ ...old, [kind]: undefined }));
    setFiles((old) => ({ ...old, [kind]: file }));
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const missing = kinds.filter((kind) => !files[kind]);
    if (missing.length) {
      setErrors(Object.fromEntries(missing.map((kind) => [kind, 'This document is required.'])));
      return;
    }
    setBusy(true);
    setError('');
    const form = new FormData();
    kinds.forEach((kind) => form.append(kind, files[kind]!));
    try {
      let result: { id: string; created: boolean };
      const settings = await api<{ direct_uploads: boolean }>('/settings');
      if (settings.direct_uploads) {
        const references: Record<string, { pathname: string; filename: string }> = {};
        for (const kind of kinds) {
          const file = files[kind]!;
          const filename = file.name.replace(/[^a-zA-Z0-9_.-]/g, '_').slice(-180);
          const extension = file.name.split('.').at(-1)!.toLowerCase();
          const contentType =
            extension === 'pdf'
              ? 'application/pdf'
              : extension === 'png'
                ? 'image/png'
                : extension === 'txt'
                  ? 'text/plain'
                  : 'image/jpeg';
          const uploaded = await uploadBlob(`incoming/${crypto.randomUUID()}/${filename}`, file, {
            access: 'private',
            handleUploadUrl: apiUrl('/blob-upload'),
            contentType,
          });
          references[kind] = { pathname: uploaded.pathname, filename: file.name };
        }
        result = await api('/cases/from-uploads', jsonRequest('POST', references));
      } else {
        result = await api('/cases', { method: 'POST', body: form });
      }
      done(result.id, result.created);
    } catch (error) {
      setError((error as Error).message);
      setBusy(false);
    }
  }
  return (
    <Modal close={busy ? () => {} : close} label="New reconciliation">
      <form onSubmit={submit}>
        <div className="modal-header">
          <div>
            <span className="eyebrow">LET’S CONNECT THE DOCUMENTS</span>
            <h2>New reconciliation</h2>
            <p>Upload a complete set. We’ll take it from here.</p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            type="button"
            className="icon-button"
            aria-label="Close upload"
            disabled={busy}
            onClick={close}
          >
            <X size={20} />
          </Button>
        </div>
        <div className="upload-slots">
          {kinds.map((kind) => (
            <FileSlot
              key={kind}
              kind={kind}
              file={files[kind]}
              choose={(file) => choose(kind, file)}
              error={errors[kind]}
            />
          ))}
        </div>
        <div className="upload-note">
          <ShieldCheck size={17} />
          <span>
            English documents with labelled fields and item codes. Every extracted value stays
            linked to its source.
          </span>
        </div>
        <a className="sample-link" href={apiUrl('/samples')}>
          <Download size={15} />
          Download sample document sets <ArrowRight size={14} />
        </a>
        {error && (
          <div className="error-banner" role="alert">
            <AlertCircle size={17} />
            {error}
          </div>
        )}
        <div className="modal-footer">
          <span>{Object.values(files).filter(Boolean).length} of 3 documents added</span>
          <Button
            variant="outline"
            type="button"
            className="button"
            disabled={busy}
            onClick={close}
          >
            Cancel
          </Button>
          <Button variant="default" type="submit" className="button button-primary" disabled={busy}>
            {busy ? <LoaderCircle className="spin" size={16} /> : <CheckCircle2 size={16} />}
            {busy ? 'Uploading documents…' : 'Start reconciliation'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
