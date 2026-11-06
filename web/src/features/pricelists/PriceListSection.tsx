import { useMemo, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { messageOf } from '../../api/client'
import { DataTable, type Column, type SortState } from '../../components/DataTable'
import { ConfirmDialog } from '../../components/Dialog'
import { FormError } from '../../components/Field'
import { useDebounced } from '../../components/useDebounced'
import { usePriceTypes } from '../lookups/lookups'
import {
  NONE,
  activate,
  deleteDraft,
  formatAmount,
  getPriceList,
  listLines,
  listVersions,
  type Line,
  type LineParams,
  type ListStatus,
  type PriceList,
  type PriceListDetail,
} from './api'
import { LineDialog } from './LineDialog'

const PAGE_SIZE = 50
const STATUS_LABEL: Record<ListStatus, string> = { draft: 'Draft', active: 'Active', expired: 'Expired' }

export function ListStatusBadge({ status }: { status: ListStatus }) {
  return <span className={`badge list-${status}`}>{STATUS_LABEL[status]}</span>
}

const fmtDate = (d: string | null) => (d ? new Date(`${d}T00:00:00`).toLocaleDateString() : 'open-ended')
const fmtWhen = (ts: string) => new Date(ts).toLocaleString()

interface Props {
  partyId: string
  /** "/customers/<id>" or "/vendors/<id>" — the import wizard lives under it. */
  basePath: string
  partyActive: boolean
  canEdit: boolean
  /** Revision to show first (e.g. right after an import). */
  initialRevision?: number
}

/** The customer's / vendor's price list: versions, filters, lines, activation. */
export function PriceListSection({ partyId, basePath, partyActive, canEdit, initialRevision }: Props) {
  const navigate = useNavigate()
  const versions = useQuery({ queryKey: ['pricelists', partyId], queryFn: () => listVersions(partyId) })
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const list = versions.data ?? []
  const selected =
    list.find((v) => v.id === selectedId) ??
    list.find((v) => v.revision === initialRevision) ??
    list.find((v) => v.effective_status === 'active') ??
    list[0]

  return (
    <section className="card stack" aria-labelledby="price-list-h">
      <div className="section-head">
        <h2 id="price-list-h">Price list</h2>
        {canEdit && partyActive && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              void navigate(`${basePath}/import`)
            }}
          >
            Import price list
          </button>
        )}
      </div>
      {versions.isPending && <p className="muted">Loading…</p>}
      {versions.isError && <p className="error">{messageOf(versions.error)}</p>}
      {versions.data && list.length === 0 && (
        <p className="muted">No price list yet. Use “Import price list” to load one from the file.</p>
      )}
      {selected && (
        <>
          <SelectedVersion key={selected.id} summary={selected} canEdit={canEdit} />
          <VersionHistory versions={list} selectedId={selected.id} onSelect={setSelectedId} />
        </>
      )}
    </section>
  )
}

