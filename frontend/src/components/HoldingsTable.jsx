import { useState } from 'react';
import { deletePosition, updatePosition } from '../api/client';

const COLUMNS = [
  { key: 'ticker', label: 'Ticker', align: 'left' },
  { key: 'asset_type', label: 'Type', align: 'left' },
  { key: 'quantity', label: 'Qty', align: 'right' },
  { key: 'avg_cost', label: 'Avg Cost', align: 'right' },
  { key: 'current_price', label: 'Price', align: 'right' },
  { key: 'market_value', label: 'Mkt Value', align: 'right' },
  { key: 'day_pnl', label: 'Day P&L', align: 'right' },
  { key: 'pnl', label: 'P&L', align: 'right' },
  { key: 'pnl_percent', label: 'P&L %', align: 'right' },
  { key: 'delta_per_unit', label: 'Delta', align: 'right' },
  { key: 'theta', label: 'Theta', align: 'right' },
  { key: 'weight', label: 'Weight', align: 'right' },
];

export default function HoldingsTable({ positions, onNavigateToAnalysis, onRefresh }) {
  const [sortKey, setSortKey] = useState('market_value');
  const [sortAsc, setSortAsc] = useState(false);
  const [deleting, setDeleting] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [saving, setSaving] = useState(false);

  function handleSort(key) {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  const sorted = [...positions].sort((a, b) => {
    let va = a[sortKey], vb = b[sortKey];
    if (va == null) va = sortAsc ? Infinity : -Infinity;
    if (vb == null) vb = sortAsc ? Infinity : -Infinity;
    if (typeof va === 'string') va = va.toLowerCase();
    if (typeof vb === 'string') vb = vb.toLowerCase();
    if (va < vb) return sortAsc ? -1 : 1;
    if (va > vb) return sortAsc ? 1 : -1;
    return 0;
  });

  async function handleDelete(e, id) {
    e.stopPropagation();
    setDeleting(id);
    try {
      await deletePosition(id);
      onRefresh();
    } catch (err) {
      console.error('Delete failed:', err.message);
    } finally {
      setDeleting(null);
    }
  }

  function handleEditStart(e, pos) {
    e.stopPropagation();
    setEditingId(pos.id);
    setEditForm({
      quantity: pos.quantity,
      avg_cost: pos.avg_cost,
      strike: pos.strike || '',
      expiration: pos.expiration || '',
    });
  }

  function handleEditCancel(e) {
    e.stopPropagation();
    setEditingId(null);
    setEditForm({});
  }

  async function handleEditSave(e, id) {
    e.stopPropagation();
    setSaving(true);
    try {
      const payload = {
        quantity: parseInt(editForm.quantity, 10),
        avg_cost: parseFloat(editForm.avg_cost),
      };
      if (editForm.strike) payload.strike = parseFloat(editForm.strike);
      if (editForm.expiration) payload.expiration = editForm.expiration;
      await updatePosition(id, payload);
      setEditingId(null);
      setEditForm({});
      onRefresh();
    } catch (err) {
      console.error('Update failed:', err.message);
    } finally {
      setSaving(false);
    }
  }

  function formatVal(col, val, row) {
    if (val == null || val === undefined) return '\u2014';
    switch (col.key) {
      case 'asset_type': {
        const label = val.charAt(0).toUpperCase() + val.slice(1);
        if (val === 'call' || val === 'put') {
          return `${label} ${row.strike || ''}`;
        }
        return label;
      }
      case 'avg_cost':
      case 'current_price':
        return `$${Number(val).toFixed(2)}`;
      case 'market_value':
        return `$${Number(val).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
      case 'day_pnl':
      case 'pnl':
        return `${val >= 0 ? '+' : ''}$${Number(val).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
      case 'pnl_percent':
        return `${val >= 0 ? '+' : ''}${Number(val).toFixed(2)}%`;
      case 'delta_per_unit':
        return Number(val).toFixed(2);
      case 'theta':
        return `$${Number(val).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
      case 'weight':
        return `${Number(val).toFixed(1)}%`;
      default:
        return String(val);
    }
  }

  function pnlClass(val) {
    if (val == null) return '';
    return val >= 0 ? 'text-green' : 'text-red';
  }

  const isEditing = (id) => editingId === id;

  return (
    <div className="holdings-section">
      <div className="holdings-header">
        <h3>Holdings</h3>
        <span className="holdings-count">{positions.length} position{positions.length !== 1 ? 's' : ''}</span>
      </div>
      <div className="holdings-table-wrapper">
        <table className="holdings-table">
          <thead>
            <tr>
              {COLUMNS.map(col => (
                <th
                  key={col.key}
                  className={`sort-header ${col.align === 'right' ? 'text-right' : ''} ${sortKey === col.key ? 'sorted' : ''}`}
                  onClick={() => handleSort(col.key)}
                >
                  {col.label}
                  {sortKey === col.key && <span className="sort-arrow">{sortAsc ? ' \u25B2' : ' \u25BC'}</span>}
                </th>
              ))}
              <th></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(pos => (
              <tr
                key={pos.id}
                className={`holdings-row ${isEditing(pos.id) ? 'editing-row' : ''}`}
                onClick={() => !isEditing(pos.id) && onNavigateToAnalysis(pos.ticker)}
              >
                {COLUMNS.map(col => {
                  const val = pos[col.key];
                  const coloredKeys = ['pnl', 'pnl_percent', 'day_pnl', 'delta_per_unit', 'theta'];
                  const isColored = coloredKeys.includes(col.key);

                  // Editable cells when in edit mode
                  if (isEditing(pos.id)) {
                    if (col.key === 'quantity') {
                      return (
                        <td key={col.key} className="text-right" onClick={e => e.stopPropagation()}>
                          <input
                            className="inline-edit-input"
                            type="number"
                            value={editForm.quantity}
                            onChange={e => setEditForm({ ...editForm, quantity: e.target.value })}
                          />
                        </td>
                      );
                    }
                    if (col.key === 'avg_cost') {
                      return (
                        <td key={col.key} className="text-right" onClick={e => e.stopPropagation()}>
                          <input
                            className="inline-edit-input"
                            type="number"
                            step="0.01"
                            value={editForm.avg_cost}
                            onChange={e => setEditForm({ ...editForm, avg_cost: e.target.value })}
                          />
                        </td>
                      );
                    }
                  }

                  return (
                    <td
                      key={col.key}
                      className={`${col.align === 'right' ? 'text-right' : ''} ${isColored ? pnlClass(val) : ''} ${col.key === 'ticker' ? 'ticker-cell' : ''}`}
                    >
                      {formatVal(col, val, pos)}
                    </td>
                  );
                })}
                <td className="actions-cell" onClick={e => e.stopPropagation()}>
                  {isEditing(pos.id) ? (
                    <div className="edit-actions">
                      <button
                        className="btn-save-inline"
                        title="Save"
                        disabled={saving}
                        onClick={e => handleEditSave(e, pos.id)}
                      >
                        {'\u2713'}
                      </button>
                      <button
                        className="btn-cancel-inline"
                        title="Cancel"
                        onClick={handleEditCancel}
                      >
                        {'\u2715'}
                      </button>
                    </div>
                  ) : (
                    <div className="edit-actions">
                      <button
                        className="btn-edit"
                        title="Edit position"
                        onClick={e => handleEditStart(e, pos)}
                      >
                        {'\u270E'}
                      </button>
                      <button
                        className="btn-remove"
                        title="Delete position"
                        disabled={deleting === pos.id}
                        onClick={e => handleDelete(e, pos.id)}
                      >
                        &times;
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
