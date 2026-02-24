import { useState, useMemo } from 'react';
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

function groupByTicker(positions) {
  const groups = {};
  for (const pos of positions) {
    const t = pos.ticker;
    if (!groups[t]) groups[t] = [];
    groups[t].push(pos);
  }

  return Object.entries(groups).map(([ticker, items]) => {
    if (items.length === 1) {
      return { ticker, isSingle: true, positions: items, parent: items[0] };
    }
    // Aggregate parent row
    const parent = {
      ticker,
      asset_type: items.map(p => p.asset_type.charAt(0).toUpperCase() + p.asset_type.slice(1)).join(' + '),
      quantity: null,
      avg_cost: null,
      current_price: null,
      market_value: items.reduce((s, p) => s + (p.market_value || 0), 0),
      day_pnl: items.reduce((s, p) => s + (p.day_pnl || 0), 0),
      pnl: items.reduce((s, p) => s + (p.pnl || 0), 0),
      pnl_percent: null,
      delta_per_unit: null,
      delta: items.reduce((s, p) => s + (p.delta || 0), 0),
      theta: items.reduce((s, p) => s + (p.theta || 0), 0),
      weight: items.reduce((s, p) => s + (p.weight || 0), 0),
    };
    // Compute aggregate pnl_percent from total cost
    const totalCost = items.reduce((s, p) => s + (p.cost_basis || 0), 0);
    if (totalCost !== 0) {
      parent.pnl_percent = (parent.pnl / Math.abs(totalCost)) * 100;
    }
    return { ticker, isSingle: false, positions: items, parent };
  });
}