function SelectedVersion({ summary, canEdit }: { summary: PriceList; canEdit: boolean }) {
  const queryClient = useQueryClient()
  const detail = useQuery({ queryKey: ['pricelist', summary.id], queryFn: () => getPriceList(summary.id) })
  const [confirming, setConfirming] = useState(false)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [only, setOnly] = useState<LineParams['only']>('')

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['pricelists'] })
    void queryClient.invalidateQueries({ queryKey: ['pricelist', summary.id] })
    void queryClient.invalidateQueries({ queryKey: ['pricelines', summary.id] })
  }
  const act = useMutation({
    mutationFn: () => activate(detail.data ?? summary),
    onSuccess: () => {
      setConfirming(false)
      setNotice('Price list activated.')
      refresh()
    },
    onError: () => {
      setConfirming(false)
    },
  })
  const del = useMutation({
    mutationFn: () => deleteDraft(detail.data ?? summary),
    onSuccess: () => {
      setConfirmingDelete(false)
      queryClient.removeQueries({ queryKey: ['pricelist', summary.id] })
      queryClient.removeQueries({ queryKey: ['pricelines', summary.id] })
      void queryClient.invalidateQueries({ queryKey: ['pricelists'] })
    },
    onError: () => {
      setConfirmingDelete(false)
    },
  })

  const d = detail.data
  return (
    <div className="stack">
      <div className="version-head">
        <div>
          <h3>
            {summary.name} <ListStatusBadge status={summary.effective_status} />{' '}
            <span className="muted small">Rev {summary.revision}</span>
          </h3>
          <p className="muted small" aria-label="Last update">
            Last update {fmtWhen(summary.updated_at)} by {summary.updated_by_email ?? 'unknown'}
          </p>
        </div>
        {canEdit && summary.status === 'draft' && (
          <div className="actions">
            <button
              type="button"
              className="btn btn-danger"
              disabled={del.isPending || act.isPending || !d}
              onClick={() => {
                del.reset()
                setConfirmingDelete(true)
              }}
            >
              Delete draft
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={act.isPending || del.isPending || !d}
              onClick={() => {
                act.reset()
                setConfirming(true)
              }}
            >
              Activate
            </button>
          </div>
        )}
      </div>
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {act.error ? <FormError message={messageOf(act.error)} /> : null}
      {del.error ? <FormError message={messageOf(del.error)} /> : null}
      <dl className="kv kv-wide" aria-label="Price list details">
        <dt>Price currencies</dt>
        <dd>
          {d
            ? [...new Set(d.price_columns.map((p) => p.currency))].sort().join(', ') || '—'
            : 'Loading…'}
        </dd>
        <dt>Valid</dt>
        <dd>
          {fmtDate(summary.valid_from)} – {fmtDate(summary.valid_to)}
        </dd>
        <dt>Lines</dt>
        <dd>
          {summary.line_count.toLocaleString()}
          {d && d.lines_with_warnings > 0 && ` · ${d.lines_with_warnings.toLocaleString()} with warnings`}
          {d && d.excluded_lines > 0 && ` · ${d.excluded_lines.toLocaleString()} excluded`}
        </dd>
        <dt>Source file</dt>
        <dd className="wrap">
          {summary.source_file_name}
          {summary.source_sheet ? ` (sheet ${summary.source_sheet})` : ''}
        </dd>
        <dt>Imported</dt>
        <dd>
          {fmtWhen(summary.imported_at)} by {summary.imported_by_email ?? 'unknown'}
        </dd>
      </dl>
      {d && d.duplicate_groups > 0 && (
        <div className="warning-box" role="alert">
          <strong>{d.duplicate_groups} duplicate group(s).</strong> The same product appears more than
          once with the same dimensions. Open each duplicate and exclude the extra lines; the list
          can&apos;t be activated until then.{' '}
          <button
            type="button"
            className="btn btn-small"
            onClick={() => {
              setOnly('duplicates')
            }}
          >
            Show duplicates
          </button>
        </div>
      )}
      {d && (
        <Lines
          detail={d}
          canEdit={canEdit}
          only={only}
          onOnlyChange={setOnly}
          onChanged={(msg) => {
            setNotice(msg)
            refresh()
          }}
        />
      )}

      <ConfirmDialog
        open={confirming}
        title="Activate price list"
        confirmLabel="Activate"
        busy={act.isPending}
        message={
          <p>
            Activate <strong>{summary.name}</strong> (Rev {summary.revision}) from{' '}
            {fmtDate(summary.valid_from)}? Any active {summary.currency} list of this
            {' '}customer/vendor that overlaps it will be expired. Its prices stay in the history.
          </p>
        }
        onConfirm={() => {
          act.mutate()
        }}
        onCancel={() => {
          setConfirming(false)
        }}
      />
      <ConfirmDialog
        open={confirmingDelete}
        title="Delete draft"
        confirmLabel="Delete draft"
        danger
        busy={del.isPending}
        message={
          <p>
            Delete the draft <strong>{summary.name}</strong> (Rev {summary.revision},{' '}
            {summary.line_count.toLocaleString()} lines)? It disappears from the version history.
            Active and expired versions are not affected.
          </p>
        }
        onConfirm={() => {
          del.mutate()
        }}
        onCancel={() => {
          setConfirmingDelete(false)
        }}
      />
    </div>
  )
}

