import { useState, useRef, useEffect } from 'react';
import { addPosition, uploadCSV, uploadOCR, confirmImport, getOptionsExpirations } from '../api/client';

const ASSET_TYPES = ['stock', 'call', 'put'];

export default function ManagePortfolioModal({ onClose, onSaved }) {
  const [tab, setTab] = useState('manual');
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Manage Portfolio</h2>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>
        <div className="modal-tabs">
          {[['manual', 'Manual Entry'], ['csv', 'CSV Upload'], ['ocr', 'Screenshot OCR']].map(([key, label]) => (
            <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>
              {label}
            </button>
          ))}
        </div>
        <div className="modal-body">
          {tab === 'manual' && <ManualEntry onSaved={onSaved} />}
          {tab === 'csv' && <CSVUpload onSaved={onSaved} />}
          {tab === 'ocr' && <OCRUpload onSaved={onSaved} />}
        </div>
      </div>
    </div>
  );
}

function ManualEntry({ onSaved }) {
  const [form, setForm] = useState({
    ticker: '', asset_type: 'stock', direction: 'long', quantity: '', avg_cost: '', strike: '', expiration: '',
  });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [expirations, setExpirations] = useState([]);
  const [expirationsLoading, setExpirationsLoading] = useState(false);
  const [expirationsError, setExpirationsError] = useState('');

  const isOption = form.asset_type === 'call' || form.asset_type === 'put';

  // Fetch valid expirations when ticker changes and type is call/put
  useEffect(() => {
    if (!isOption || !form.ticker || form.ticker.length < 1) {
      setExpirations([]);
      setExpirationsError('');
      return;
    }
    const ticker = form.ticker.toUpperCase().trim();
    if (ticker.length < 1) return;

    const timer = setTimeout(() => {
      setExpirationsLoading(true);
      setExpirationsError('');
      getOptionsExpirations(ticker)
        .then(data => {
          const exps = data.expirations || [];
          setExpirations(exps);
          if (exps.length === 0) {
            setExpirationsError('No options available for this ticker');
          }
          // Auto-select first expiration if current selection is not in list
          if (form.expiration && !exps.includes(form.expiration)) {
            setForm(prev => ({ ...prev, expiration: exps.length > 0 ? exps[0] : '' }));
          }
        })
        .catch(() => {
          setExpirations([]);
          setExpirationsError('Could not load expirations');
        })
        .finally(() => setExpirationsLoading(false));
    }, 500); // debounce 500ms

    return () => clearTimeout(timer);
  }, [form.ticker, isOption]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    if (!form.ticker || !form.quantity || !form.avg_cost) {
      setError('Ticker, quantity, and avg cost are required');
      return;
    }
    if (isOption && (!form.strike || !form.expiration)) {
      setError('Strike and expiration are required for options');
      return;
    }
    setSaving(true);
    try {
      const payload = {
        ticker: form.ticker.toUpperCase(),
        asset_type: form.asset_type,
        direction: form.direction,
        quantity: parseInt(form.quantity, 10),
        avg_cost: parseFloat(form.avg_cost),
        strike: isOption ? parseFloat(form.strike) : null,
        expiration: isOption ? form.expiration : null,
      };
      await addPosition(payload);
      setForm({ ticker: '', asset_type: 'stock', direction: 'long', quantity: '', avg_cost: '', strike: '', expiration: '' });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="manual-entry-form" onSubmit={handleSubmit}>
      <div className="form-row">
        <label>Ticker
          <input value={form.ticker} onChange={e => setForm({ ...form, ticker: e.target.value })} placeholder="AAPL" />
        </label>
        <label>Type
          <select value={form.asset_type} onChange={e => setForm({ ...form, asset_type: e.target.value, expiration: '' })}>
            {ASSET_TYPES.map(t => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
          </select>
        </label>
        <label>Direction
          <select value={form.direction} onChange={e => setForm({ ...form, direction: e.target.value })}>
            <option value="long">Long</option>
            <option value="short">Short</option>
          </select>
        </label>
      </div>
      <div className="form-row">
        <label>Quantity
          <input type="number" value={form.quantity} onChange={e => setForm({ ...form, quantity: e.target.value })} placeholder="100" />
        </label>
        <label>Avg Cost
          <input type="number" step="0.01" value={form.avg_cost} onChange={e => setForm({ ...form, avg_cost: e.target.value })} placeholder="150.00" />
        </label>
      </div>
      {isOption && (
        <div className="form-row">
          <label>Strike
            <input type="number" step="0.5" value={form.strike} onChange={e => setForm({ ...form, strike: e.target.value })} placeholder="155" />
          </label>
          <label>Expiration
            {expirationsLoading ? (
              <span className="spinner" style={{ display: 'inline-block', marginTop: 8 }} />
            ) : expirations.length > 0 ? (
              <select value={form.expiration} onChange={e => setForm({ ...form, expiration: e.target.value })}>
                <option value="">Select expiration...</option>
                {expirations.map(exp => (
                  <option key={exp} value={exp}>{exp}</option>
                ))}
              </select>
            ) : (
              <input type="date" value={form.expiration} onChange={e => setForm({ ...form, expiration: e.target.value })} />
            )}
            {expirationsError && <span className="form-hint-error">{expirationsError}</span>}
          </label>
        </div>
      )}
      {error && <div className="form-error">{error}</div>}
      <button type="submit" className="btn-primary" disabled={saving}>
        {saving ? 'Adding...' : 'Add Position'}
      </button>
    </form>
  );
}

function CSVUpload({ onSaved }) {
  const fileRef = useRef(null);
  const [rows, setRows] = useState(null);
  const [errors, setErrors] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [confirming, setConfirming] = useState(false);

  async function handleFile(e) {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    setErrors([]);
    try {
      const result = await uploadCSV(file);
      setRows(result.rows);
      setErrors(result.errors || []);
    } catch (err) {
      setErrors([err.message]);
    } finally {
      setUploading(false);
    }
  }

  async function handleConfirm() {
    if (!rows || rows.length === 0) return;
    setConfirming(true);
    try {
      await confirmImport(rows);
      setRows(null);
      onSaved();
    } catch (err) {
      setErrors([err.message]);
    } finally {
      setConfirming(false);
    }
  }

  function removeRow(idx) {
    setRows(rows.filter((_, i) => i !== idx));
  }

  return (
    <div className="csv-upload">
      <div className="upload-area" onClick={() => fileRef.current?.click()}>
        <p>Click to select a CSV file</p>
        <p className="upload-hint">Expected columns: ticker, type, quantity, avg_cost, strike, expiration</p>
        <input ref={fileRef} type="file" accept=".csv" onChange={handleFile} hidden />
      </div>
      {uploading && <div className="loading"><span className="spinner" /> Parsing CSV...</div>}
      {errors.length > 0 && <div className="form-error">{errors.join('; ')}</div>}
      {rows && rows.length > 0 && (
        <>
          <div className="import-preview">
            <table className="preview-table">
              <thead>
                <tr>
                  <th>Ticker</th><th>Type</th><th>Qty</th><th>Avg Cost</th><th>Strike</th><th>Exp</th><th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td>{r.ticker}</td>
                    <td>{r.asset_type}</td>
                    <td>{r.quantity}</td>
                    <td>{r.avg_cost}</td>
                    <td>{r.strike || '—'}</td>
                    <td>{r.expiration || '—'}</td>
                    <td><button className="btn-remove" onClick={() => removeRow(i)}>&times;</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button className="btn-primary" onClick={handleConfirm} disabled={confirming}>
            {confirming ? 'Importing...' : `Import ${rows.length} Position${rows.length > 1 ? 's' : ''}`}
          </button>
        </>
      )}
      {rows && rows.length === 0 && <p className="upload-hint">No valid positions found in the CSV.</p>}
    </div>
  );
}

function OCRUpload({ onSaved }) {
  const fileRef = useRef(null);
  const [rows, setRows] = useState(null);
  const [errors, setErrors] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [confirming, setConfirming] = useState(false);

  async function handleFile(e) {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    setErrors([]);
    try {
      const result = await uploadOCR(file);
      setRows(result.rows);
      setErrors(result.errors || []);
    } catch (err) {
      setErrors([err.message]);
    } finally {
      setUploading(false);
    }
  }

  async function handleConfirm() {
    if (!rows || rows.length === 0) return;
    setConfirming(true);
    try {
      await confirmImport(rows);
      setRows(null);
      onSaved();
    } catch (err) {
      setErrors([err.message]);
    } finally {
      setConfirming(false);
    }
  }

  function removeRow(idx) {
    setRows(rows.filter((_, i) => i !== idx));
  }

  return (
    <div className="ocr-upload">
      <div className="upload-area" onClick={() => fileRef.current?.click()}>
        <p>Click to upload a brokerage screenshot</p>
        <p className="upload-hint">Supports PNG, JPG. Requires Tesseract on the server.</p>
        <input ref={fileRef} type="file" accept="image/*" onChange={handleFile} hidden />
      </div>
      {uploading && <div className="loading"><span className="spinner" /> Running OCR...</div>}
      {errors.length > 0 && <div className="form-error">{errors.join('; ')}</div>}
      {rows && rows.length > 0 && (
        <>
          <div className="import-preview">
            <table className="preview-table">
              <thead>
                <tr>
                  <th>Ticker</th><th>Type</th><th>Qty</th><th>Avg Cost</th><th>Strike</th><th>Exp</th><th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td>{r.ticker}</td>
                    <td>{r.asset_type}</td>
                    <td>{r.quantity}</td>
                    <td>{r.avg_cost}</td>
                    <td>{r.strike || '—'}</td>
                    <td>{r.expiration || '—'}</td>
                    <td><button className="btn-remove" onClick={() => removeRow(i)}>&times;</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button className="btn-primary" onClick={handleConfirm} disabled={confirming}>
            {confirming ? 'Importing...' : `Import ${rows.length} Position${rows.length > 1 ? 's' : ''}`}
          </button>
        </>
      )}
      {rows && rows.length === 0 && <p className="upload-hint">No positions detected in the image.</p>}
    </div>
  );
}