export default function HoldingsTable({ positions, onNavigateToAnalysis, onRefresh }) {
  const [sortKey, setSortKey] = useState('market_value');
  const [sortAsc, setSortAsc] = useState(false);
  const [expandedTickers, setExpandedTickers] = useState(new Set());
  const [deleting, setDeleting] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [saving, setSaving] = useState(false);

  const groups = useMemo(() => groupByTicker(positions), [positions]);

  const sortedGroups = useMemo(() => {
    return [...groups].sort((a, b) => {
      let va = a.parent[sortKey], vb = b.parent[sortKey];
      if (va == null) va = sortAsc ? Infinity : -Infinity;
      if (vb == null) vb = sortAsc ? Infinity : -Infinity;
      if (typeof va === 'string') va = va.toLowerCase();
      if (typeof vb === 'string') vb = vb.toLowerCase();
      if (va < vb) return sortAsc ? -1 : 1;
      if (va > vb) return sortAsc ? 1 : -1;
      return 0;
    });
  }, [groups, sortKey, sortAsc]);

  function handleSort(key) {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  function toggleExpand(ticker) {
    setExpandedTickers(prev => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  }

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
        // For grouped parent rows, asset_type is already a summary string
        if (typeof val === 'string' && val.includes('+')) return val;
        const label = val.charAt(0).toUpperCase() + val.slice(1);
        const isShort = row.direction === 'short';
        const dirBadge = isShort ? ' Short' : '';
        if (val === 'call' || val === 'put') {
          return <>{isShort && <span className="direction-badge short">Short</span>}{label} {row.strike || ''}</>;
        }
        return <>{isShort && <span className="direction-badge short">Short</span>}{label}</>;
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
        return `${val >= 0 ? '+' : ''}${Number(val).toFixed(1)}%`;
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
  const totalPositions = positions.length;

  return (
    <div className="holdings-section">
      <div className="holdings-header">
        <h3>Holdings</h3>
        <span className="holdings-count">{totalPositions} position{totalPositions !== 1 ? 's' : ''} / {groups.length} ticker{groups.length !== 1 ? 's' : ''}</span>
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
            {sortedGroups.map(group => {
              const isExpanded = expandedTickers.has(group.ticker);
              const isMulti = !group.isSingle;

              return (
                <GroupRows
                  key={group.ticker}
                  group={group}
                  isMulti={isMulti}
                  isExpanded={isExpanded}
                  onToggle={() => toggleExpand(group.ticker)}
                  onNavigate={onNavigateToAnalysis}
                  formatVal={formatVal}
                  pnlClass={pnlClass}
                  isEditing={isEditing}
                  editForm={editForm}
                  setEditForm={setEditForm}
                  onEditStart={handleEditStart}
                  onEditCancel={handleEditCancel}
                  onEditSave={handleEditSave}
                  onDelete={handleDelete}
                  deleting={deleting}
                  saving={saving}
                />
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function GroupRows({
  group, isMulti, isExpanded, onToggle, onNavigate,
  formatVal, pnlClass, isEditing, editForm, setEditForm,
  onEditStart, onEditCancel, onEditSave, onDelete, deleting, saving,
}) {
  const { ticker, parent, positions } = group;

  if (!isMulti) {
    // Single position — render as normal row
    const pos = positions[0];
    return (
      <PositionRow
        pos={pos}
        isChild={false}
        onNavigate={onNavigate}
        formatVal={formatVal}
        pnlClass={pnlClass}
        isEditing={isEditing}
        editForm={editForm}
        setEditForm={setEditForm}
        onEditStart={onEditStart}
        onEditCancel={onEditCancel}
        onEditSave={onEditSave}
        onDelete={onDelete}
        deleting={deleting}
        saving={saving}
      />
    );
  }

  // Multi-position group
  return (
    <>
      {/* Parent row */}
      <tr
        className={`holdings-row group-parent-row ${isExpanded ? 'group-expanded' : ''}`}
        onClick={onToggle}
      >
        {COLUMNS.map(col => {
          const val = parent[col.key];
          const coloredKeys = ['pnl', 'pnl_percent', 'day_pnl', 'theta'];
          const isColored = coloredKeys.includes(col.key);

          if (col.key === 'ticker') {
            return (
              <td key={col.key} className="ticker-cell group-ticker-cell">
                <span className="group-chevron">{isExpanded ? '\u25BC' : '\u25B6'}</span>
                {ticker}
              </td>
            );
          }

          return (
            <td
              key={col.key}
              className={`${col.align === 'right' ? 'text-right' : ''} ${isColored ? pnlClass(val) : ''}`}
            >
              {formatVal(col, val, parent)}
            </td>
          );
        })}
        <td className="actions-cell"></td>
      </tr>

      {/* Child rows */}
      {isExpanded && positions.map(pos => (
        <PositionRow
          key={pos.id}
          pos={pos}
          isChild={true}
          onNavigate={onNavigate}
          formatVal={formatVal}
          pnlClass={pnlClass}
          isEditing={isEditing}
          editForm={editForm}
          setEditForm={setEditForm}
          onEditStart={onEditStart}
          onEditCancel={onEditCancel}
          onEditSave={onEditSave}
          onDelete={onDelete}
          deleting={deleting}
          saving={saving}
        />
      ))}
    </>
  );
}

function PositionRow({
  pos, isChild, onNavigate, formatVal, pnlClass,
  isEditing, editForm, setEditForm,
  onEditStart, onEditCancel, onEditSave, onDelete, deleting, saving,
}) {
  const editing = isEditing(pos.id);

  return (
    <tr
      className={`holdings-row ${editing ? 'editing-row' : ''} ${isChild ? 'child-row' : ''}`}
      onClick={() => !editing && onNavigate(pos.ticker)}
    >
      {COLUMNS.map(col => {
        const val = pos[col.key];
        const coloredKeys = ['pnl', 'pnl_percent', 'day_pnl', 'delta_per_unit', 'theta'];
        const isColored = coloredKeys.includes(col.key);

        // Editable cells when in edit mode
        if (editing) {
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

        if (col.key === 'ticker' && isChild) {
          return (
            <td key={col.key} className="ticker-cell child-ticker-cell">
              {pos.ticker}
            </td>
          );
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
        {editing ? (
          <div className="edit-actions">
            <button
              className="btn-save-inline"
              title="Save"
              disabled={saving}
              onClick={e => onEditSave(e, pos.id)}
            >
              {'\u2713'}
            </button>
            <button
              className="btn-cancel-inline"
              title="Cancel"
              onClick={onEditCancel}
            >
              {'\u2715'}
            </button>
          </div>
        ) : (
          <div className="edit-actions">
            <button
              className="btn-edit"
              title="Edit position"
              onClick={e => onEditStart(e, pos)}
            >
              {'\u270E'}
            </button>
            <button
              className="btn-remove"
              title="Delete position"
              disabled={deleting === pos.id}
              onClick={e => onDelete(e, pos.id)}
            >
              &times;
            </button>
          </div>
        )}
      </td>
    </tr>
  );
}