interface LinesProps {
  detail: PriceListDetail
  canEdit: boolean
  only: LineParams['only']
  onOnlyChange: (o: LineParams['only']) => void
  onChanged: (message: string) => void
}

function Lines({ detail, canEdit, only, onOnlyChange, onChanged }: LinesProps) {
  const priceTypes = usePriceTypes()
  const [search, setSearch] = useState('')
  const [brand, setBrand] = useState('')
  const [category, setCategory] = useState('')
  const [sort, setSort] = useState<SortState>({ sort: 'source_row', order: 'asc' })
  // The page belongs to the current "Show" filter: switching it starts again at page 1.
  const [paging, setPaging] = useState({ only, page: 1 })
  const page = paging.only === only ? paging.page : 1
  const setPage = (p: number) => {
    setPaging({ only, page: p })
  }
  const [open, setOpen] = useState<Line | null>(null)
  const q = useDebounced(search)

  const params: LineParams = { q, brand, category, only, ...sort, page, page_size: PAGE_SIZE }
  const lines = useQuery({
    queryKey: ['pricelines', detail.id, params],
    queryFn: () => listLines(detail.id, params),
    placeholderData: keepPreviousData,
  })

  const typeName = (code: string) => priceTypes.data?.find((t) => t.code === code)?.name ?? code
  const columns = useMemo<Column<Line>[]>(() => {
    const cols: Column<Line>[] = [
      { id: 'ean', header: 'EAN', accessorFn: (l) => l.ean ?? '—' },
      {
        id: 'description',
        header: 'Description',
        accessorKey: 'description',
        cell: ({ row }) => (
          <span className="cell-clip" title={row.original.description ?? undefined}>
            {row.original.description ?? '—'}
          </span>
        ),
      },
      {
        id: 'moq',
        header: 'MOQ',
        enableSorting: false,
        cell: ({ row }) => <span className="num">{row.original.moq ?? '—'}</span>,
      },
    ]
    const priceTypesInList = [...new Set(detail.price_columns.map((p) => p.price_type))]
    const pricesFor = (line: Line, priceType: string) =>
      line.prices
        .filter((p) => p.price_type === priceType)
        .sort((a, b) => a.currency.localeCompare(b.currency))
    for (const priceType of priceTypesInList) {
      cols.push({
        id: `price:${priceType}`,
        header: typeName(priceType),
        enableSorting: false,
        cell: ({ row }) => {
          const prices = pricesFor(row.original, priceType)
          return prices.length === 0 ? '—' : prices.map((p) => (
            <div className="num" key={p.currency}>{formatAmount(p.amount)}</div>
          ))
        },
      })
      cols.push({
        id: `currency:${priceType}`,
        header: priceTypesInList.length === 1 ? 'Currency' : `${typeName(priceType)} currency`,
        enableSorting: false,
        cell: ({ row }) => {
          const prices = pricesFor(row.original, priceType)
          return prices.length === 0 ? '—' : prices.map((p) => (
            <div key={p.currency}>{p.currency}</div>
          ))
        },
      })
    }
    cols.push(
      { id: 'asin', header: 'ASIN', accessorFn: (l) => l.asin ?? '—' },
      { id: 'brand', header: 'Brand', accessorFn: (l) => l.brand ?? '—' },
      { id: 'category', header: 'Category', accessorFn: (l) => l.category ?? '—' },
    )
    cols.push({
      id: 'observations',
      header: 'Observations',
      enableSorting: false,
      cell: ({ row }) => (
        <span className="cell-clip" title={row.original.observations ?? undefined}>
          {row.original.observations ?? '—'}
        </span>
      ),
    })
    cols.push({
      id: 'flags',
      header: '',
      enableSorting: false,
      cell: ({ row }) => <LineFlags line={row.original} />,
    })
    return cols
    // typeName depends on the price-type lookup, which loads once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail.price_columns, priceTypes.data])

  const facetLabel = (v: string | null, n: number) => `${v ?? 'None'} (${n.toLocaleString()})`

  return (
    <div className="stack">
      <div className="filters">
        <input
          type="search"
          placeholder="Search EAN, ASIN or description"
          aria-label="Search lines"
          maxLength={100}
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setPage(1)
          }}
        />
        <select
          aria-label="Filter by category"
          value={category}
          onChange={(e) => {
            setCategory(e.target.value)
            setPage(1)
          }}
        >
          <option value="">All categories</option>
          {detail.categories.map((f) => (
            <option key={f.value ?? NONE} value={f.value ?? NONE}>
              {facetLabel(f.value, f.count)}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by brand"
          value={brand}
          onChange={(e) => {
            setBrand(e.target.value)
            setPage(1)
          }}
        >
          <option value="">All brands</option>
          {detail.brands.map((f) => (
            <option key={f.value ?? NONE} value={f.value ?? NONE}>
              {facetLabel(f.value, f.count)}
            </option>
          ))}
        </select>
        <select
          aria-label="Show lines"
          value={only}
          onChange={(e) => {
            onOnlyChange(e.target.value as LineParams['only'])
          }}
        >
          <option value="">All lines</option>
          <option value="warnings">With warnings</option>
          <option value="duplicates">Duplicates</option>
          <option value="excluded">Excluded</option>
        </select>
      </div>
      {lines.isError ? (
        <p className="error">{messageOf(lines.error)}</p>
      ) : (
        <DataTable
          columns={columns}
          rows={lines.data?.items ?? []}
          total={lines.data?.total ?? 0}
          page={page}
          pageSize={PAGE_SIZE}
          sort={sort}
          loading={lines.isFetching}
          onSortChange={(s) => {
            setSort(s)
            setPage(1)
          }}
          onPageChange={setPage}
          onRowClick={setOpen}
          rowLabel={(l) => `Row ${String(l.source_row)}`}
          emptyText="No lines match."
          ariaLabel="Price list lines"
        />
      )}
      {open && (
        <LineDialog
          line={open}
          listIsDraft={detail.status === 'draft'}
          canEdit={canEdit}
          typeName={typeName}
          onClose={() => {
            setOpen(null)
          }}
          onSaved={(msg) => {
            setOpen(null)
            onChanged(msg)
          }}
          onConflict={() => {
            setOpen(null)
            onChanged('Someone else changed this line. The list has been reloaded: open it again.')
          }}
        />
      )}
    </div>
  )
}

function LineFlags({ line }: { line: Line }) {
  return (
    <span className="flags">
      {!line.is_active && <span className="badge list-expired">Excluded</span>}
      {line.duplicate && <span className="badge status-on_hold">Duplicate</span>}
      {line.issues.filter((i) => i !== 'duplicate_key').length > 0 && (
        <span className="badge status-on_hold" title={line.issues.join(', ')}>
          ⚠ {line.issues.filter((i) => i !== 'duplicate_key').length}
        </span>
      )}
    </span>
  )
}

function VersionHistory({
  versions,
  selectedId,
  onSelect,
}: {
  versions: PriceList[]
  selectedId: string
  onSelect: (id: string) => void
}) {
  return (
    <details className="history" open={versions.length > 1}>
      <summary>Version history ({versions.length})</summary>
      <table className="data-table" aria-label="Version history">
        <thead>
          <tr>
            <th>Rev</th>
            <th>Name</th>
            <th>Status</th>
            <th>Valid</th>
            <th>Currency</th>
            <th>Lines</th>
            <th>Imported</th>
            <th>File</th>
          </tr>
        </thead>
        <tbody>
          {versions.map((v) => (
            <tr
              key={v.id}
              className={v.id === selectedId ? 'clickable selected' : 'clickable'}
              aria-label={`Revision ${String(v.revision)}`}
              aria-selected={v.id === selectedId}
              tabIndex={0}
              onClick={() => {
                onSelect(v.id)
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') onSelect(v.id)
              }}
            >
              <td>{v.revision}</td>
              <td>{v.name}</td>
              <td>
                <ListStatusBadge status={v.effective_status} />
              </td>
              <td>
                {fmtDate(v.valid_from)} – {fmtDate(v.valid_to)}
              </td>
              <td>{v.currency}</td>
              <td>{v.line_count.toLocaleString()}</td>
              <td>
                {new Date(v.imported_at).toLocaleDateString()} · {v.imported_by_email ?? '—'}
              </td>
              <td className="wrap">{v.source_file_name}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  )
}
